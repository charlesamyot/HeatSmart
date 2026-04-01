#!/usr/bin/env python3
"""
HeatSmart — macOS Menu Bar App
Runs the FastAPI server in the background with a menu bar icon.
No Terminal window needed. Configurable port via Settings.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import rumps

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# When running as .app bundle, __file__ resolves inside the .app — find the project root
if ".app" in APP_DIR:
    # Walk up until we exit the .app directory
    candidate = APP_DIR
    while ".app" in candidate and candidate != "/":
        candidate = os.path.dirname(candidate)
    APP_DIR = candidate
CONFIG_PATH = os.path.join(APP_DIR, "config", "menubar.json")
DEFAULT_PORT = 7777
# Use system Python, not the bundled py2app Python
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


class HeatSmartApp(rumps.App):
    def __init__(self):
        super().__init__(
            "HeatSmart",
            icon=None,
            title="🔥",
            quit_button=None,
        )
        self.config = load_config()
        self.port = self.config.get("port", DEFAULT_PORT)
        self.server_process = None
        self.server_running = False

        self.status_item = rumps.MenuItem(f"Server: Starting on port {self.port}...")
        self.menu = [
            rumps.MenuItem("HeatSmart v1.0", callback=None),
            None,
            rumps.MenuItem("Open HeatSmart", callback=self.open_app),
            rumps.MenuItem("Open Dashboard", callback=self.open_dashboard),
            None,
            self.status_item,
            rumps.MenuItem("Restart Server", callback=self.restart_server),
            None,
            rumps.MenuItem("Settings...", callback=self.open_settings),
            None,
            rumps.MenuItem("Quit HeatSmart", callback=self.quit_app),
        ]

        threading.Thread(target=self.start_server, daemon=True).start()

    @property
    def url(self):
        return f"http://localhost:{self.port}"

    def start_server(self, open_browser=True):
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        self.server_process = subprocess.Popen(
            [
                PYTHON_PATH, "-m", "uvicorn",
                "src.backend.main:app",
                "--host", "127.0.0.1",
                "--port", str(self.port),
            ],
            cwd=APP_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Wait for the server to actually be ready (up to 15 seconds)
        self.status_item.title = f"Server: Starting on port {self.port}..."
        for _ in range(30):
            time.sleep(0.5)
            if self._port_is_open():
                break

        if self._port_is_open():
            self.server_running = True
            self.status_item.title = f"Server: Running on port {self.port}"
            self.title = "🔥"
            if open_browser:
                webbrowser.open(self.url)
        else:
            self.status_item.title = "Server: Failed to start"
            self.title = "🔥⚠️"
            return

        # Wait for process to exit (blocks this thread)
        self.server_process.wait()
        self.server_running = False
        self.status_item.title = "Server: Stopped"
        self.title = "🔥⚠️"

    def _port_is_open(self):
        """Check if the server is accepting connections."""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError):
            return False

    def stop_server(self):
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        self.server_running = False

    def open_app(self, _):
        """Open the main app page in the default browser."""
        if self.server_running:
            webbrowser.open(self.url)
        else:
            rumps.alert("Server Not Running", "The server is not running. Try restarting.")

    def open_dashboard(self, _):
        if self.server_running:
            webbrowser.open(f"{self.url}/dashboard")
        else:
            rumps.alert("Server Not Running", "The server is not running. Try restarting.")

    def restart_server(self, _, open_browser=False):
        self.status_item.title = "Server: Restarting..."
        self.title = "🔥"
        self.stop_server()
        threading.Thread(target=lambda: self.start_server(open_browser=open_browser), daemon=True).start()

    def open_settings(self, _):
        response = rumps.Window(
            title="HeatSmart Settings",
            message=f"Server port (current: {self.port}).\nChange requires restart.",
            default_text=str(self.port),
            ok="Save & Restart",
            cancel="Cancel",
            dimensions=(200, 24),
        ).run()

        if response.clicked:
            try:
                new_port = int(response.text.strip())
                if 1024 <= new_port <= 65535:
                    self.port = new_port
                    self.config["port"] = new_port
                    save_config(self.config)
                    self.restart_server(None)
                else:
                    rumps.alert("Invalid Port", "Port must be between 1024 and 65535.")
            except ValueError:
                rumps.alert("Invalid Port", "Please enter a valid number.")

    def quit_app(self, _):
        self.stop_server()
        rumps.quit_application()


if __name__ == "__main__":
    HeatSmartApp().run()
