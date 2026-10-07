"""Decimal financial math; end-of-month payments and nominal annual rate / 12."""
from datetime import date
from decimal import Decimal, localcontext, ROUND_HALF_UP

ZERO = Decimal(0)
SCENARIOS = [('Conservative', Decimal(8)), ('Base', Decimal(10)), ('Optimistic', Decimal(12))]
DISCLOSURE = 'Projections are illustrations based on the selected annual return assumption, not guaranteed returns.'

def rounded(value):
    return value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def validate_rate(rate):
    if not isinstance(rate, Decimal) or not rate.is_finite() or not ZERO <= rate <= 30:
        raise ValueError('Annual assumption must be between 0 and 30 percent')
    return rate

def future_value(corpus, payments, rate):
    validate_rate(rate)
    with localcontext() as context:
        context.prec = 40
        monthly = rate / Decimal(1200)
        value = corpus
        for payment in payments:
            value = value * (1 + monthly) + payment
        contributed = sum(payments, ZERO)
        return dict(future_contributions=contributed, projected_growth=value-corpus-contributed, projected_value=value)

def xirr(flows):
    """ACT/365, unique conventional root only; bounded Decimal bisection."""
    grouped = {}
    for day, amount in flows:
        grouped[day] = grouped.get(day, ZERO) + amount
    flows = sorted((day, amount) for day, amount in grouped.items() if amount)
    if len(flows) < 2 or flows[0][0] == flows[-1][0]:
        return None
    signs = [amount > 0 for _, amount in flows]
    if signs[0] or not signs[-1] or sum(a != b for a,b in zip(signs, signs[1:])) != 1:
        return None  # Multiple-root/nonconventional histories deliberately unavailable.
    with localcontext() as context:
        context.prec = 40
        first = flows[0][0]
        def npv(rate):
            return sum((amount / ((1+rate) ** (Decimal((day-first).days)/365)) for day,amount in flows), ZERO)
        low, high = Decimal('-.9999'), Decimal(100)
        if npv(low) * npv(high) > 0:
            return None
        for _ in range(200):
            middle = (low+high)/2
            value = npv(middle)
            if abs(value) < Decimal('.00000001'):
                return rounded(middle*100)
            if value > 0:
                low = middle
            else:
                high = middle
        return None
