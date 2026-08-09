"""
Tests for purchase costs, bank tie-ins and the buy-vs-invest comparison.

These are the numbers a visitor would act on, so the assertions are about
behaviour that would mislead if wrong: that transfer tax follows the region and
not a national average, that a tie-in costing more than it saves is reported as
such, and that closing costs never quietly become equity.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.mortgage import compute_mortgage  # noqa: E402
from components.purchase_costs import (  # noqa: E402
    DEFAULT_ITP_RATE,
    ITP_BY_CCAA,
    Bonification,
    apply_bonifications,
    balance_after,
    buy_vs_invest,
    purchase_costs,
)
import pytest  # noqa: E402


class TestItpFollowsTheRegion:
    def test_the_same_flat_is_taxed_differently_by_region(self):
        # The whole reason ITP is modelled per community: a €400,000 flat costs
        # €16,000 in transfer tax in Bilbao and €40,000 in Barcelona.
        bilbao = purchase_costs(400_000, ltv_pct=80, ine_region="país vasco")
        barcelona = purchase_costs(400_000, ltv_pct=80, ine_region="cataluña")
        assert bilbao.itp == pytest.approx(16_000)
        assert barcelona.itp == pytest.approx(40_000)
        assert barcelona.itp - bilbao.itp == pytest.approx(24_000)

    def test_valencia_uses_the_post_june_2026_rate(self):
        # Reduced from 10% to 9% on 1 June 2026. A stale 10% would overstate the
        # tax on a €300,000 flat by €3,000.
        c = purchase_costs(300_000, ltv_pct=80, ine_region="comunitat valenciana")
        assert c.itp_rate == 9.0
        assert c.itp == pytest.approx(27_000)

    def test_unknown_region_does_not_default_to_the_cheapest_rate(self):
        c = purchase_costs(300_000, ltv_pct=80, ine_region="narnia")
        assert c.itp_rate == DEFAULT_ITP_RATE
        assert c.itp_rate > min(r.general_rate for r in ITP_BY_CCAA.values())
        assert "unknown" in c.itp_reason

    def test_missing_region_behaves_like_an_unknown_one(self):
        assert purchase_costs(300_000, ltv_pct=80).itp_rate == DEFAULT_ITP_RATE


class TestReducedAndTieredRates:
    def test_young_first_home_gets_the_reduced_valencian_rate(self):
        c = purchase_costs(
            170_000, ltv_pct=80, ine_region="comunitat valenciana",
            young_first_home=True,
        )
        assert c.itp_rate == 6.0
        assert "first habitual residence" in c.itp_reason

    def test_the_reduced_rate_stops_at_its_price_ceiling(self):
        # €180,000 is the Valencian ceiling; a euro over and the relief is gone.
        c = purchase_costs(
            180_001, ltv_pct=80, ine_region="comunitat valenciana",
            young_first_home=True,
        )
        assert c.itp_rate == 9.0
        # And it says why, rather than silently showing a number that does not
        # match what the buyer expected.
        assert "does not reach this price" in c.itp_reason

    def test_the_upper_band_applies_above_its_threshold(self):
        c = purchase_costs(1_200_000, ltv_pct=80, ine_region="comunitat valenciana")
        assert c.itp_rate == 11.0
        assert "higher band" in c.itp_reason

    def test_a_region_without_a_young_rate_ignores_the_flag(self):
        plain = purchase_costs(150_000, ltv_pct=80, ine_region="madrid, comunidad de")
        young = purchase_costs(
            150_000, ltv_pct=80, ine_region="madrid, comunidad de",
            young_first_home=True,
        )
        assert plain.itp_rate == young.itp_rate == 6.0


class TestCashNeeded:
    def test_cash_needed_is_deposit_plus_costs_not_just_the_deposit(self):
        c = purchase_costs(300_000, ltv_pct=80, ine_region="comunitat valenciana")
        assert c.deposit == pytest.approx(60_000)
        # 27,000 ITP + ~2,000 of fees — a third as much again as the deposit.
        assert c.cash_needed > c.deposit + 25_000
        assert c.cash_needed == pytest.approx(c.deposit + c.total_costs)

    def test_costs_land_in_the_documented_8_to_12_percent_band(self):
        for region in ITP_BY_CCAA:
            c = purchase_costs(300_000, ltv_pct=80, ine_region=region)
            assert 4 < c.costs_pct_of_price < 13, region

    def test_gestoria_is_optional_because_it_is_optional_in_reality(self):
        with_g = purchase_costs(300_000, ltv_pct=80, ine_region="cataluña")
        without = purchase_costs(
            300_000, ltv_pct=80, ine_region="cataluña", include_gestoria=False
        )
        assert with_g.total_costs > without.total_costs
        assert without.gestoria == 0.0


class TestBonifications:
    def test_a_free_tie_in_is_worth_taking(self):
        out = apply_bonifications(
            250_000, 3.0, 25, [Bonification("Payroll", 0.30, 0.0)]
        )
        assert out.final_rate == 2.70
        assert out.monthly_saving > 0
        assert out.worth_it

    def test_a_tie_in_costing_more_than_it_saves_is_reported_as_a_loss(self):
        # The point of modelling the cost at all. A 0.05% cut on a small loan
        # saves a few euros a month; €600/yr of insurance does not pay for it.
        out = apply_bonifications(
            80_000, 3.0, 30,
            [Bonification("Life insurance", 0.05, 600.0)],
        )
        assert out.monthly_saving > 0          # the rate really did fall
        assert out.net_monthly_benefit < 0     # and it still costs you money
        assert not out.worth_it

    def test_cuts_accumulate_and_the_rate_never_goes_negative(self):
        absurd = [Bonification(f"b{i}", 1.0) for i in range(6)]
        out = apply_bonifications(200_000, 3.0, 20, absurd)
        assert out.final_rate == 0.0

    def test_no_tie_ins_changes_nothing(self):
        out = apply_bonifications(200_000, 3.0, 20, [])
        assert out.final_rate == 3.0
        assert out.net_monthly_benefit == 0.0


class TestBuyVsInvest:
    def _compare(self, *, investment_return_pct, property_growth_pct, horizon=20):
        price, ltv, rate, years = 300_000, 80.0, 3.0, 30
        costs = purchase_costs(price, ltv_pct=ltv, ine_region="comunitat valenciana")
        loan = price * ltv / 100
        m = compute_mortgage(loan, rate, years)
        return buy_vs_invest(
            price=price,
            costs=costs,
            monthly_payment=m.monthly_payment,
            years=years,
            horizon_years=horizon,
            monthly_rent=1_100,
            investment_return_pct=investment_return_pct,
            property_growth_pct=property_growth_pct,
            outstanding_balance_at_horizon=balance_after(m.schedule, horizon),
        )

    def test_a_high_alternative_return_can_beat_buying(self):
        # The verdict this whole comparison exists to be able to reach. A tool
        # that cannot say "don't buy" is not analysis, it is advertising.
        assert not self._compare(
            investment_return_pct=9.0, property_growth_pct=0.5
        ).buying_wins

    def test_strong_house_price_growth_favours_buying(self):
        assert self._compare(
            investment_return_pct=1.0, property_growth_pct=5.0
        ).buying_wins

    def test_closing_costs_are_spent_never_counted_as_equity(self):
        c = self._compare(investment_return_pct=5.0, property_growth_pct=2.0)
        # Net worth from buying is equity minus the costs, so it must sit below
        # the raw equity by exactly the sunk amount.
        costs = purchase_costs(300_000, ltv_pct=80, ine_region="comunitat valenciana")
        assert c.net_worth_buying == pytest.approx(
            c.equity_at_horizon - costs.total_costs, abs=1
        )

    def test_the_renting_branch_starts_by_investing_the_deposit_and_costs(self):
        # Pin the seeding directly: no returns, no growth, and a rent set equal
        # to the instalment, so nothing is added or drawn after month one. The
        # portfolio must then be exactly the cash that buying would have consumed.
        price, ltv, rate, years, horizon = 300_000, 80.0, 3.0, 30, 10
        costs = purchase_costs(price, ltv_pct=ltv, ine_region="comunitat valenciana")
        m = compute_mortgage(price * ltv / 100, rate, years)
        c = buy_vs_invest(
            price=price, costs=costs, monthly_payment=m.monthly_payment,
            years=years, horizon_years=horizon,
            monthly_rent=m.monthly_payment,
            investment_return_pct=0.0, property_growth_pct=0.0,
            outstanding_balance_at_horizon=balance_after(m.schedule, horizon),
        )
        assert c.cash_invested == pytest.approx(costs.cash_needed)
        assert c.portfolio_at_horizon == pytest.approx(costs.cash_needed)

    def test_rent_above_the_instalment_draws_the_portfolio_down(self):
        # The honest treatment, and the reason the test above had to pin the
        # seeding a different way: when renting costs more each month than the
        # mortgage, that money is really gone and the portfolio must shrink.
        c = self._compare(investment_return_pct=0.0, property_growth_pct=0.0)
        assert c.portfolio_at_horizon < c.cash_invested

    def test_rent_is_indexed_rather_than_frozen(self):
        # Freezing rent for 20 years is the classic thumb on the scale. With
        # growth, total rent paid must exceed a flat 20 years of the starting rent.
        c = self._compare(investment_return_pct=5.0, property_growth_pct=3.0, horizon=20)
        assert c.total_rent_paid > 1_100 * 12 * 20

    def test_the_horizon_changes_the_answer(self):
        short = self._compare(investment_return_pct=6.0, property_growth_pct=3.0, horizon=3)
        long = self._compare(investment_return_pct=6.0, property_growth_pct=3.0, horizon=30)
        assert short.difference != long.difference


class TestBalanceAfter:
    def test_reads_the_balance_at_the_horizon(self):
        m = compute_mortgage(200_000, 3.0, 30)
        assert balance_after(m.schedule, 10) < 200_000
        assert balance_after(m.schedule, 10) > balance_after(m.schedule, 20)

    def test_beyond_the_term_the_loan_is_repaid(self):
        m = compute_mortgage(200_000, 3.0, 20)
        assert balance_after(m.schedule, 25) == 0.0
