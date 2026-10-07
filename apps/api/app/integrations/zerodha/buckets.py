"""Authoritative version-controlled instrument registry; never infer from names.

Add reviewed instrument definitions here. Tokens are optional provider aliases,
not permanent identifiers: matching symbol/exchange metadata is also required.
"""
from dataclasses import dataclass
from app.models import Bucket


@dataclass(frozen=True)
class InstrumentClassification:
    tradingsymbol: str
    bucket: Bucket
    exchanges: tuple[str, ...] = ("NSE", "BSE")
    instrument_tokens: tuple[int, ...] = ()
    display_name: str | None = None
    source: str = "reviewed_household_registry"


def validate_registry(entries):
    aliases, tokens = {}, {}
    for entry in entries:
        if not entry.tradingsymbol or not entry.exchanges or entry.bucket == Bucket.UNCLASSIFIED:
            raise ValueError("Invalid authoritative instrument definition")
        for exchange in entry.exchanges:
            key = (exchange, entry.tradingsymbol)
            if key in aliases:
                raise ValueError("Duplicate or conflicting instrument alias")
            aliases[key] = entry
        for token in entry.instrument_tokens:
            if token <= 0 or token in tokens:
                raise ValueError("Duplicate or conflicting instrument token")
            tokens[token] = entry
    return aliases, tokens


# These holdings have no reviewed bucket yet. Add an InstrumentClassification
# below only after a deliberate household decision with source metadata.
PENDING_CLASSIFICATION = ("ETERNAL", "FEDERALBNK", "HDFCBANK", "HINDUNILVR", "KWIL",
                          "NYKAA", "HDFCLIFE", "INFY", "KARURVYSYA", "PNB")

REGISTRY = (
    InstrumentClassification("NIFTYBEES", Bucket.NIFTY_50, display_name="Nifty 50 ETF"),
    InstrumentClassification("MIDCAPETF", Bucket.MID_CAP, display_name="Midcap ETF"),
    InstrumentClassification("HDFCSML250", Bucket.SMALL_CAP, display_name="HDFC Smallcap 250 ETF"),

)
ALIASES, TOKENS = validate_registry(REGISTRY)  # Fail at import/startup on conflicts.


def classify_instrument(tradingsymbol: str, exchange: str, instrument_token: int | None = None) -> Bucket:
    alias = ALIASES.get((exchange, tradingsymbol))
    token = TOKENS.get(instrument_token)
    if token is not None and token != alias:
        # A recycled token or conflicting identity must never misclassify money.
        return Bucket.UNCLASSIFIED
    return alias.bucket if alias is not None else Bucket.UNCLASSIFIED
