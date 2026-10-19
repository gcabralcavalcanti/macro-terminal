"""Universe, paths and limits. Everything that costs money is capped here."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"        # last good copy of every dataset (versioned: the page works offline)
DOWNLOADS = ROOT / ".downloads"        # big raw files (CVM zips); not versioned
WEB = ROOT / "web"                     # page template (HTML/CSS/JS)
SITE = ROOT / "site"                   # generated static site (what GitHub Pages serves)
SCHEMAS = ROOT / "schemas"
RECORDINGS = ROOT / "recordings"       # recorded LLM answers: response cache + demo mode
NEWSLETTER = ROOT / "newsletter"
LOGS = ROOT / "logs"                   # one JSON line per LLM call (not versioned)

USER_AGENT = "macro-terminal/1.0 (portfolio project; public data only)"
HTTP_TIMEOUT_S = 60
HTTP_TRIES = 3

# ---------------------------------------------------------------- macro, Brazil (BCB SGS)
# code: (key, label, unit, frequency, plausible range)
SGS = {
    432: ("selic_target", "Selic target", "% p.a.", "daily", (0.0, 60.0)),
    13522: ("ipca_12m", "IPCA 12m", "% 12m", "monthly", (-5.0, 50.0)),
    433: ("ipca_mom", "IPCA m/m", "% m/m", "monthly", (-3.0, 10.0)),
    1: ("usdbrl_ptax", "USD/BRL PTAX", "BRL per USD", "daily", (1.0, 15.0)),
    24369: ("unemployment_br", "Unemployment (PNADC)", "% labor force", "monthly", (2.0, 25.0)),
}
SGS_START = "01/01/2021"

# Focus survey (BCB Olinda): median expectation for the current and next year
FOCUS = {
    "IPCA": ("focus_ipca", "Focus IPCA", "%", (-5.0, 50.0)),
    "Selic": ("focus_selic", "Focus Selic (end of year)", "% p.a.", (0.0, 60.0)),
    "Câmbio": ("focus_fx", "Focus USD/BRL (end of year)", "BRL per USD", (1.0, 15.0)),
    "PIB Total": ("focus_gdp", "Focus GDP", "% y/y", (-15.0, 15.0)),
}
FOCUS_WEEKS = 12

# ---------------------------------------------------------------- macro, United States (FRED, no key)
FRED = {
    "DFF": ("fed_funds", "Fed funds (effective)", "% p.a.", "daily", (0.0, 25.0)),
    "DGS2": ("ust_2y", "UST 2y", "%", "daily", (0.0, 25.0)),
    "DGS10": ("ust_10y", "UST 10y", "%", "daily", (0.0, 25.0)),
    "CPIAUCSL": ("cpi_us", "CPI (index)", "index 1982-84=100", "monthly", (50.0, 1000.0)),
    "UNRATE": ("unemployment_us", "Unemployment", "% labor force", "monthly", (1.0, 30.0)),
}
FRED_START = "2021-01-01"

# ---------------------------------------------------------------- market (Yahoo Finance via yfinance)
# ticker shown on screen -> (Yahoo symbol, region, name, CVM code for fundamentals/filings or None)
TICKERS = {
    "PETR4": ("PETR4.SA", "BR", "Petrobras PN", 9512),
    "VALE3": ("VALE3.SA", "BR", "Vale ON", 4170),
    "ITUB4": ("ITUB4.SA", "BR", "Itau Unibanco PN", 19348),
    "WEGE3": ("WEGE3.SA", "BR", "WEG ON", 5410),
    "ABEV3": ("ABEV3.SA", "BR", "Ambev ON", 23264),
    "GGBR4": ("GGBR4.SA", "BR", "Gerdau PN", 3980),
    "EMBJ3": ("EMBJ3.SA", "BR", "Embraer ON", 20087),  # ticker was EMBR3 until 2025
    "SUZB3": ("SUZB3.SA", "BR", "Suzano ON", 13986),
    "AAPL": ("AAPL", "US", "Apple", None),
    "MSFT": ("MSFT", "US", "Microsoft", None),
    "NVDA": ("NVDA", "US", "Nvidia", None),
    "AMZN": ("AMZN", "US", "Amazon", None),
    "GOOGL": ("GOOGL", "US", "Alphabet A", None),
    "JPM": ("JPM", "US", "JPMorgan", None),
    "XOM": ("XOM", "US", "Exxon Mobil", None),
    "IBOV": ("^BVSP", "IDX", "Ibovespa", None),
    "SPX": ("^GSPC", "IDX", "S&P 500", None),
    "USDBRL": ("USDBRL=X", "FX", "Dollar / Real", None),
}
BENCHMARK = {"BR": "IBOV", "US": "SPX"}
PRICE_PERIOD = "2y"
# Banks report a different income statement (no "net revenue" line); fundamentals skip them.
NO_FUNDAMENTALS = {"ITUB4"}

# ---------------------------------------------------------------- CVM (open data portal)
CVM_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
FUNDAMENTALS_MAX_AGE_DAYS = 7   # the zips are large (~100 MB); refresh weekly, not daily
FUNDAMENTAL_QUARTERS = 8
FILINGS_KEEP = 40

# ---------------------------------------------------------------- AI daily brief (Claude API)
# Cheapest model that handles a short structured summary.
MODEL = os.environ.get("MACRO_TERMINAL_MODEL", "claude-haiku-5-5")
PRICE_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50)}  # USD (input, output), Anthropic price list
MAX_CALLS_PER_RUN = int(os.environ.get("MACRO_TERMINAL_MAX_CALLS", "2"))  # first try + one retry
MAX_TOKENS = 700
TIMEOUT_S = 45.0
SDK_RETRIES = 2      # network / 429 / 5xx, done by the SDK
SCHEMA_RETRIES = 1   # one extra call if the answer fails our own checks
ASK_MAX_CALLS = int(os.environ.get("MACRO_TERMINAL_ASK_MAX_CALLS", "12"))  # 6 preset questions x (1 + 1 retry)
SERVE_MAX_CALLS = 20   # live questions per local server session
