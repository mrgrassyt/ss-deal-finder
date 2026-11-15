"""Content drops: items added to portfolio/content/*.json (with pictures in content/images/) are imported once per key.

After an item has been imported it belongs to the dashboard. Editing or deleting it there is never undone by an update,
because the key is remembered. Each file is a list of {"key", "type", "published", "images": {field: file or [files]}, "data": {...}}.
An entry with "update": "<slug>" changes the named fields of an item that already exists (also once).
A drop of type "settings" changes only the site settings it names (it is applied once, like the rest).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import media
from .schema import TYPES, clean, clean_settings


def run(db, media_dir: Path, content_dir: Path) -> list[str]:
    done = set(db.kv("imported") or [])
    added: list[str] = []
    for f in sorted(content_dir.glob("*.json")):
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            print(f"content drop {f.name}: not valid JSON ({e})", flush=True)
            continue
        for e in entries:
            key, t = e.get("key"), e.get("type")
            if t == "settings" and key and key not in done:      # {"key", "type": "settings", "data": {fields to change}}
                values, bad = clean_settings({**(db.kv("site") or {}), **(e.get("data") or {})})
                if bad:
                    print(f"content drop {key}: {bad}", flush=True)
                    continue
                db.set_kv("site", values)
                done.add(key)
                added.append(key)
                continue
            if not key or key in done or t not in TYPES:
                continue
            data = dict(e.get("data") or {})
            try:
                for field, files in (e.get("images") or {}).items():
                    many = isinstance(files, list)
                    imgs = [media.store((content_dir / "images" / n).read_bytes(), media_dir, "photo" if t == "photo" else "normal") for n in (files if many else [files])]
                    data[field] = imgs if many else imgs[0]
            except (OSError, media.BadImage) as err:
                print(f"content drop {key}: {err}", flush=True)
                continue
            fields = TYPES[t]["fields"]
            target = None
            if e.get("update"):                                  # change an item that is already there, found by its slug
                target = db.one(t, e["update"])
                if not target:
                    print(f"content drop {key}: nothing with the address '{e['update']}' to update", flush=True)
                    continue
                data = {**target, **data}
            values, bad = clean(fields, data)
            if bad:
                print(f"content drop {key}: {bad}", flush=True)
                continue
            if target:
                db.save(t, values, id_=target["id"], published=bool(target.get("published", True)))
            else:
                db.save(t, values, published=bool(e.get("published", True)), created=e.get("created"))
            done.add(key)
            added.append(key)
    if added:
        db.set_kv("imported", sorted(done))
    return added
