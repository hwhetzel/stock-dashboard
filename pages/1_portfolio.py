import streamlit as st
import pandas as pd
from datetime import date
from database import (
    initialize_db,
    add_transaction,
    get_transactions,
    delete_transaction, 
    update_transaction,
) 
from data import get_bulk_current_prices

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Portfolio", layout="wide")
initialize_db()

st.title("Portfolio")

# ── Helpers ───────────────────────────────────────────────────────────────────

def compute_holdings(transactions: list[dict]) -> pd.DataFrame:
    """
    Derive current holdings from the full transaction list.

    For each ticker we track:
    - shares_held       : net shares still owned
    - avg_cost          : average cost basis of remaining shares (FIFO-lite:
                          we recalculate avg cost on every buy, and reduce
                          cost basis proportionally on sells)
    - total_invested    : cumulative cash put in (buys only)
    - realized_gl       : gain/loss already locked in from sell transactions
    """
    # Group transactions by ticker, sorted oldest → newest
    by_ticker: dict[str, list[dict]] = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)

    rows = []
    for ticker, txs in by_ticker.items():
        shares_held   = 0.0
        cost_basis    = 0.0   # total cost of currently held shares
        realized_gl   = 0.0

        for tx in txs:
            if tx["type"] == "buy":
                cost_basis  += tx["shares"] * tx["price"]
                shares_held += tx["shares"]
            elif tx["type"] == "sell" and shares_held > 0:
                # Avg cost of held shares before this sell
                avg_before   = cost_basis / shares_held
                sell_shares  = min(tx["shares"], shares_held)  # can't sell more than held
                realized_gl += sell_shares * (tx["price"] - avg_before)
                cost_basis  -= sell_shares * avg_before
                shares_held -= sell_shares

        if shares_held > 0.0001:   # ignore dust (floating point remnants)
            rows.append({
                "Ticker":       ticker,
                "Shares":       round(shares_held, 6),
                "Avg Cost":     round(cost_basis / shares_held, 4),
                "Cost Basis":   round(cost_basis, 2),
                "Realized G/L": round(realized_gl, 2),
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Ticker", "Shares", "Avg Cost", "Cost Basis", "Realized G/L"]
    )


def enrich_with_market_data(holdings: pd.DataFrame) -> pd.DataFrame:
    """Add live price, market value, and unrealized G/L to the holdings table."""
    if holdings.empty:
        return holdings

    tickers = holdings["Ticker"].tolist()
    prices  = get_bulk_current_prices(tickers)

    holdings = holdings.copy()
    holdings["Current Price"]    = holdings["Ticker"].map(prices)
    holdings["Market Value"]     = (holdings["Shares"] * holdings["Current Price"]).round(2)
    holdings["Unrealized G/L"]   = (holdings["Market Value"] - holdings["Cost Basis"]).round(2)
    holdings["Unrealized G/L %"] = (
        (holdings["Unrealized G/L"] / holdings["Cost Basis"]) * 100
    ).round(2)

    return holdings


def color_value(val):
    """Green for positive, red for negative — used in DataFrame styling."""
    if pd.isna(val):
        return ""
    color = "green" if val >= 0 else "red"
    return f"color: {color}"


# ── Holdings table ────────────────────────────────────────────────────────────

st.subheader("Current Holdings")

all_transactions = get_transactions()
holdings         = compute_holdings(all_transactions)
holdings         = enrich_with_market_data(holdings)

if holdings.empty:
    st.info("No holdings yet. Add your first transaction below.")
else:
    # Summary metrics across the whole portfolio
    total_value     = holdings["Market Value"].sum()
    total_cost      = holdings["Cost Basis"].sum()
    total_unrealized = holdings["Unrealized G/L"].sum()
    total_realized  = holdings["Realized G/L"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio Value",   f"${total_value:,.2f}")
    c2.metric("Total Cost Basis",  f"${total_cost:,.2f}")
    c3.metric(
        "Unrealized G/L",
        f"${total_unrealized:,.2f}",
        delta=f"{(total_unrealized/total_cost*100):.2f}%" if total_cost else None,
    )
    c4.metric("Realized G/L", f"${total_realized:,.2f}")

    st.divider()

    # Style G/L columns
    styled = holdings.style.applymap(
        color_value, subset=["Unrealized G/L", "Unrealized G/L %", "Realized G/L"]
    ).format({
        "Shares":           "{:.4f}",
        "Avg Cost":         "${:.2f}",
        "Cost Basis":       "${:.2f}",
        "Current Price":    "${:.2f}",
        "Market Value":     "${:.2f}",
        "Unrealized G/L":   "${:.2f}",
        "Unrealized G/L %": "{:.2f}%",
        "Realized G/L":     "${:.2f}",
    }, na_rep="N/A")

    st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Per-holding transaction detail ────────────────────────────────────────────

if not holdings.empty:
    st.divider()
    st.subheader("Transaction Detail by Holding")

    selected_ticker = st.selectbox(
        "Select ticker to view transactions",
        options=sorted(holdings["Ticker"].tolist()),
    )

    ticker_txs = get_transactions(ticker=selected_ticker)
    if ticker_txs:
        tx_df = pd.DataFrame(ticker_txs)
        tx_df = tx_df[["id", "date", "type", "shares", "price", "notes"]]
        tx_df.columns = ["ID", "Date", "Type", "Shares", "Price", "Notes"]
        tx_df["Price"] = tx_df["Price"].map("${:.2f}".format)
        st.dataframe(tx_df, use_container_width=True, hide_index=True)

# ── Add transaction form ──────────────────────────────────────────────────────

st.divider()
st.subheader("Add Transaction")

with st.form("add_tx_form", clear_on_submit=True):
    col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 2])

    ticker_input = col1.text_input("Ticker", placeholder="e.g. AAPL").upper().strip()
    tx_type      = col2.selectbox("Type", ["buy", "sell"])
    shares_input = col3.number_input("Shares", min_value=0.0001, step=0.01, format="%.4f")
    price_input  = col4.number_input("Price per Share", min_value=0.01, step=0.01, format="%.2f")
    date_input   = col5.date_input("Date", value=date.today())
    notes_input  = st.text_input("Notes (optional)", placeholder="e.g. dividend reinvestment")

    submitted = st.form_submit_button("Add Transaction")
    if submitted:
        if not ticker_input:
            st.error("Ticker is required.")
        else:
            add_transaction(
                ticker=ticker_input,
                type_=tx_type,
                shares=shares_input,
                price=price_input,
                date=date_input.strftime("%Y-%m-%d"),
                notes=notes_input,
            )
            st.success(f"Added {tx_type} of {shares_input} shares of {ticker_input}.")
            st.rerun()

