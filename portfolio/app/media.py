"""Image uploads. Every file is opened with Pillow (so only real images get through), turned the right way up,
resized, and saved again as WebP. Re-saving drops all metadata, including GPS position; the camera details worth
showing are read first and returned separately.
"""
from __future__ import annotations

import io
import secrets
from fractions import Fraction
from pathlib import Path

from PIL import ExifTags, Image, ImageOps

MAX_BYTES = 30 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 80_000_000
SIZES = {"photo": (3000, 90), "normal": (2000, 84)}       # longest edge, WebP quality
THUMB = (900, 80)


class BadImage(Exception):
    pass


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def read_exif(im: Image.Image) -> dict:
    out: dict = {}
    try:
        raw = im.getexif()
        tags = {ExifTags.TAGS.get(k, k): v for k, v in raw.items()}
        tags.update({ExifTags.TAGS.get(k, k): v for k, v in raw.get_ifd(ExifTags.IFD.Exif).items()})
    except Exception:
        return out
    make, model = str(tags.get("Make") or "").strip("\x00 "), str(tags.get("Model") or "").strip("\x00 ")
    if model:
        out["camera"] = model if make.split(" ")[0].lower() in model.lower() else f"{make} {model}".strip()
    if tags.get("LensModel"):
        out["lens"] = str(tags["LensModel"]).strip("\x00 ")
    bits = []
    if (v := _num(tags.get("FocalLength"))):
        bits.append(f"{v:g}mm")
    if (v := _num(tags.get("FNumber"))):
        bits.append(f"f/{v:g}")
    if (v := _num(tags.get("ExposureTime"))):
        bits.append(f"1/{round(1 / v)}s" if v < 1 else f"{v:g}s")
    if (v := tags.get("ISOSpeedRatings")):
        bits.append(f"ISO {v[0] if isinstance(v, tuple) else v}")
    if bits:
        out["settings"] = ", ".join(bits)
    taken = str(tags.get("DateTimeOriginal") or "")
    if len(taken) >= 10 and taken[4] == ":":
        out["taken"] = taken[:10].replace(":", "-")
    return out


def store(raw: bytes, folder: Path, quality: str = "normal") -> dict:
    if len(raw) > MAX_BYTES:
        raise BadImage("That file is larger than 30 MB.")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception as e:
        raise BadImage("That file is not an image this site can read (use JPG, PNG, WebP or GIF).") from e
    exif = read_exif(im)
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") and "transparency" in im.info or im.mode == "RGBA" else "RGB")
    edge, q = SIZES.get(quality, SIZES["normal"])
    big = im.copy()
    big.thumbnail((edge, edge), Image.LANCZOS)
    small = im.copy()
    small.thumbnail((THUMB[0], THUMB[0]), Image.LANCZOS)
    folder.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(8)
    big.save(folder / f"{name}.webp", "WEBP", quality=q, method=5)
    small.save(folder / f"{name}_s.webp", "WEBP", quality=THUMB[1], method=5)
    return {"src": f"/media/{name}.webp", "thumb": f"/media/{name}_s.webp", "w": big.width, "h": big.height, "exif": exif}


def remove_unused(folder: Path, in_use: str, candidates: list[str]) -> None:
    """Delete uploaded files that no item refers to any more (called after an item is deleted or changed)."""
    for src in candidates:
        if src and src.startswith("/media/") and src not in in_use:
            for p in (folder / Path(src).name, folder / Path(src).name.replace(".webp", "_s.webp")):
                p.unlink(missing_ok=True)
