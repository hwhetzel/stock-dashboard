import subprocess
import threading
import time
import sys
import os
import webview

# ── Config ────────────────────────────────────────────────────────────────────

PORT    = 8501
URL     = f"http://localhost:{PORT}"
APP     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")


def start_streamlit():
    """Launch Streamlit as a subprocess, suppressing its console output."""
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP,
         "--server.port", str(PORT),
         "--server.headless", "true",       # don't open a browser tab
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_streamlit(timeout: int = 30):
    """
    Poll localhost until Streamlit is responding.
    Gives the subprocess time to boot before webview opens.
    """
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    # Start Streamlit in background thread
    thread = threading.Thread(target=start_streamlit, daemon=True)
    thread.start()

    # Wait until the server is up
    ready = wait_for_streamlit(timeout=30)
    if not ready:
        print("Streamlit failed to start within 30 seconds.")
        sys.exit(1)

    # Open in a native desktop window
    webview.create_window(
        title="Stock Dashboard",
        url=URL,
        width=1400,
        height=900,
        min_size=(900, 600),
        resizable=True,
    )
    webview.start()


if __name__ == "__main__":
    main()