"""One authenticated household; mutual-fund accounts represent household members."""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.models.mutual_fund import SIP, MutualFundScheme, MutualFundHolding, MutualFundTransaction
from app.investments.calculations import ZERO, SCENARIOS, DISCLOSURE, rounded, future_value, xirr
from app.portfolio.service import today

CONTRIBUTIONS = {'PURCHASE', 'SIP'}
OUTFLOWS = {'PURCHASE', 'SIP', 'SWITCH_IN'}
INFLOWS = {'REDEMPTION', 'SWITCH_OUT', 'DIVIDEND'}

def monthly_contributions(db, day=None):
    day = day or today()
    rows = db.scalars(select(MutualFundTransaction).where(
        MutualFundTransaction.status == 'CONFIRMED',
        MutualFundTransaction.transaction_type.in_(CONTRIBUTIONS),
        MutualFundTransaction.transaction_date >= day.replace(day=1),
        MutualFundTransaction.transaction_date <= day)).all()
    return sum((row.amount for row in rows), ZERO)

def actual(scheme, holding, transactions):
    contributed = sum((t.amount for t in transactions if t.transaction_type in CONTRIBUTIONS), ZERO)
    current = holding.current_value if holding else None
    gain = current - holding.invested_amount if holding and holding.invested_amount is not None else None
    rate = None
    if holding and scheme.history_complete and not any(t.transaction_date > holding.valuation_date for t in transactions):
        flows = [(t.transaction_date, -t.amount if t.transaction_type in OUTFLOWS else t.amount) for t in transactions]
        flows.append((holding.valuation_date, current))
        rate = xirr(flows)
    return dict(contributed=contributed, current_value=current, gain_loss=gain, xirr=rate,
                valuation_date=holding.valuation_date if holding else None,
                history_complete=scheme.history_complete)

def data(db):
    schemes = db.scalars(select(MutualFundScheme).order_by(MutualFundScheme.id)).all()
    holdings = {h.scheme_id:h for h in db.scalars(select(MutualFundHolding))}
    transactions = db.scalars(select(MutualFundTransaction).where(MutualFundTransaction.status == 'CONFIRMED')).all()
    sips = db.scalars(select(SIP).order_by(SIP.id)).all()
    return schemes, holdings, transactions, sips

def active(sip, day):
    return sip.status == 'ACTIVE' and (sip.end_date is None or sip.end_date >= day)

def sip_views(db):
    schemes, holdings, transactions, sips = data(db)
    by_id = {s.id:s for s in schemes}
    return [dict(id=s.id, scheme_id=s.scheme_id, scheme_name=by_id[s.scheme_id].scheme_name,
        category=by_id[s.scheme_id].category, source=s.source, currency=by_id[s.scheme_id].currency,
        monthly_amount=s.monthly_amount, sip_day=s.sip_day, start_date=s.start_date,
        end_date=s.end_date, status=s.status,
        scheme_actual=actual(by_id[s.scheme_id], holdings.get(s.scheme_id), [t for t in transactions if t.scheme_id == s.scheme_id])) for s in sips]

def summary(db):
    schemes, holdings, transactions, sips = data(db)
    metrics = [actual(s, holdings.get(s.id), [t for t in transactions if t.scheme_id == s.id]) for s in schemes]
    complete = bool(schemes) and all(s.history_complete and s.id in holdings for s in schemes)
    dates = {h.valuation_date for h in holdings.values()}
    flows = [(t.transaction_date, -t.amount if t.transaction_type in OUTFLOWS else t.amount) for t in transactions]
    flows += [(h.valuation_date, h.current_value) for h in holdings.values()]
    rate = xirr(flows) if complete and len(dates) == 1 and all(t.transaction_date <= next(iter(dates)) for t in transactions) else None
    current = sum((h.current_value for h in holdings.values()), ZERO) if len(holdings) == len(schemes) else None
    return dict(active_sips=sum(active(s,today()) for s in sips), monthly_sip=sum((s.monthly_amount for s in sips if active(s,today())), ZERO),
        contributed=sum((m['contributed'] for m in metrics), ZERO), current_value=current,
        gain_loss=sum((m['gain_loss'] for m in metrics), ZERO) if metrics and all(m['gain_loss'] is not None for m in metrics) else None,
        xirr=rate, history_complete=complete, monthly_mf_contributions=monthly_contributions(db),
        valuation_dates=sorted(dates), schemes=[dict(id=s.id, scheme_name=s.scheme_name, **m) for s,m in zip(schemes, metrics)])

def payments(sip, day, months):
    result = []
    for offset in range(1, months+1):
        index = day.year*12 + day.month-1 + offset
        year, month = divmod(index,12)
        due = date(year, month+1, min(sip.sip_day or day.day, monthrange(year,month+1)[1]))
        result.append(sip.monthly_amount if sip.status == 'ACTIVE' and sip.start_date <= due and (sip.end_date is None or due <= sip.end_date) else ZERO)
    return result

def projections(db, rate):
    schemes, holdings, transactions, sips = data(db)
    if any(s.currency != 'INR' for s in schemes):
        raise ValueError('Only INR projections are supported')
    day = today()
    by_id = {s.id:s for s in schemes}
    groups = {s.id:[p for p in sips if p.scheme_id == s.id and active(p,day)] for s in schemes}
    entries = []
    for sip in sips:
        if not active(sip,day):
            continue
        holding = holdings.get(sip.scheme_id)
        total = sum((p.monthly_amount for p in groups[sip.scheme_id]), ZERO)
        corpus = holding.current_value * sip.monthly_amount / total if holding else ZERO
        points = {name:future_value(corpus,payments(sip,day,years*12),rate) for name,years in [('one_year',1),('five_years',5),('ten_years',10)]}
        entries.append(dict(id=sip.id, scheme_name=by_id[sip.scheme_id].scheme_name, monthly_sip=sip.monthly_amount,
            current_value=holding.current_value if holding else None, allocated_starting_corpus=corpus,
            assumption_percent=rate, projections=points))
    corpus = sum((h.current_value for h in holdings.values()), ZERO)
    def combined(year):
        monthly = [sum((payments(s,day,year*12)[i] for s in sips),ZERO) for i in range(year*12)]
        point = future_value(corpus,monthly,rate)
        point['total_contributions'] = sum((t.amount for t in transactions if t.transaction_type in CONTRIBUTIONS),ZERO) + point['future_contributions']
        return point
    return dict(assumption_percent=rate, scenarios=[dict(name=name,annual_return=value) for name,value in SCENARIOS], disclosure=DISCLOSURE,
        as_of=day, corpus_complete=len(holdings)==len(schemes), starting_corpus=corpus,
        monthly_sip=sum((s.monthly_amount for s in sips if active(s,day)),ZERO), sips=entries,
        combined={name:combined(year) for name,year in [('one_year',1),('five_years',5),('ten_years',10)]},
        chart=[dict(year=year,**combined(year)) for year in range(11)])

def serialize(value):
    if isinstance(value, Decimal):
        return str(rounded(value))
    if isinstance(value, dict):
        return {k:serialize(v) for k,v in value.items()}
    if isinstance(value, list):
        return [serialize(v) for v in value]
    return value

def family_composition(settled_stocks_etfs, available_cash, mutual_fund_value):
    """Compose actual assets; unknown components keep the total unavailable."""
    parts = dict(stocks_etfs=settled_stocks_etfs, mutual_funds=mutual_fund_value, cash=available_cash)
    return dict(**parts, long_term_wealth=sum(parts.values(), ZERO) if all(v is not None for v in parts.values()) else None)
