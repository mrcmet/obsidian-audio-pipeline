#!/usr/bin/env python3
"""
tray.py — Persistent system tray process that owns main.py as a subprocess.

Manages process lifecycle, auto-restart with backoff, and exposes a tray menu
for log viewing, settings, start/stop/restart, and quit.
"""

from __future__ import annotations

import sys
import os
import subprocess
import threading
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).parent.resolve()
_MAIN_PY = _BASE_DIR / "main.py"
_LOG_FILE = _BASE_DIR / "pipeline.log"
_ICON_IDLE = _BASE_DIR / "assets" / "icon.png"
_ICON_ACTIVE = _BASE_DIR / "assets" / "icon_active.png"

_MAX_RESTARTS = 3
_RESTART_WINDOW = 30.0   # seconds — resets restart counter if process lives this long
_POLL_INTERVAL = 5       # seconds between health checks


class _PipelineProcess:
    """Owns the main.py subprocess and tracks restart state."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._restart_count = 0
        self._start_time: float = 0.0
        self._user_stopped = False   # True when Stop was requested by user
        self._crashed = False        # True after exhausting restarts

    def start(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return
            self._user_stopped = False
            self._crashed = False
            self._launch()

    def stop(self) -> None:
        with self._lock:
            self._user_stopped = True
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            self._proc = None

    def restart(self) -> None:
        self.stop()
        with self._lock:
            self._restart_count = 0
            self._crashed = False
            self._user_stopped = False
            self._launch()

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def is_crashed(self) -> bool:
        return self._crashed

    def _launch(self) -> None:
        """Open the log file in append mode and start the subprocess. Must be called under lock."""
        log_fh = open(_LOG_FILE, "a", encoding="utf-8")
        self._proc = subprocess.Popen(
            [sys.executable, str(_MAIN_PY)],
            stdout=log_fh,
            stderr=log_fh,
            cwd=str(_BASE_DIR),
        )
        self._start_time = time.monotonic()
        logger.info("Pipeline started (pid=%d)", self._proc.pid)

    def check_and_maybe_restart(self) -> None:
        """Called by the health-check thread every _POLL_INTERVAL seconds."""
        with self._lock:
            if self._user_stopped or self._crashed or self._proc is None:
                return
            if self._proc.poll() is None:
                # Still running — check if we can reset restart counter.
                if time.monotonic() - self._start_time > _RESTART_WINDOW:
                    self._restart_count = 0
                return

            # Process has exited unexpectedly.
            exit_code = self._proc.returncode
            logger.warning("Pipeline exited (code=%d), restart_count=%d", exit_code, self._restart_count)

            if self._restart_count >= _MAX_RESTARTS:
                self._crashed = True
                logger.error("Pipeline crashed %d times — giving up. Restart manually.", _MAX_RESTARTS)
                return

            self._restart_count += 1
            self._launch()


def _read_last_log_line() -> str:
    """Return the last non-empty line of pipeline.log, or empty string."""
    if not _LOG_FILE.exists():
        return ""
    try:
        with open(_LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                return stripped[-120:]   # cap tooltip length
    except OSError:
        pass
    return ""


def _open_log_window_thread() -> None:
    import tkinter as tk
    import log_window
    root = tk.Tk()
    log_window.open_log_window(root)
    root.mainloop()


def _open_settings_window_thread() -> None:
    import tkinter as tk
    import settings_window
    root = tk.Tk()
    settings_window.open_settings_window(root)
    root.mainloop()


# ---------------------------------------------------------------------------
# Windows implementation (pystray)
# ---------------------------------------------------------------------------

def _run_windows(proc: _PipelineProcess) -> None:
    import pystray
    from PIL import Image

    def _load_icon(active: bool) -> Image.Image:
        path = _ICON_ACTIVE if active else _ICON_IDLE
        if path.exists():
            return Image.open(path)
        # Fallback: plain coloured square so pystray doesn't crash.
        img = Image.new("RGBA", (64, 64), "#1a7a6e")
        return img

    icon_ref: list[pystray.Icon] = []

    def _status_text() -> str:
        if proc.is_crashed():
            return "Crashed — restart manually"
        return "● Running" if proc.is_running() else "○ Stopped"

    def _rebuild_menu() -> pystray.Menu:
        running = proc.is_running()
        return pystray.Menu(
            pystray.MenuItem(_status_text(), None, enabled=False),
            pystray.MenuItem("Open Log", lambda icon, item: threading.Thread(
                target=_open_log_window_thread, daemon=True).start()),
            pystray.MenuItem("Settings", lambda icon, item: threading.Thread(
                target=_open_settings_window_thread, daemon=True).start()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Stop" if running else "Start",
                _on_toggle,
            ),
            pystray.MenuItem("Restart", lambda icon, item: proc.restart()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _on_quit),
        )

    def _on_toggle(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        if proc.is_running():
            proc.stop()
        else:
            proc.start()
        icon.menu = _rebuild_menu()

    def _on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        proc.stop()
        icon.stop()

    def _health_loop(icon: pystray.Icon) -> None:
        while True:
            time.sleep(_POLL_INTERVAL)
            proc.check_and_maybe_restart()
            running = proc.is_running()
            icon.icon = _load_icon(running)
            icon.title = _read_last_log_line() or _status_text()
            # Rebuild menu so Stop/Start label toggles.
            icon.menu = _rebuild_menu()

    proc.start()
    icon = pystray.Icon(
        "ObsidianAudioPipeline",
        _load_icon(proc.is_running()),
        title="Obsidian Audio Pipeline",
        menu=_rebuild_menu(),
    )
    icon_ref.append(icon)

    health_thread = threading.Thread(target=_health_loop, args=(icon,), daemon=True)
    health_thread.start()

    icon.run()


# ---------------------------------------------------------------------------
# Mac implementation (rumps)
# ---------------------------------------------------------------------------

def _run_mac(proc: _PipelineProcess) -> None:
    import rumps

    class TrayApp(rumps.App):
        def __init__(self) -> None:
            icon_path = str(_ICON_IDLE) if _ICON_IDLE.exists() else None
            super().__init__("Obsidian Audio Pipeline", icon=icon_path, quit_button=None)
            self._update_menu()
            proc.start()
            self._health_timer = rumps.Timer(self._on_tick, _POLL_INTERVAL)
            self._health_timer.start()

        def _status_text(self) -> str:
            if proc.is_crashed():
                return "Crashed — restart manually"
            return "● Running" if proc.is_running() else "○ Stopped"

        def _update_menu(self) -> None:
            running = proc.is_running()
            self.menu.clear()
            self.menu = [
                rumps.MenuItem(self._status_text(), callback=None),
                rumps.MenuItem("Open Log", callback=self._on_open_log),
                rumps.MenuItem("Settings", callback=self._on_settings),
                None,  # separator
                rumps.MenuItem("Stop" if running else "Start", callback=self._on_toggle),
                rumps.MenuItem("Restart", callback=self._on_restart),
                None,
                rumps.MenuItem("Quit", callback=self._on_quit),
            ]

        @rumps.clicked("Open Log")
        def _on_open_log(self, _: rumps.MenuItem) -> None:
            threading.Thread(target=_open_log_window_thread, daemon=True).start()

        @rumps.clicked("Settings")
        def _on_settings(self, _: rumps.MenuItem) -> None:
            threading.Thread(target=_open_settings_window_thread, daemon=True).start()

        def _on_toggle(self, sender: rumps.MenuItem) -> None:
            if proc.is_running():
                proc.stop()
            else:
                proc.start()
            self._update_menu()

        def _on_restart(self, _: rumps.MenuItem) -> None:
            proc.restart()
            self._update_menu()

        def _on_quit(self, _: rumps.MenuItem) -> None:
            proc.stop()
            rumps.quit_application()

        def _on_tick(self, _: rumps.Timer) -> None:
            proc.check_and_maybe_restart()
            last_line = _read_last_log_line()
            if last_line:
                self.title = last_line
            self._update_menu()
            icon_path = str(_ICON_ACTIVE if proc.is_running() else _ICON_IDLE)
            if Path(icon_path).exists():
                self.icon = icon_path

    TrayApp().run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the tray app. Blocks until the user quits."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    proc = _PipelineProcess()

    if sys.platform == "win32":
        _run_windows(proc)
    elif sys.platform == "darwin":
        _run_mac(proc)
    else:
        print(f"Unsupported platform: {sys.platform}. Only win32 and darwin are supported.")
        sys.exit(1)


if __name__ == "__main__":
    main()
