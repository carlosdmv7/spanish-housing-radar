"""
Unit tests for the pure mortgage math in app/components/mortgage.py.

These functions are deterministic (no Streamlit, no I/O), so we can assert exact
financial behaviour: the French-amortisation instalment, that the schedule fully
repays the loan, and that the affordability inverses round-trip.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.mortgage import (  # noqa: E402
    compute_mortgage,
    compute_variable_mortgage,
    max_affordable_loan,
    required_income,
)
import pytest  # noqa: E402


class TestComputeMortgage:
    def test_known_instalment(self):
        """200k @ 3% over 30y → ~843.21 €/month (standard annuity formula)."""
        r = compute_mortgage(200_000, 3.0, 30)
        assert r.monthly_payment == pytest.approx(843.21, abs=0.5)

    def test_schedule_repays_loan_in_full(self):
        r = compute_mortgage(200_000, 3.0, 30)
        assert len(r.schedule) == 30 * 12
        assert r.schedule[-1]["balance"] == pytest.approx(0.0, abs=1.0)

    def test_total_interest_is_paid_minus_principal(self):
        r = compute_mortgage(200_000, 3.0, 30)
        assert r.total_interest == pytest.approx(r.total_paid - r.principal, abs=1.0)
        assert r.total_interest > 0

    def test_zero_rate_is_straight_line(self):
        """At 0% the instalment is simply principal / number of months."""
        r = compute_mortgage(120_000, 0.0, 10)
        assert r.monthly_payment == pytest.approx(1_000.0, abs=0.01)
        assert r.total_interest == pytest.approx(0.0, abs=0.01)

    def test_higher_rate_costs_more(self):
        cheap = compute_mortgage(200_000, 2.0, 30)
        dear = compute_mortgage(200_000, 4.0, 30)
        assert dear.monthly_payment > cheap.monthly_payment


class TestVariableMortgage:
    def test_stress_scenario_is_more_expensive(self):
        base, stress = compute_variable_mortgage(200_000, 1.0, 2.5, 30, euribor_stress=1.0)
        assert stress.monthly_payment > base.monthly_payment

    def test_base_equals_spread_plus_euribor(self):
        base, _ = compute_variable_mortgage(200_000, 1.0, 2.5, 30)
        equivalent = compute_mortgage(200_000, 3.5, 30)
        assert base.monthly_payment == pytest.approx(equivalent.monthly_payment, abs=0.01)


class TestAffordabilityInverses:
    def test_required_income_round_trips_with_max_loan(self):
        """required_income and max_affordable_loan should be inverses at a fixed ratio."""
        principal, rate, years, ratio = 180_000, 3.0, 30, 35.0
        income = required_income(principal, rate, years, ratio)
        loan = max_affordable_loan(income, ratio, rate, years)
        assert loan == pytest.approx(principal, rel=0.001)

    def test_required_income_respects_ratio(self):
        principal, rate, years, ratio = 180_000, 3.0, 30, 35.0
        income = required_income(principal, rate, years, ratio)
        payment = compute_mortgage(principal, rate, years).monthly_payment
        assert payment / income == pytest.approx(ratio / 100, abs=0.001)
