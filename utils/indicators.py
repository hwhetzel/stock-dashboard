import pandas as pd
import numpy as np


def compute_moving_averages(close: pd.Series, windows: list[int]) -> pd.DataFrame:
    """
    Return a DataFrame with one MA column per window.
    Columns named MA_20, MA_50, MA_200 etc.
    """
    df = pd.DataFrame(index=close.index)
    for w in windows:
        df[f"MA_{w}"] = close.rolling(window=w).mean()
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.
    Returns a Series of RSI values (0–100).
    Values < 30 = oversold, > 70 = overbought.
    """
    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)

    # Use exponential moving average for smoothing (Wilder's method)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD indicator.
    Returns DataFrame with columns: MACD, Signal, Histogram.
    MACD    = fast EMA − slow EMA
    Signal  = EMA of MACD
    Histogram = MACD − Signal
    """
    ema_fast   = close.ewm(span=fast,   adjust=False).mean()
    ema_slow   = close.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line

    return pd.DataFrame({
        "MACD":      macd_line,
        "Signal":    signal_line,
        "Histogram": histogram,
    }, index=close.index)