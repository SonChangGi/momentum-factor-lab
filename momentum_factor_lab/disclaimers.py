DATA_LIMITATIONS = (
    "This lab uses a current liquid US individual-stock candidate universe and free/public data. ETFs are excluded from candidate holdings; benchmark ETFs may be used only as comparators. "
    "Historical backtests can contain survivorship bias, delisting omissions, benchmark ETF inception/adjustment caveats, "
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
