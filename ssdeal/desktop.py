"""Desktop shell: a native window (pywebview / Edge WebView2 on Windows) around the
local UI, plus an optional tray icon. The monitoring service runs as a separate
background process, so closing this window does NOT stop monitoring.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from .config import Settings, data_dir

ROOT = Path(__file__).resolve().parent.parent


def service_url(demo: bool) -> str:
    s = Settings(data_dir() / "demo" if demo else data_dir())
    port = int(s.get("api.port", 8765)) + (1 if demo else 0)
    return f"http://127.0.0.1:{port}"


def is_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def start_service(demo: bool) -> None:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    interpreter = str(pyw if (sys.platform == "win32" and pyw.exists()) else exe)
    args = [interpreter, str(ROOT / "run_service.pyw")] + (["--demo"] if demo else [])
    kwargs: dict = {"cwd": str(ROOT), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x08000000 | 0x00000200  # DETACHED | NO_WINDOW | NEW_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)


def ensure_service(url: str, demo: bool, timeout: float = 45) -> bool:
    if is_up(url):
        return True
    start_service(demo)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_up(url):
            return True
        time.sleep(0.5)
    return False


def post(url: str) -> None:
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=b"{}", method="POST",
                                                      headers={"Content-Type": "application/json"}), timeout=3)
    except OSError:
        pass


def run_tray(url: str, on_open, on_quit) -> None:
    try:
        import pystray  # type: ignore
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError:
        return
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, 60, 60), 14, fill=(34, 197, 94, 255))
    d.text((18, 18), "SS", fill=(255, 255, 255, 255))
    menu = pystray.Menu(
        pystray.MenuItem("Open SS Deal Finder", lambda: on_open(), default=True),
        pystray.MenuItem("Pause scanning", lambda: post(url + "/api/scanner/pause")),
        pystray.MenuItem("Resume scanning", lambda: post(url + "/api/scanner/resume")),
        pystray.MenuItem("Close window (keep monitoring)", lambda: on_quit(False)),
        pystray.MenuItem("Stop monitoring service and quit", lambda: on_quit(True)),
    )
    icon = pystray.Icon("ssdeal", img, "SS Deal Finder", menu)
    threading.Thread(target=icon.run, daemon=True).start()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="SS Deal Finder desktop app")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--browser", action="store_true", help="open in the default browser instead of a window")
    args = ap.parse_args(argv)
    url = service_url(args.demo)
    if not ensure_service(url, args.demo):
        msg = f"The monitoring service did not start. See logs in {data_dir() / 'logs'}"
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, msg, "SS Deal Finder", 0x10)
        print(msg)
        return
    if args.browser:
        webbrowser.open(url)
        return
    try:
        import webview  # type: ignore
    except ImportError:
        # Fallback: Edge/Chrome "app mode" window, else the default browser
        for cand in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                     r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
            if os.path.exists(cand):
                subprocess.Popen([cand, f"--app={url}", "--window-size=1440,900"])
                return
        webbrowser.open(url)
        return
    state = {"window": None, "fullscreen": False}

    class Api:
        """Called from the page (Big Picture) as window.pywebview.api.set_fullscreen(true/false)."""
        def set_fullscreen(self, on):
            w = state["window"]
            if w is not None and bool(on) != state["fullscreen"]:
                w.toggle_fullscreen()
                state["fullscreen"] = bool(on)
            return state["fullscreen"]

    window = webview.create_window("SS Deal Finder", url, width=1440, height=920, min_size=(980, 640),
                                   background_color="#0b1020", js_api=Api())
    state["window"] = window

    def on_open():
        try:
            window.show()
            window.restore()
        except Exception:
            pass

    def on_quit(stop_service: bool):
        if stop_service:
            post(url + "/api/system/shutdown")
        try:
            window.destroy()
        except Exception:
            pass
        if stop_service:
            time.sleep(1)
        os._exit(0)

    def watch_service():
        """If the service is stopped (Quit button, tray, task manager), close the window and exit too."""
        down = 0
        while True:
            time.sleep(2)
            down = 0 if is_up(url) else down + 1
            if down >= 3:
                try:
                    window.destroy()
                except Exception:
                    pass
                time.sleep(1)
                os._exit(0)

    run_tray(url, on_open, on_quit)
    threading.Thread(target=watch_service, daemon=True).start()
    webview.start(private_mode=False, storage_path=str(data_dir() / "webview"))
    os._exit(0)     # window closed: the tray thread must not keep this process in Task Manager (the service keeps monitoring)


if __name__ == "__main__":
    main()
