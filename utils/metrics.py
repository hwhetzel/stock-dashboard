import pandas as pd
import numpy as np


def calculate_returns(price_series: pd.Series) -> pd.Series:
    """Return daily percentage returns from a price series."""
    return price_series.pct_change().dropna()


def calculate_total_return(price_series: pd.Series) -> float:
    """
    Total return % over the full period of the series.
    (end_price - start_price) / start_price * 100
    """
    if price_series.empty or len(price_series) < 2:
        return 0.0
    start = price_series.iloc[0]
    end   = price_series.iloc[-1]
    return ((end - start) / start) * 100 if start else 0.0


def calculate_annualized_return(price_series: pd.Series) -> float:
    """
    Annualized return % using CAGR formula.
    Assumes daily price data with ~252 trading days/year.
    """
    if price_series.empty or len(price_series) < 2:
        return 0.0
    total_return = (price_series.iloc[-1] / price_series.iloc[0])
    num_days = (price_series.index[-1] - price_series.index[0]).days
    if num_days <= 0 or total_return <= 0:
        return 0.0
    years = num_days / 365.25
    cagr = (total_return ** (1 / years) - 1) * 100
    return cagr


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.04) -> float:
    """
    Annualized Sharpe Ratio.
    risk_free_rate is annual (default 4%, roughly current T-bill rate —
    update this manually if you want a more precise figure).
    Formula: (mean daily return - daily risk-free) / std daily return, annualized.
    """
    if returns.empty or returns.std() == 0:
        return 0.0

    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    sharpe = (excess_returns.mean() / returns.std()) * np.sqrt(252)
    return sharpe


def calculate_correlation_matrix(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a DataFrame of price series (columns = tickers), return the
    pairwise correlation matrix of daily returns.
    """
    returns_df = price_df.pct_change().dropna()
    return returns_df.corr()


def calculate_gain_loss(shares: float, avg_cost: float, current_price: float) -> dict:
    """
    Return unrealized gain/loss in dollars and percent for a single holding.
    """
    cost_basis  = shares * avg_cost
    market_value = shares * current_price
    gain_loss   = market_value - cost_basis
    gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis else 0.0

    return {
        "cost_basis":     cost_basis,
        "market_value":   market_value,
        "gain_loss":      gain_loss,
        "gain_loss_pct":  gain_loss_pct,
    }


def calculate_portfolio_value_over_time(
    transactions: list[dict],
    price_history: dict[str, pd.Series],
) -> pd.Series:
    """
    Reconstruct total portfolio market value for each date in the price history.

    transactions   : list of transaction dicts (ticker, type, shares, price, date)
    price_history  : {ticker: pd.Series of close prices indexed by date}

    Returns a pd.Series indexed by date -> total portfolio value.
    Used for benchmark comparison and total return over time.
    """
    if not transactions or not price_history:
        return pd.Series(dtype=float)

    # Build a unified date index across all price series
    all_dates = sorted(set().union(*[s.index for s in price_history.values()]))
    if not all_dates:
        return pd.Series(dtype=float)

    # Sort transactions chronologically
    sorted_tx = sorted(transactions, key=lambda x: x["date"])

    portfolio_values = []
    for current_date in all_dates:
        # Strip timezone from current_date so it's always tz-naive for comparison
        current_date_only = pd.Timestamp(current_date).tz_localize(None).normalize()

        # Compute shares held per ticker as of this date
        shares_as_of = {}
        for tx in sorted_tx:
            tx_date = pd.Timestamp(tx["date"]).tz_localize(None).normalize()
            if tx_date > current_date_only:
                continue
            ticker = tx["ticker"]
            shares_as_of.setdefault(ticker, 0.0)
            if tx["type"] == "buy":
                shares_as_of[ticker] += tx["shares"]
            elif tx["type"] == "sell":
                shares_as_of[ticker] -= tx["shares"]

        # Sum market value across tickers using closest available price
        total_value = 0.0
        for ticker, shares in shares_as_of.items():
            if shares <= 0 or ticker not in price_history:
                continue
            series = price_history[ticker]
            # Use the most recent price at or before current_date
            valid_prices = series[series.index <= current_date]
            if not valid_prices.empty:
                total_value += shares * valid_prices.iloc[-1]

        portfolio_values.append(total_value)

    return pd.Series(portfolio_values, index=pd.to_datetime(all_dates))


def normalize_to_100(series: pd.Series) -> pd.Series:
    """
    Rebase a price/value series to start at 100.
    Useful for comparing portfolio performance vs a benchmark on the same scale.
    """
    if series.empty or series.iloc[0] == 0:
        return series
    return (series / series.iloc[0]) * 100