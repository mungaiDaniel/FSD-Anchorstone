"""
ESTIMATED monthly instalment for pre-screening only (TEMPORARY: phase 5's product
engine replaces it with real schedules, fees and day counts).

    amortising (business loan, asset finance): equal monthly instalments on a reducing
        balance,  P × r ÷ (1 − (1 + r)^−n),  r = annual rate ÷ 12
    interest_only (bridge loan): monthly interest P × r, and the principal with the last
        month's interest at maturity

Full precision throughout, rounded to the cent once at the end (round_money).
"""
from decimal import Decimal, localcontext

from app.Applications.model import PRODUCTS
from app.utils.money import round_money


def estimate(product_code: str, amount: Decimal, term_months: int, annual_rate_percent: Decimal) -> \
        tuple[Decimal, Decimal]:
    """(estimated monthly instalment, estimated final payment)."""
    shape = PRODUCTS[product_code][3]
    with localcontext() as ctx:
        ctx.prec = 40
        r = Decimal(annual_rate_percent) / Decimal(100) / Decimal(12)
        principal = Decimal(amount)
        if shape == "interest_only":
            interest = principal * r
            return round_money(interest), round_money(principal + interest)
        if r == 0:
            payment = principal / Decimal(term_months)
        else:
            payment = principal * r / (1 - (1 + r) ** -term_months)
        return round_money(payment), round_money(payment)
