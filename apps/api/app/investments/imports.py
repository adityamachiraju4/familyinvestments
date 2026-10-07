"""Trusted statement-adapter boundary. No HTTP writes, provider networking or credentials."""
from typing import Protocol, Iterable
from datetime import date
from decimal import Decimal
from app.models.mutual_fund import Source, MutualFundScheme
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.mutual_fund import MutualFundTransaction, SIP

class StatementProvider(Protocol):
    def transactions(self) -> Iterable[dict]: ...

def import_transactions(db: Session, provider: StatementProvider):
    """Caller owns atomic commit/rollback. DB uniqueness also prevents concurrent duplicates.

    Adapter keys must identify the provider's immutable event within a scheme/folio;
    never use row number, amount/date alone, or filename. Conflicting replays fail.
    """
    added = 0
    for data in provider.transactions():
        for key in ('amount', 'units', 'nav'):
            value = data.get(key)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < 0):
                raise ValueError('Financial input must be a finite nonnegative Decimal')
        if not data.get('amount') or not data.get('import_key') or len(data['import_key']) > 255:
            raise ValueError('Positive amount and stable event key required')
        if data.get('source') not in set(Source) or data.get('transaction_type') not in {'PURCHASE','SIP','REDEMPTION','SWITCH_IN','SWITCH_OUT','DIVIDEND'}:
            raise ValueError('Invalid source or transaction type')
        if data.get('status', 'CONFIRMED') not in {'CONFIRMED','PENDING','CANCELLED'} or not isinstance(data.get('transaction_date'), date):
            raise ValueError('Invalid transaction date or status')
        scheme = db.get(MutualFundScheme, data.get('scheme_id'))
        if scheme is None or scheme.currency != 'INR':
            raise ValueError('A verified INR scheme is required')
        row = MutualFundTransaction(**data)
        if row.sip_id is not None:
            sip = db.get(SIP, row.sip_id)
            if sip is None or sip.scheme_id != row.scheme_id:
                raise ValueError('SIP does not belong to the transaction scheme')
        old = db.scalar(select(MutualFundTransaction).where(
            MutualFundTransaction.scheme_id == row.scheme_id,
            MutualFundTransaction.source == row.source,
            MutualFundTransaction.import_key == row.import_key))
        if old:
            if any(getattr(old, key) != value for key,value in data.items()):
                raise ValueError('Conflicting immutable transaction')
            continue
        db.add(row)
        db.flush()
        added += 1
    return added
