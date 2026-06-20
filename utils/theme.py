import streamlit as st
from database import get_setting

def apply_theme():
    """
    Inject CSS to apply light or dark mode based on the stored setting.
    Call this at the top of every page after initialize_db().
    """
    theme = get_setting("theme", "Light")

    if theme == "Dark":
        css = """
        <style>
            .stApp { background-color: #0e1117; color: #fafafa; }
            .stSidebar { background-color: #1a1d23; }
            .stDataFrame { background-color: #1a1d23; }
            div[data-testid="metric-container"] {
                background-color: #1a1d23;
                border: 1px solid #2d3139;
                border-radius: 8px;
                padding: 12px;
            }
            .stExpander { border: 1px solid #2d3139; }
        </style>
        """
    else:
        css = """
        <style>
            .stApp { background-color: #ffffff; color: #31333f; }
            .stSidebar { background-color: #f0f2f6; color: #31333f; }
            .stSidebar * { color: #31333f; }
            p, h1, h2, h3, h4, h5, h6, li, span, label { color: #31333f; }

            /* Top toolbar bar */
            header[data-testid="stHeader"] {
                background-color: #ffffff;
            }

            /* Buttons */
            .stButton > button {
                background-color: #f0f2f6;
                color: #31333f;
                border: 1px solid #cccccc;
            }
            .stButton > button:hover {
                background-color: #e0e2e6;
                color: #31333f;
            }

            /* Form submit buttons */
            .stFormSubmitButton > button {
                background-color: #f0f2f6;
                color: #31333f;
                border: 1px solid #cccccc;
            }

            /* Selectbox, text input, number input */
            .stSelectbox > div, .stTextInput > div, .stNumberInput > div {
                background-color: #ffffff;
                color: #31333f;
            }

            div[data-testid="metric-container"] {
                background-color: #f0f2f6;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
            }
            .stExpander { border: 1px solid #e0e0e0; }
        </style>
        """

    st.markdown(css, unsafe_allow_html=True)