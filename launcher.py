import subprocess
import threading
import time
import sys
import os
import webview

# ── Config ────────────────────────────────────────────────────────────────────

PORT = 8501
URL = f"http://localhost:{PORT}"
APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Home.py")

streamlit_process = None
_stop_monitor = threading.Event()


def start_streamlit():
    """Launch Streamlit as a subprocess, suppressing its console output."""
    global streamlit_process
    kwargs = {}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si

    streamlit_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP,
         "--server.port", str(PORT),
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def wait_for_streamlit(timeout: int = 30):
    """Poll localhost until Streamlit is responding."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def background_price_monitor():
    """
    Background thread that checks prices against notification thresholds.
    Runs independently of Streamlit — works even when app is minimized.
    Stops cleanly when _stop_monitor is set (app closes).
    """
    # Wait for Streamlit and DB to be ready before first check
    time.sleep(15)

    while not _stop_monitor.is_set():
        try:
            from utils.price_monitor import run_background_checks, fire_alerts
            alerts = run_background_checks()
            if alerts:
                fire_alerts(alerts)
        except Exception:
            pass

        # Sleep in small increments so we can respond to stop signal quickly
        check_interval_mins = 5.0
        try:
            # Read interval from DB each cycle so settings changes take effect
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from database import get_setting
            check_interval_mins = float(str(get_setting("price_check_interval_mins", "5")))
        except Exception:
            pass

        # Sleep in 5-second chunks so stop signal is picked up quickly
        elapsed = 0.0
        interval_secs = check_interval_mins * 60
        while elapsed < interval_secs and not _stop_monitor.is_set():
            time.sleep(5)
            elapsed += 5


def main():
    # Start Streamlit in background thread
    streamlit_thread = threading.Thread(target=start_streamlit, daemon=True)
    streamlit_thread.start()

    # Wait until the server is up
    ready = wait_for_streamlit(timeout=30)
    if not ready:
        print("Streamlit failed to start within 30 seconds.")
        sys.exit(1)

    # Start background price monitor thread
    monitor_thread = threading.Thread(target=background_price_monitor, daemon=True)
    monitor_thread.start()

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

    # Webview window closed — stop monitor and kill Streamlit
    _stop_monitor.set()

    if streamlit_process is not None:
        streamlit_process.terminate()
        try:
            streamlit_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            streamlit_process.kill()

    sys.exit(0)


if __name__ == "__main__":
    main()