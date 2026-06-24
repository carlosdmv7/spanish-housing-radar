"""
Pure mortgage math — no Streamlit imports here.
All functions are deterministic and unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class MortgageResult:
    principal:          float   # loan amount (€)
    annual_rate:        float   # interest rate (%)
    years:              int
    monthly_payment:    float   # fixed monthly instalment (€)
    total_paid:         float   # total amount paid over life of loan (€)
    total_interest:     float   # total interest paid (€)
    schedule:           list[dict]  # amortisation table (one row per month)


def compute_mortgage(
    principal:    float,
    annual_rate:  float,   # in %, e.g. 3.0
    years:        int,
) -> MortgageResult:
    """
    French amortisation (annuité constante).
    Returns monthly payment and full schedule.
    """
    n = years * 12
    r = annual_rate / 100 / 12  # monthly rate

    monthly = (
        principal / n
        if r == 0
        else principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    )

    schedule = []
    balance  = principal
    for month in range(1, n + 1):
        interest   = balance * r
        amort      = monthly - interest
        balance    = max(balance - amort, 0.0)
        schedule.append({
            "month":        month,
            "year":         math.ceil(month / 12),
            "payment":      round(monthly, 2),
            "interest":     round(interest, 2),
            "amortisation": round(amort, 2),
            "balance":      round(balance, 2),
        })

    total_paid     = monthly * n
    total_interest = total_paid - principal

    return MortgageResult(
        principal=principal,
        annual_rate=annual_rate,
        years=years,
        monthly_payment=round(monthly, 2),
        total_paid=round(total_paid, 2),
        total_interest=round(total_interest, 2),
        schedule=schedule,
    )


def compute_variable_mortgage(
    principal:      float,
    spread:         float,   # bank spread in %
    euribor:        float,   # current Euribor in %
    years:          int,
    euribor_stress: float = 1.0,   # stress scenario: Euribor + this
) -> tuple[MortgageResult, MortgageResult]:
    """
    Returns (base_scenario, stress_scenario).
    Base: spread + current Euribor.
    Stress: spread + euribor + euribor_stress.
    """
    base   = compute_mortgage(principal, spread + euribor, years)
    stress = compute_mortgage(principal, spread + euribor + euribor_stress, years)
    return base, stress


def max_affordable_loan(
    monthly_net_income: float,
    max_ratio:          float,   # e.g. 35.0 → 35%
    annual_rate:        float,
    years:              int,
) -> float:
    """
    Maximum loan principal given a monthly income and max payment ratio.
    Inverts the annuity formula.
    """
    max_payment = monthly_net_income * max_ratio / 100
    n = years * 12
    r = annual_rate / 100 / 12
    if r == 0:
        return max_payment * n
    return max_payment * ((1 + r) ** n - 1) / (r * (1 + r) ** n)


def required_income(
    principal:   float,
    annual_rate: float,
    years:       int,
    max_ratio:   float = 35.0,
) -> float:
    """
    Minimum monthly net income needed to afford a loan at max_ratio% rule.
    """
    result = compute_mortgage(principal, annual_rate, years)
    return result.monthly_payment / (max_ratio / 100)
