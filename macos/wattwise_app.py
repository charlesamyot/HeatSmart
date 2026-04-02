#!/usr/bin/env python3
"""
WattWise — Native macOS Windowed App
Uses pywebview (WebKit/WKWebView) to render the FastAPI UI in a native window.
Architecture mirrors iOS WKWebView pattern for future portability.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# When running as .app bundle, __file__ resolves inside the .app — find the project root
if ".app" in APP_DIR:
    candidate = APP_DIR
    while ".app" in candidate and candidate != "/":
        candidate = os.path.dirname(candidate)
    APP_DIR = candidate

CONFIG_PATH = os.path.join(APP_DIR, "config", "menubar.json")
LOG_PATH = os.path.join(APP_DIR, "config", "server.log")
DEFAULT_PORT = 8000
PYTHON_PATH = "/usr/bin/python3"


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"port": DEFAULT_PORT}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def port_is_open(port, host="127.0.0.1", timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError):
        return False


class WattWiseServer:
    """Manages the FastAPI/uvicorn backend process."""

    def __init__(self, port):
        self.port = port
        self.process = None

    def start(self):
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = APP_DIR

        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        log_file = open(LOG_PATH, "w")

        cmd = [
            PYTHON_PATH, "-m", "uvicorn",
            "src.backend.main:app",
            "--host", "127.0.0.1",
            "--port", str(self.port),
        ]

        self.process = subprocess.Popen(
            cmd, cwd=APP_DIR, env=env,
            stdout=log_file, stderr=subprocess.STDOUT,
        )

        # Wait for server to be ready (up to 20s)
        for _ in range(40):
            time.sleep(0.5)
            if self.process.poll() is not None:
                return False
            if port_is_open(self.port):
                return True
        return False

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    @property
    def url(self):
        return f"http://localhost:{self.port}"


class WattWiseBridge:
    """JavaScript API bridge — exposed to the webview as `window.pybridge`.

    This pattern maps directly to iOS WKScriptMessageHandler,
    making future Swift/UIKit port straightforward.
    """

    def __init__(self, window, server, config):
        self._window = window
        self._server = server
        self._config = config

    def get_app_version(self):
        return "1.1.0"

    def get_port(self):
        return self._server.port

    def restart_server(self):
        self._server.stop()
        ok = self._server.start()
        return {"success": ok}

    def get_config(self):
        return self._config

    def save_config(self, cfg):
        self._config.update(cfg)
        save_config(self._config)
        return {"success": True}

    def quit_app(self):
        self._server.stop()
        self._window.destroy()


def main():
    import webview

    # Set macOS process name so menu bar shows "WattWise" instead of "Python"
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info['CFBundleName'] = 'WattWise'
    except ImportError:
        pass  # Not available outside .app bundle or without PyObjC

    config = load_config()
    port = config.get("port", DEFAULT_PORT)

    server = WattWiseServer(port)

    # Start server in background thread
    server_ready = threading.Event()
    server_ok = [False]

    def boot_server():
        server_ok[0] = server.start()
        server_ready.set()

    threading.Thread(target=boot_server, daemon=True).start()

    # Create native window immediately (shows loading state)
    bridge = WattWiseBridge(None, server, config)

    window = webview.create_window(
        title="WattWise",
        url=f"http://localhost:{port}",
        width=1100,
        height=750,
        min_size=(800, 500),
        text_select=False,
        confirm_close=False,
        js_api=bridge,
    )

    bridge._window = window

    def on_loaded():
        """Called when the webview finishes loading a page."""
        window.evaluate_js("""
            window.isNativeApp = true;
            window.appVersion = '1.1.0';
        """)

    def on_closing():
        """Clean shutdown when the window is closed."""
        server.stop()

    window.events.loaded += on_loaded
    window.events.closing += on_closing

    # Start the webview event loop (blocks until window closes)
    webview.start(
        debug=os.environ.get("WATTWISE_DEBUG", "") == "1",
    )


if __name__ == "__main__":
    main()
