import yfinance as yf
import pandas as pd
import streamlit as st
from datetime import date, timedelta


# ── Caching strategy ──────────────────────────────────────────────────────────
# st.cache_data caches the return value for `ttl` seconds.
# Price data refreshes every 5 minutes; slow-changing data (info, dividends,
# earnings) refreshes every hour so we don't hammer yfinance.

PRICE_TTL   = 300    # 5 minutes
GENERAL_TTL = 3600   # 1 hour


# ── Price data ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=PRICE_TTL)
def get_current_price(ticker: str) -> float | None:
    """Return the latest market price for a single ticker."""
    try:
        data = yf.Ticker(ticker)
        price = data.fast_info.get("last_price")
        if price is None:
            # Fallback: last close from a 2-day history fetch
            hist = data.history(period="2d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        return round(float(price), 4) if price else None
    except Exception:
        return None


@st.cache_data(ttl=PRICE_TTL)
def get_price_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    Return OHLCV history as a DataFrame.
    period  : 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max
    interval: 1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo
    """
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=PRICE_TTL)
def get_price_history_range(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Return OHLCV history between explicit start/end dates (YYYY-MM-DD)."""
    try:
        df = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=PRICE_TTL)
def get_bulk_current_prices(tickers: list[str]) -> dict[str, float]:
    """
    Fetch current prices for multiple tickers in one yfinance call.
    Returns {ticker: price}. Missing tickers are omitted.
    """
    if not tickers:
        return {}
    try:
        prices = {}
        # Newer yfinance returns a MultiIndex columns DataFrame;
        # easiest cross-version approach is to just call get_current_price
        # per ticker — still fast enough for typical portfolio sizes.
        for t in tickers:
            price = get_current_price(t)
            if price is not None:
                prices[t] = price
        return prices
    except Exception:
        return {}


# ── Ticker info ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=GENERAL_TTL)
def get_ticker_info(ticker: str) -> dict:
    """
    Return yfinance's .info dict for a ticker.
    Useful fields: sector, industry, longName, marketCap,
                   trailingPE, forwardPE, dividendYield, beta,
                   fiftyTwoWeekHigh, fiftyTwoWeekLow,
                   targetMeanPrice, recommendationMean
    """
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


@st.cache_data(ttl=GENERAL_TTL)
def get_bulk_ticker_info(tickers: list[str]) -> dict[str, dict]:
    """Return {ticker: info_dict} for a list of tickers."""
    return {t: get_ticker_info(t) for t in tickers}


# ── Dividends ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=GENERAL_TTL)
def get_dividends(ticker: str) -> pd.Series:
    """Return historical dividend payments as a pandas Series (date → amount)."""
    try:
        divs = yf.Ticker(ticker).dividends
        divs.index = pd.to_datetime(divs.index).tz_localize(None)
        return divs
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=GENERAL_TTL)
def get_dividend_calendar(ticker: str) -> dict:
    """
    Return upcoming dividend info dict.
    Keys vary by ticker but typically include:
    exDividendDate, dividendDate, dividendRate, dividendYield
    """
    try:
        info = yf.Ticker(ticker).info
        return {
            "ex_dividend_date": info.get("exDividendDate"),
            "dividend_rate":    info.get("dividendRate"),
            "dividend_yield":   info.get("dividendYield"),
            "payout_ratio":     info.get("payoutRatio"),
        }
    except Exception:
        return {}


# ── Earnings ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=GENERAL_TTL)
def get_earnings_dates(ticker: str, limit: int = 8) -> pd.DataFrame:
    """
    Return upcoming (and recent) earnings dates.
    Columns: EPS Estimate, Reported EPS, Surprise(%)
    Rows are indexed by date.
    """
    try:
        df = yf.Ticker(ticker).earnings_dates
        if df is None or df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df.head(limit)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=GENERAL_TTL)
def get_earnings_history(ticker: str) -> pd.DataFrame:
    """Return annual and quarterly earnings history."""
    try:
        t = yf.Ticker(ticker)
        quarterly = t.quarterly_earnings
        if quarterly is None:
            return pd.DataFrame()
        return quarterly
    except Exception:
        return pd.DataFrame()


# ── News ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=PRICE_TTL)
def get_news(ticker: str, limit: int = 10) -> list[dict]:
    """
    Return recent news articles for a ticker.
    Each dict has keys: title, publisher, link, providerPublishTime
    """
    try:
        articles = yf.Ticker(ticker).news or []
        return articles[:limit]
    except Exception:
        return []


# ── Technicals helper data ────────────────────────────────────────────────────

@st.cache_data(ttl=PRICE_TTL)
def get_52_week_range(ticker: str) -> dict:
    """Return 52-week high and low from ticker info."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "high": info.get("fiftyTwoWeekHigh"),
            "low":  info.get("fiftyTwoWeekLow"),
        }
    except Exception:
        return {"high": None, "low": None}


@st.cache_data(ttl=GENERAL_TTL)
def get_spy_history(period: str = "1y") -> pd.DataFrame:
    """
    Convenience wrapper for SPY (S&P 500 benchmark) history.
    Used by analytics page for benchmark comparison.
    """
    return get_price_history("SPY", period=period)


# ── Validation ────────────────────────────────────────────────────────────────

def is_valid_ticker(ticker: str) -> bool:
    """
    Quick check — returns True if yfinance can find price data for the ticker.
    Used to validate user input before saving to the database.
    """
    try:
        hist = yf.Ticker(ticker).history(period="2d")
        return not hist.empty
    except Exception:
        return False