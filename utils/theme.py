import streamlit as st


def apply_theme():
    """Inject minimal card styling for metric containers."""
    css = """
    <style>
        div[data-testid="stMetric"] {
            border: 1px solid #2d3139;
            border-radius: 10px;
            padding: 16px;
            background-color: #1a1d23;
            min-height: 140px;
        }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def html_table(rows: list[dict], theme: str = "") -> str:
    """
    Render a list of dicts as a styled HTML table.
    Works in both light and dark mode with Streamlit default theme.
    """
    if not rows:
        return "<p>No data.</p>"

    headers = list(rows[0].keys())

    header_html = "".join(
        f"<th style='padding:8px 12px;text-align:left;"
        f"border-bottom:2px solid #2d3139;font-size:0.85rem;'>"
        f"{h}</th>"
        for h in headers
    )

    rows_html = ""
    for i, row in enumerate(rows):
        cells = "".join(
            f"<td style='padding:8px 12px;"
            f"border-bottom:1px solid #2d3139;font-size:0.88rem;'>"
            f"{row.get(h, '')}</td>"
            for h in headers
        )
        rows_html += f"<tr>{cells}</tr>"

    return (
        f"<div style='border-radius:8px;overflow:hidden;"
        f"border:1px solid #2d3139;margin-bottom:8px;'>"
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table></div>"
    )

def show_notification_badge(count: int = -1):
    from database import get_unread_count
    if count == -1:
        count = get_unread_count()
    if count > 0:
        st.sidebar.markdown(
            f"""
            <div style="
                background-color: #e63946;
                color: white;
                border-radius: 12px;
                padding: 2px 10px;
                font-size: 0.8rem;
                font-weight: bold;
                display: inline-block;
                margin-top: 4px;
            ">
                🔔 {count} unread notification{'s' if count != 1 else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )