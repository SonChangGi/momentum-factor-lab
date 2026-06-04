DATA_LIMITATIONS = (
    "This first-pass lab uses a current liquid US stock/ETF universe and free/public data. "
    "Historical backtests can contain survivorship bias, delisting omissions, ETF inception bias, "
    "provider adjusted-price quirks, and historical-universe membership gaps."
)

NON_ADVICE = (
    "Outputs are research artifacts and model-portfolio examples, not personalized financial, "
    "tax, legal, or investment advice. Validate all data, assumptions, risks, and suitability "
    "before making real-money decisions."
)

LIVE_DATA_GATE = (
    "Current recommendation weights require a successful fresh live-data run. Offline sample or "
    "stale live-data runs must not be interpreted as current tradable recommendations."
)

ALL = [DATA_LIMITATIONS, NON_ADVICE, LIVE_DATA_GATE]
