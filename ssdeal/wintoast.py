"""Real Windows toast notifications (Action Center), without extra packages.

Windows only shows a toast when the sender's AppUserModelID is registered. An unpackaged app registers it under
HKCU\\Software\\Classes\\AppUserModelId\\<id> (display name + icon); without that key Windows silently drops the toast,
which is why the earlier version never showed anything. The toast itself is raised through PowerShell's WinRT bridge
(built into Windows 10/11), with the XML passed base64-encoded so no title or price can break the command line.
"""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

AUMID = "SSDealFinder.App"
NO_WINDOW = 0x08000000


def register(icon_dir: Path | None = None) -> str:
    """Create/refresh the registry entry. Returns '' on success, else the reason."""
    if sys.platform != "win32":
        return "not Windows"
    try:
        import winreg  # type: ignore

        icon = ""
        if icon_dir is not None:
            icon = str(_icon(icon_dir) or "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{AUMID}") as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "SS Deal Finder")
            if icon:
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, icon)
            winreg.SetValueEx(k, "IconBackgroundColor", 0, winreg.REG_SZ, "FF1D4ED8")
            winreg.SetValueEx(k, "ShowInSettings", 0, winreg.REG_DWORD, 1)
        return ""
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def _icon(folder: Path) -> Path | None:
    p = folder / "toast-icon.png"
    if p.exists():
        return p
    try:
        from PIL import Image, ImageDraw  # type: ignore

        folder.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((4, 4, 92, 92), 20, fill=(29, 78, 216, 255))
        for x, top in ((26, 52), (46, 34), (66, 60)):
            d.rounded_rectangle((x - 5, top, x + 5, 74), 4, fill=(255, 255, 255, 255))
        d.rounded_rectangle((18, 72, 78, 80), 4, fill=(255, 255, 255, 255))
        img.save(p)
        return p
    except Exception:  # noqa: BLE001
        return None


def toast_xml(title: str, body: str, url: str | None = None, buttons: list[tuple[str, str]] | None = None,
              urgent: bool = False, attribution: str = "SS Deal Finder") -> str:
    acts = "".join(f"<action content={quoteattr(label[:40])} activationType=\"protocol\" arguments={quoteattr(link)}/>"
                   for label, link in (buttons or []) if link)
    launch = f" activationType=\"protocol\" launch={quoteattr(url)}" if url else ""
    # 'reminder' keeps an important toast on screen until it is dismissed (it needs at least one button)
    scenario = " scenario=\"reminder\"" if urgent and acts else ""
    audio = "<audio src=\"ms-winsoundevent:Notification.Reminder\"/>" if urgent else "<audio src=\"ms-winsoundevent:Notification.Default\"/>"
    return (f"<toast{launch}{scenario}><visual><binding template=\"ToastGeneric\"><text>{escape(title[:120])}</text>"
            f"<text>{escape(body[:400])}</text><text placement=\"attribution\">{escape(attribution)}</text></binding></visual>"
            + (f"<actions>{acts}</actions>" if acts else "") + audio + "</toast>")


def _script(xml: str) -> str:
    b64 = base64.b64encode(xml.encode("utf-8")).decode("ascii")
    return (
        "$ErrorActionPreference='Stop';"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] > $null;"
        "$d = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$d.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}')));"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{AUMID}').Show([Windows.UI.Notifications.ToastNotification]::new($d))"
    )


def show(title: str, body: str, url: str | None = None, buttons: list[tuple[str, str]] | None = None,
         urgent: bool = False, wait: bool = False) -> str:
    """Raise a toast. Returns '' when it was handed to Windows, else the error. wait=True reports PowerShell errors."""
    if sys.platform != "win32":
        return "Windows notifications only work on Windows"
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
           "-EncodedCommand", base64.b64encode(_script(toast_xml(title, body, url, buttons, urgent)).encode("utf-16-le")).decode("ascii")]
    try:
        if not wait:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
            return ""
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25, creationflags=NO_WINDOW)
        return "" if r.returncode == 0 else (r.stderr or r.stdout or f"PowerShell exit {r.returncode}").strip()[:400]
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
