import pytest
from app.models import Bucket
from app.integrations.zerodha.buckets import classify_instrument, validate_registry, InstrumentClassification


@pytest.mark.parametrize('symbol,bucket', [('NIFTYBEES',Bucket.NIFTY_50),('MIDCAPETF',Bucket.MID_CAP),('HDFCSML250',Bucket.SMALL_CAP),('ETERNAL',Bucket.LARGE_CAP),('NEWNIFTYMIDSMALLETF',Bucket.UNCLASSIFIED)])
def test_authoritative_classification(symbol,bucket):
    assert classify_instrument(symbol,'NSE') == bucket


def test_unknown_identity_is_not_other():
    assert classify_instrument('NIFTYBEES','UNREVIEWED',123) == Bucket.UNCLASSIFIED
    assert classify_instrument('NEWETF','NSE',99999) == Bucket.UNCLASSIFIED


@pytest.mark.parametrize('entries', [
    (InstrumentClassification('X',Bucket.OTHER), InstrumentClassification('X',Bucket.SMALL_CAP)),
    (InstrumentClassification('X',Bucket.OTHER), InstrumentClassification('X',Bucket.OTHER)),
    (InstrumentClassification('X',Bucket.OTHER,instrument_tokens=(1,)), InstrumentClassification('Y',Bucket.SMALL_CAP,instrument_tokens=(1,))),
])
def test_conflicting_registry_rejected(entries):
    with pytest.raises(ValueError): validate_registry(entries)


def test_reviewed_token_requires_matching_metadata(monkeypatch):
    import app.integrations.zerodha.buckets as registry
    entry = InstrumentClassification('X',Bucket.SMALL_CAP,exchanges=('NSE',),instrument_tokens=(123,))
    aliases,tokens=validate_registry((entry,))
    monkeypatch.setattr(registry,'ALIASES',aliases)
    monkeypatch.setattr(registry,'TOKENS',tokens)
    assert classify_instrument('X','NSE',123)==Bucket.SMALL_CAP
    assert classify_instrument('RECYCLED','NSE',123)==Bucket.UNCLASSIFIED


@pytest.mark.parametrize('symbol,bucket', [
    ('ETERNAL', Bucket.LARGE_CAP), ('HDFCBANK', Bucket.LARGE_CAP),
    ('HINDUNILVR', Bucket.LARGE_CAP), ('HDFCLIFE', Bucket.LARGE_CAP),
    ('INFY', Bucket.LARGE_CAP), ('PNB', Bucket.LARGE_CAP),
    ('FEDERALBNK', Bucket.MID_CAP), ('NYKAA', Bucket.MID_CAP),
    ('KARURVYSYA', Bucket.SMALL_CAP), ('KWIL', Bucket.SMALL_CAP),
])
@pytest.mark.parametrize('exchange', ['NSE', 'BSE'])
def test_deliberate_household_stock_classifications(symbol, bucket, exchange):
    from app.integrations.zerodha.buckets import ALIASES
    assert classify_instrument(symbol, exchange) == bucket
    assert ALIASES[(exchange, symbol)].source == 'explicit_household_classification'
