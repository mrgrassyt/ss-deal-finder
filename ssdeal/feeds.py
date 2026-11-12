"""SS.lv electronics feeds (list pages) and the mapping to our own categories.

Only Latvian-language paths (/lv/...) are used: the /ru/ section mirrors the
same ads and /en/ is disallowed by robots.txt. Mid-level pages such as
/lv/electronics/computers/completing-pc/ list ads from all of their
sub-categories, which keeps the number of requests low.
"""
from __future__ import annotations

# Our categories. "key" values are stable identifiers used everywhere.
CATEGORIES: dict[str, dict] = {
    "camera":           {"name": "Cameras (DSLR / mirrorless / compact)", "group": "Photo", "value_floor": 40},
    "lens":             {"name": "Camera lenses", "group": "Photo", "value_floor": 30},
    "camera_accessory": {"name": "Camera accessories & bundles", "group": "Photo", "value_floor": 15},
    "film_camera":      {"name": "Film cameras", "group": "Photo", "value_floor": 20},
    "pc":               {"name": "Desktop PCs", "group": "Computers", "value_floor": 60},
    "laptop":           {"name": "Laptops & workstations", "group": "Computers", "value_floor": 60},
    "gpu":              {"name": "Graphics cards", "group": "PC parts", "value_floor": 25},
    "cpu":              {"name": "CPUs", "group": "PC parts", "value_floor": 15},
    "motherboard":      {"name": "Motherboards", "group": "PC parts", "value_floor": 20},
    "ram":              {"name": "RAM", "group": "PC parts", "value_floor": 10},
    "storage":          {"name": "SSDs & HDDs", "group": "PC parts", "value_floor": 10},
    "psu":              {"name": "Power supplies", "group": "PC parts", "value_floor": 15},
    "case_cooling":     {"name": "PC cases & cooling", "group": "PC parts", "value_floor": 15},
    "pc_parts_other":   {"name": "Other PC parts & cables", "group": "PC parts", "value_floor": 10},
    "monitor":          {"name": "Monitors", "group": "Computers", "value_floor": 30},
    "peripheral":       {"name": "Keyboards, mice & gaming peripherals", "group": "Computers", "value_floor": 10},
    "network":          {"name": "Network equipment", "group": "Computers", "value_floor": 10},
    "audio":            {"name": "Audio equipment", "group": "Audio/Video", "value_floor": 20},
    "headphones_mic":   {"name": "Headphones & microphones", "group": "Audio/Video", "value_floor": 15},
    "video":            {"name": "Video equipment", "group": "Audio/Video", "value_floor": 30},
    "tv":               {"name": "TVs & projectors", "group": "Audio/Video", "value_floor": 40},
    "console":          {"name": "Consoles & gaming", "group": "Gaming", "value_floor": 30},
    "phone":            {"name": "Phones", "group": "Mobile", "value_floor": 25},
    "tablet":           {"name": "Tablets", "group": "Mobile", "value_floor": 25},
    "wearable":         {"name": "Smartwatches & wearables", "group": "Mobile", "value_floor": 20},
    "drone":            {"name": "Drones & action cams", "group": "Photo", "value_floor": 40},
    "smart_home":       {"name": "Smart home, Arduino, Raspberry Pi", "group": "Other", "value_floor": 10},
    "other":            {"name": "Other electronics", "group": "Other", "value_floor": 15},
}

