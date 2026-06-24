import streamlit as st
import pandas as pd
from datetime import date
from database import (
    initialize_db,
    add_transaction,
    get_transactions,
    delete_transaction,
    update_transaction,
    get_known_accounts,
    get_setting,
)
from data import get_bulk_current_prices
from utils.csv_parser import parse_unrealized_gl_csv, apply_csv_import

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Portfolio", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

st.title("Portfolio")

# ── Helpers ───────────────────────────────────────────────────────────────────

def compute_holdings(transactions: list[dict]) -> pd.DataFrame:
    """
    Derive current holdings from the full transaction list.
    Also tracks which accounts hold each ticker (for the dynamic Account column).
    """
    by_ticker: dict[str, list[dict]] = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)

    rows = []
    for ticker, txs in by_ticker.items():
        shares_held = 0.0
        cost_basis = 0.0
        realized_gl = 0.0
        accounts = set()

        for tx in txs:
            if tx.get("account"):
                accounts.add(tx["account"])
            if tx["type"] == "buy":
                cost_basis += tx["shares"] * tx["price"]
                shares_held += tx["shares"]
            elif tx["type"] == "sell" and shares_held > 0:
                avg_before = cost_basis / shares_held
                sell_shares = min(tx["shares"], shares_held)
                realized_gl += sell_shares * (tx["price"] - avg_before)
                cost_basis -= sell_shares * avg_before
                shares_held -= sell_shares

        if shares_held > 0.0001:
            rows.append({
                "Ticker": ticker,
                "Shares": round(shares_held, 6),
                "Avg Cost": round(cost_basis / shares_held, 4),
                "Cost Basis": round(cost_basis, 2),
                "Realized G/L": round(realized_gl, 2),
                # Store accounts as comma-separated string for display
                "_accounts": ", ".join(sorted(accounts)) if accounts else "",
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Ticker", "Shares", "Avg Cost", "Cost Basis", "Realized G/L", "_accounts"]
    )


def enrich_with_market_data(holdings: pd.DataFrame) -> pd.DataFrame:
    """Add live price, market value, and unrealized G/L to the holdings table."""
    if holdings.empty:
        return holdings

    tickers = holdings["Ticker"].tolist()
    prices = get_bulk_current_prices(tickers)

    holdings = holdings.copy()
    holdings["Current Price"] = holdings["Ticker"].map(prices)
    holdings["Market Value"] = (holdings["Shares"] * holdings["Current Price"]).round(2)
    holdings["Unrealized G/L"] = (holdings["Market Value"] - holdings["Cost Basis"]).round(2)
    holdings["Unrealized G/L %"] = (
        (holdings["Unrealized G/L"] / holdings["Cost Basis"]) * 100
    ).round(2)

    return holdings


def color_value(val: object) -> str:
    try:
        color = "green" if float(val) >= 0 else "red"  # type: ignore[arg-type]
        return f"color: {color}"
    except (TypeError, ValueError):
        return ""


def show_holdings_table(holdings: pd.DataFrame, show_account_col: bool):
    """Render the styled holdings dataframe, conditionally showing Account column."""
    display = holdings.copy()

    if show_account_col and "_accounts" in display.columns:
        display.insert(1, "Account", display["_accounts"])

    # Drop internal column before display
    display = display.drop(columns=["_accounts"], errors="ignore")

    format_map = {
        "Shares": "{:.4f}",
        "Avg Cost": "${:.2f}",
        "Cost Basis": "${:.2f}",
        "Current Price": "${:.2f}",
        "Market Value": "${:.2f}",
        "Unrealized G/L": "${:.2f}",
        "Unrealized G/L %": "{:.2f}%",
        "Realized G/L": "${:.2f}",
    }
    gl_cols = [c for c in ["Unrealized G/L", "Unrealized G/L %", "Realized G/L"] if c in display.columns]

    styled = display.style.map(color_value, subset=gl_cols).format(  # type: ignore[call-overload]
    {k: v for k, v in format_map.items() if k in display.columns},
    na_rep="N/A",
)
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Determine if Account column should be shown ───────────────────────────────
# Uses the has_multiple_accounts setting written by the CSV parser.
# Also checks manually entered transactions with account values.

_multi_setting = get_setting("has_multiple_accounts", "false")
_known_accounts = get_known_accounts()
show_account_col = (_multi_setting == "true") or (len(_known_accounts) > 1)

# ── CSV Import ────────────────────────────────────────────────────────────────

# Track whether to keep the expander open
if "csv_expander_open" not in st.session_state:
    st.session_state.csv_expander_open = False

st.subheader("Import from Ameriprise CSV")

with st.expander("Import Unrealized Gain/Loss CSV", expanded=st.session_state.csv_expander_open):
    uploaded_file = st.file_uploader(
        "Upload your Ameriprise Unrealized Gain/Loss CSV",
        type=["csv"],
        key=st.session_state.get("csv_uploader_key", "csv_upload"),
    )

    if uploaded_file is not None:
        try:
            positions = parse_unrealized_gl_csv(uploaded_file)

            if not positions:
                st.error("No valid positions found in the file. Check that you uploaded the Unrealized Gain/Loss export.")
            else:
                preview_df = pd.DataFrame(positions)
                preview_df = preview_df.rename(columns={
                    "symbol": "Ticker",
                    "quantity": "Shares",
                    "unit_price": "Avg Unit Cost",
                    "cost_basis": "Total Cost Basis",
                    "open_date": "Open Date",
                    "account": "Account",
                })
                display_cols = [c for c in ["Ticker", "Account", "Shares", "Avg Unit Cost", "Total Cost Basis", "Open Date"] if c in preview_df.columns]
                st.write(f"**{len(positions)} positions found** — preview:")
                st.dataframe(preview_df[display_cols], use_container_width=True, hide_index=True)

                st.warning(
                    "Importing will **replace all previous CSV-imported transactions** "
                    "and re-import from this file. Manually entered transactions are not affected."
                )

                if st.button("Confirm Import", type="primary", key="confirm_import"):
                    summary = apply_csv_import(positions)

                    # Close expander and reset uploader on next rerun
                    st.session_state.csv_expander_open = False
                    st.session_state.csv_uploader_key = f"csv_upload_{summary['date']}_{summary['total_positions']}"

                    st.success(f"Imported {summary['total_positions']} positions.")

                    if summary["added"]:
                        st.info(f"**New positions:** {', '.join(summary['added'])}")
                    if summary["removed"]:
                        st.info(f"**Positions closed:** {', '.join(summary['removed'])}")
                    if summary["changed"]:
                        for c in summary["changed"]:
                            diff = c["share_diff"]
                            direction = "▲" if diff > 0 else "▼"
                            st.info(
                                f"**{c['symbol']}** shares changed: "
                                f"{c['old_shares']} → {c['new_shares']} "
                                f"({direction}{abs(diff):.4f})"
                            )
                    if summary["moved_from_watchlist"]:
                        st.info(
                            f"**Removed from watchlist** (now in portfolio): "
                            f"{', '.join(summary['moved_from_watchlist'])}"
                        )
                    if not any([summary["added"], summary["removed"], summary["changed"]]):
                        st.info("No changes detected since last import.")

                    st.rerun()

        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")
    else:
        # Reset expander open state when no file is uploaded
        st.session_state.csv_expander_open = False

# ── Holdings table ────────────────────────────────────────────────────────────

st.divider()
st.subheader("Current Holdings")

all_transactions = get_transactions()
holdings = compute_holdings(all_transactions)
holdings = enrich_with_market_data(holdings)

if holdings.empty:
    st.info("No holdings yet. Add your first transaction below or import a CSV.")
else:
    total_value = holdings["Market Value"].sum()
    total_cost = holdings["Cost Basis"].sum()
    total_unrealized = holdings["Unrealized G/L"].sum()
    total_realized = holdings["Realized G/L"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio Value", f"${total_value:,.2f}")
    c2.metric("Total Cost Basis", f"${total_cost:,.2f}")
    c3.metric(
        "Unrealized G/L",
        f"${total_unrealized:,.2f}",
        delta=f"{(total_unrealized/total_cost*100):.2f}%" if total_cost else None,
    )
    c4.metric("Realized G/L", f"${total_realized:,.2f}")

    st.divider()
    show_holdings_table(holdings, show_account_col)

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
        cols = ["id", "date", "type", "shares", "price", "account", "notes", "source"]
        cols = [c for c in cols if c in tx_df.columns]
        tx_df = tx_df[cols]
        tx_df.columns = [c.title() for c in cols]
        if "Price" in tx_df.columns:
            tx_df["Price"] = tx_df["Price"].map("${:.2f}".format)
        st.dataframe(tx_df, use_container_width=True, hide_index=True)

# ── Add transaction form ──────────────────────────────────────────────────────

st.divider()
st.subheader("Add Transaction")

# Build account options: known accounts from DB + blank option
known_accounts = get_known_accounts()
account_options = ["(none)"] + known_accounts

with st.form("add_tx_form", clear_on_submit=True):
    col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 2])

    ticker_input = col1.text_input("Ticker", placeholder="e.g. AAPL").upper().strip()
    tx_type = col2.selectbox("Type", ["buy", "sell"])
    shares_input = col3.number_input("Shares", min_value=0.001, step=0.01, format="%.4f")
    price_input = col4.number_input("Price per Share", min_value=0.01, step=0.01, format="%.2f")
    date_input = col5.date_input("Date", value=date.today())

    acct_col, notes_col = st.columns([1, 2])
    # Dropdown shows known accounts; user can also type a new one below
    acct_select = acct_col.selectbox("Account (optional)", account_options)
    acct_custom = acct_col.text_input("Or type New Account Name", placeholder="e.g. Roth IRA")
    notes_input = notes_col.text_input("Notes (optional)", placeholder="e.g. dividend reinvestment")

    submitted = st.form_submit_button("Add Transaction")
    if submitted:
        if not ticker_input:
            st.error("Ticker is required.")
        else:
            # Custom account name takes priority over dropdown selection
            account_val = acct_custom.strip() if acct_custom.strip() else (
                acct_select if acct_select != "(none)" else None
            )
            add_transaction(
                ticker=ticker_input,
                type_=tx_type,
                shares=shares_input,
                price=price_input,
                date=date_input.strftime("%Y-%m-%d"),
                notes=notes_input,
                account=account_val,
                source="manual",
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

    tx_df_all["label"] = tx_df_all.apply(
        lambda r: f"[{r['id']}] {r['date']} — {r['type'].upper()} "
                  f"{r['shares']} {r['ticker']} @ ${r['price']:.2f}",
        axis=1,
    )

    selected_label = st.selectbox("Select transaction", tx_df_all["label"].tolist())
    selected_row = tx_df_all[tx_df_all["label"] == selected_label].iloc[0]
    tx_id = int(selected_row["id"])

    with st.form("edit_tx_form"):
        col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 2])

        e_ticker = col1.text_input("Ticker", value=selected_row["ticker"])
        e_type = col2.selectbox(
            "Type", ["buy", "sell"],
            index=0 if selected_row["type"] == "buy" else 1
        )
        e_shares = col3.number_input(
            "Shares", min_value=0.0001, value=float(selected_row["shares"]),
            step=0.01, format="%.4f"
        )
        e_price = col4.number_input(
            "Price", min_value=0.01, value=float(selected_row["price"]),
            step=0.01, format="%.2f"
        )
        e_date = col5.date_input(
            "Date", value=pd.to_datetime(selected_row["date"]).date()
        )

        # Account field on edit form
        current_account = selected_row.get("account", "") or ""
        edit_acct_options = ["(none)"] + known_accounts
        edit_acct_idx = edit_acct_options.index(current_account) if current_account in edit_acct_options else 0
        e_acct_col, e_notes_col = st.columns([1, 2])
        e_account_select = e_acct_col.selectbox("Account", edit_acct_options, index=edit_acct_idx)
        e_account_custom = e_acct_col.text_input("Or type New Account Name", value="" if current_account in edit_acct_options else current_account)
        e_notes = e_notes_col.text_input("Notes", value=selected_row["notes"] or "")

        edit_col, del_col = st.columns([1, 1])
        save_btn = edit_col.form_submit_button("Save Changes")
        delete_btn = del_col.form_submit_button("Delete Transaction", type="primary")

        if save_btn:
            account_val = e_account_custom.strip() if e_account_custom.strip() else (
                e_account_select if e_account_select != "(none)" else None
            )
            update_transaction(
                tx_id, (e_ticker or "").upper().strip(), e_type,
                e_shares, e_price, e_date.strftime("%Y-%m-%d"), e_notes, account_val
            )
            st.success("Transaction updated.")
            st.rerun()

        if delete_btn:
            delete_transaction(tx_id)
            st.success("Transaction deleted.")
            st.rerun()