# ── Edit / delete transaction ─────────────────────────────────────────────────

st.divider()
st.subheader("Edit / Delete a Transaction")

if not all_transactions:
    st.info("No transactions to edit yet.")
else:
    tx_df_all = pd.DataFrame(all_transactions)

    # Build a readable label for the selectbox
    tx_df_all["label"] = tx_df_all.apply(
        lambda r: f"[{r['id']}] {r['date']} — {r['type'].upper()} "
                  f"{r['shares']} {r['ticker']} @ ${r['price']:.2f}",
        axis=1,
    )

    selected_label = st.selectbox("Select transaction", tx_df_all["label"].tolist())
    selected_row   = tx_df_all[tx_df_all["label"] == selected_label].iloc[0]
    tx_id          = int(selected_row["id"])

    with st.form("edit_tx_form"):
        col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 2])

        e_ticker = col1.text_input("Ticker", value=selected_row["ticker"])
        e_type   = col2.selectbox(
            "Type", ["buy", "sell"],
            index=0 if selected_row["type"] == "buy" else 1
        )
        e_shares = col3.number_input(
            "Shares", min_value=0.0001, value=float(selected_row["shares"]),
            step=0.01, format="%.4f"
        )
        e_price  = col4.number_input(
            "Price", min_value=0.01, value=float(selected_row["price"]),
            step=0.01, format="%.2f"
        )
        e_date   = col5.date_input(
            "Date", value=pd.to_datetime(selected_row["date"]).date()
        )
        e_notes  = st.text_input("Notes", value=selected_row["notes"] or "")

        edit_col, del_col = st.columns([1, 1])
        save_btn   = edit_col.form_submit_button("Save Changes")
        delete_btn = del_col.form_submit_button("Delete Transaction", type="primary")

        if save_btn:
            update_transaction(
                tx_id, e_ticker.upper().strip(), e_type,
                e_shares, e_price, e_date.strftime("%Y-%m-%d"), e_notes
            )
            st.success("Transaction updated.")
            st.rerun()

        if delete_btn:
            delete_transaction(tx_id)
            st.success("Transaction deleted.")
            st.rerun()