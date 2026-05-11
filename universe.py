# ============================================================
# UNIVERSE MODULE — ~1500 US large/mid cap stocks
# ============================================================

import pandas as pd
import yfinance as yf
import logging

logger = logging.getLogger(__name__)


def get_sp500_tickers() -> list:
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        sp500  = [s.replace(".", "-") for s in tables[0]["Symbol"].tolist()]
        logger.info(f"Loaded {len(sp500)} S&P 500 tickers")
        return sp500
    except Exception as e:
        logger.error(f"Failed to fetch S&P 500: {e}")
        return []


def get_nasdaq100_tickers() -> list:
    try:
        for t in pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100"):
            cols = [c.lower() for c in t.columns]
            if "ticker" in cols:
                col     = t.columns[[c.lower() == "ticker" for c in t.columns]][0]
                tickers = [str(s) for s in t[col].dropna().tolist()]
                logger.info(f"Loaded {len(tickers)} NASDAQ-100 tickers")
                return tickers
        return []
    except Exception as e:
        logger.error(f"Failed to fetch NASDAQ-100: {e}")
        return []


def get_extended_universe(max_size: int = 1500) -> list:
    tickers = set()
    tickers.update(get_sp500_tickers())
    tickers.update(get_nasdaq100_tickers())

    supplemental = [
        # Consumer / Retail
        "W","ETSY","CHWY","PDD","SE","MELI","DECK","RH","TJX","ROST","BURL",
        # Fintech / Payments
        "SQ","PYPL","STNE","GPN","FISV","AFRM","UPST","LC","SOFI","HOOD","COIN",
        # Gaming / Entertainment
        "TTWO","EA","RBLX","U","DKNG","PENN","WYNN","MGM","LVS","CZR","MTCH","BMBL",
        # EV / Auto
        "RIVN","LCID","NIO","LI","XPEV",
        # Clean Energy / Solar
        "ENPH","SEDG","FSLR","CSIQ","JKS","PLUG","RUN","GNRC","NEE","AES","ED","EXC","PCG",
        # Oil & Gas
        "DVN","FANG","PXD","EOG","MRO",
        # Cybersecurity
        "CRWD","ZS","PANW","FTNT","CYBR","S",
        # Cloud / Data
        "SNOW","MDB","DDOG","SPLK","ESTC","NET","FSLY","AKAM",
        # SaaS / Enterprise
        "NOW","WDAY","VEEV","CRM","HUBS","OKTA","QLYS","BILL","PCTY","PAYC","PAYX",
        "TWLO","FIVN","DOCU","ASAN","MNDY","CFLT","GTLB","PATH",
        # AI / Quantum
        "AI","BBAI","SOUN","PLTR","IONQ","RGTI",
        # Healthcare / Biotech
        "MRNA","BNTX","NVAX","VRTX","REGN","BIIB","ALNY","BEAM","EDIT","NTLA","CRSP",
        "INCY","EXAS","NTRA",
        # Financials
        "MSTR","SLM","ALLY","OMF",
        # Social Media
        "SNAP","PINS","DUOL",
        # Semis
        "WOLF","AEHR","AMBA",
        # ETFs
        "ARKG","ARKK","XBI","IBB",
    ]
    tickers.update(supplemental)
    universe = sorted(list(tickers))[:max_size]
    logger.info(f"Final universe: {len(universe)} tickers")
    return universe