# feed key, ss.lv path, default category, priority (fast polling), enabled by default
_F = [
    # photo & optics
    ("photo_digital", "/lv/electronics/photo-optics/digital-cameras/", "camera", True, True),
    ("photo_slr", "/lv/electronics/photo-optics/slr-cameras/", "camera", True, True),
    ("photo_lenses", "/lv/electronics/photo-optics/objectives/", "lens", True, True),
    ("photo_film", "/lv/electronics/photo-optics/film-cameras/", "film_camera", False, True),
    ("photo_accessories", "/lv/electronics/photo-optics/accessories/", "camera_accessory", False, True),
    ("photo_flashes", "/lv/electronics/photo-optics/flashes-and-illumination/", "camera_accessory", False, True),
    ("photo_tripods", "/lv/electronics/photo-optics/supports-and-the-chassis/", "camera_accessory", False, True),
    ("photo_other", "/lv/electronics/photo-optics/other/", "camera_accessory", False, True),
    ("photo_bags", "/lv/electronics/photo-optics/bags/", "camera_accessory", False, False),
    ("photo_memory", "/lv/electronics/photo-optics/memory-for-digital-cameras/", "storage", False, False),
    ("photo_telescopes", "/lv/electronics/photo-optics/field-glasses-telescopes/", "other", False, False),
    # computers
    ("pc_desktops", "/lv/electronics/computers/pc/", "pc", True, True),
    ("pc_laptops", "/lv/electronics/computers/noutbooks/", "laptop", True, True),
    ("pc_parts", "/lv/electronics/computers/completing-pc/", "pc_parts_other", True, True),
    ("pc_notebook_parts", "/lv/electronics/computers/completing-notebook/", "pc_parts_other", False, True),
    ("pc_monitors", "/lv/electronics/computers/monitors/", "monitor", False, True),
    ("pc_consoles", "/lv/electronics/computers/game-consoles/", "console", True, True),
    ("pc_tablets", "/lv/electronics/computers/tablets/", "tablet", False, True),
    ("pc_accessories", "/lv/electronics/computers/accessories/", "peripheral", False, True),
    ("pc_multimedia", "/lv/electronics/computers/multimedia/", "audio", False, True),
    ("pc_network", "/lv/electronics/computers/hubs-switch-routers/", "network", False, True),
    ("pc_other", "/lv/electronics/computers/other/", "other", False, True),
    ("pc_games", "/lv/electronics/computers/games/", "console", False, False),
    ("pc_printers", "/lv/electronics/computers/printers-scanners-cartridges/", "other", False, False),
    # phones
    ("phones_mobile", "/lv/electronics/phones/mobile-phones/", "phone", True, True),
    ("phones_spares", "/lv/electronics/phones/spares-and-repair/", "phone", False, True),
    ("phones_other", "/lv/electronics/phones/other/", "phone", False, False),
    ("phones_accessories", "/lv/electronics/phones/accessories/", "other", False, False),
    # audio / video / tv
    ("av_audio", "/lv/electronics/audio-video-dvd-sat/audio/", "audio", False, True),
    ("av_video", "/lv/electronics/audio-video-dvd-sat/dvd-and-video-technics/", "video", False, True),
    ("tv_lcd", "/lv/electronics/tvs/lcd/", "tv", False, True),
    ("tv_led", "/lv/electronics/tvs/led/", "tv", False, True),
    ("tv_plasma", "/lv/electronics/tvs/plasmic/", "tv", False, False),
    ("tv_projectors", "/lv/electronics/tvs/projecting/", "tv", False, True),
    # other
    ("other_smart_home", "/lv/electronics/other/smart-house-arduino-raspberry-pi/", "smart_home", False, True),
    ("other_misc", "/lv/electronics/other/miscellaneous/", "other", False, True),
    ("other_psu_controllers", "/lv/electronics/other/adapters-drivers-controllers/", "other", False, False),
    ("other_cables", "/lv/electronics/other/cables-and-accessories/", "pc_parts_other", False, False),
    ("other_radio_parts", "/lv/electronics/other/radio-components-chips/", "other", False, False),
]

FEEDS: dict[str, dict] = {
    k: {"key": k, "path": p, "category": c, "priority": pr, "enabled_default": en}
    for k, p, c, pr, en in _F
}

# Segment-level mapping from an ad URL (/msg/lv/<path>/xxxx.html) to our category.
PATH_CATEGORY = [
    ("completing-pc/video", "gpu"),
    ("completing-pc/cpu", "cpu"),
    ("completing-pc/ram", "ram"),
    ("completing-pc/hdd", "storage"),
    ("completing-pc/ssd", "storage"),
    ("completing-pc/motherboards", "motherboard"),
    ("completing-pc/cases", "case_cooling"),
    ("completing-pc/network-cards", "network"),
    ("completing-pc/accessories-and-cables", "pc_parts_other"),
    ("completing-pc/parts-for-repair", "pc_parts_other"),
    ("completing-pc/controllers", "pc_parts_other"),
    ("completing-pc/cd-rom-dvd", "pc_parts_other"),
    ("completing-pc", "pc_parts_other"),
    ("completing-notebook", "pc_parts_other"),
    ("computers/pc", "pc"),
    ("computers/noutbooks", "laptop"),
    ("computers/tablets", "tablet"),
    ("computers/game-consoles", "console"),
    ("computers/games", "console"),
    ("computers/monitors", "monitor"),
    ("computers/accessories", "peripheral"),
    ("computers/multimedia", "audio"),
    ("computers/hubs-switch-routers", "network"),
    ("photo-optics/digital-cameras", "camera"),
    ("photo-optics/slr-cameras", "camera"),
    ("photo-optics/film-cameras", "film_camera"),
    ("photo-optics/objectives", "lens"),
    ("photo-optics/memory-for-digital-cameras", "storage"),
    ("photo-optics", "camera_accessory"),
    ("phones/mobile-phones", "phone"),
    ("phones", "phone"),
    ("audio-video-dvd-sat/audio", "audio"),
    ("audio-video-dvd-sat/dvd-and-video-technics", "video"),
    ("tvs", "tv"),
    ("smart-house-arduino-raspberry-pi", "smart_home"),
]

SERVICE_PATH_MARKERS = (
    "repairing-pcs", "installation-of-program-providing", "photographers-services",
    "phototechnics-hire", "video-operator-services", "electronics-repair-service",
)


def category_from_path(path: str, default: str = "other") -> str:
    for marker, cat in PATH_CATEGORY:
        if f"/{marker}/" in path or path.rstrip("/").endswith("/" + marker):
            return cat
    return default


def is_service_path(path: str) -> bool:
    return any(m in path for m in SERVICE_PATH_MARKERS)


def effective_feeds(settings) -> list[dict]:
    overrides = settings.get("feeds", {}) or {}
    out = []
    for k, f in FEEDS.items():
        o = overrides.get(k, {})
        d = dict(f)
        d["enabled"] = bool(o.get("enabled", f["enabled_default"]))
        d["priority"] = bool(o.get("priority", f["priority"]))
        out.append(d)
    return out
