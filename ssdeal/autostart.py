"""Optional start with Windows (HKCU Run key → background monitoring service)."""
from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "SSDealFinderService"


def command() -> str:
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    interpreter = pyw if pyw.exists() else exe
    script = Path(__file__).resolve().parent.parent / "run_service.pyw"
    return f'"{interpreter}" "{script}"'


def status() -> dict:
    if sys.platform != "win32":
        return {"supported": False, "enabled": False, "note": "Automatic startup is available on Windows."}
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, VALUE)
            return {"supported": True, "enabled": True, "command": val}
    except FileNotFoundError:
        return {"supported": True, "enabled": False}


def set_enabled(enabled: bool) -> dict:
    if sys.platform != "win32":
        raise OSError("Automatic startup is only supported on Windows")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, VALUE)
            except FileNotFoundError:
                pass
    return status()
