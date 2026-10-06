"""Explicit symbol classifications; extend here when an ETF is selected."""

from app.models import Bucket

SYMBOL_BUCKETS: dict[str, Bucket] = {
    "NIFTYBEES": Bucket.NIFTY_50,
    "MIDCAPETF": Bucket.MID_CAP,
    # Add the selected small-cap ETF with Bucket.SMALL_CAP; never guess equities.
}


def bucket_for(symbol: str) -> Bucket:
    return SYMBOL_BUCKETS.get(symbol, Bucket.OTHER)
