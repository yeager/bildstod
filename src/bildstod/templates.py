"""Schedule templates for Bildstöd.

Built-in templates include ARASAAC pictogram IDs so that images are
automatically downloaded and shown when a template is loaded.
"""

import json
import os
import threading
from pathlib import Path

import gettext
_ = gettext.gettext

from bildstod.library import get_config_dir, get_images_dir
from bildstod.schedule import Schedule, ScheduleItem


def get_templates_dir():
    p = get_config_dir() / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ARASAAC pictogram IDs for common activities
_ARASAAC_IDS = {
    "Wake up": 8988,
    "Breakfast": 4625,
    "Get dressed": 2781,
    "Brush teeth": 2326,
    "Go to school": 3082,
    "School": 3082,
    "Lunch": 4609,
    "Come home": 6964,
    "Snack": 4694,
    "Play": 11653,      # fritid
    "Dinner": 4592,
    "Evening routine": 6942,  # god natt
    "Bedtime": 6027,    # sova
    "Rest": 3299,       # vila
}


def _ensure_arasaac_image(picto_id):
    """Download an ARASAAC image if not already cached. Returns filename."""
    dest_dir = get_images_dir()
    filename = f"arasaac_{picto_id}.png"
    dest = dest_dir / filename
    if dest.exists():
        return filename
    url = f"https://static.arasaac.org/pictograms/{picto_id}/{picto_id}_500.png"
    try:
        from urllib.request import urlopen, Request
        req = Request(url, headers={"User-Agent": "Bildstod/0.4.0"})
        with urlopen(req, timeout=15) as resp:
            with open(dest, "wb") as f:
                f.write(resp.read())
        return filename
    except Exception:
        return ""


def prefetch_template_images():
    """Download all ARASAAC images used by built-in templates (background)."""
    def _fetch():
        for picto_id in set(_ARASAAC_IDS.values()):
            _ensure_arasaac_image(picto_id)
    thread = threading.Thread(target=_fetch, daemon=True)
    thread.start()


def get_builtin_templates():
    """Return built-in template definitions with ARASAAC image references."""
    return [
        {
            "name": _("School Day"),
            "items": [
                {"label": _("Wake up"), "time_str": "06:30", "duration": 15, "category": "morning", "arasaac_id": 8988},
                {"label": _("Breakfast"), "time_str": "06:45", "duration": 20, "category": "meals", "arasaac_id": 4625},
                {"label": _("Get dressed"), "time_str": "07:05", "duration": 15, "category": "morning", "arasaac_id": 2781},
                {"label": _("Brush teeth"), "time_str": "07:20", "duration": 10, "category": "hygiene", "arasaac_id": 2326},
                {"label": _("Go to school"), "time_str": "07:30", "duration": 30, "category": "transport", "arasaac_id": 3082},
                {"label": _("School"), "time_str": "08:00", "duration": 360, "category": "school", "arasaac_id": 3082},
                {"label": _("Lunch"), "time_str": "11:30", "duration": 30, "category": "meals", "arasaac_id": 4609},
                {"label": _("Come home"), "time_str": "14:00", "duration": 30, "category": "transport", "arasaac_id": 6964},
                {"label": _("Snack"), "time_str": "14:30", "duration": 15, "category": "meals", "arasaac_id": 4694},
                {"label": _("Play"), "time_str": "14:45", "duration": 60, "category": "play", "arasaac_id": 11653},
                {"label": _("Dinner"), "time_str": "17:30", "duration": 30, "category": "meals", "arasaac_id": 4592},
                {"label": _("Evening routine"), "time_str": "19:00", "duration": 30, "category": "evening", "arasaac_id": 6942},
                {"label": _("Brush teeth"), "time_str": "19:30", "duration": 10, "category": "hygiene", "arasaac_id": 2326},
                {"label": _("Bedtime"), "time_str": "19:45", "duration": 15, "category": "evening", "arasaac_id": 6027},
            ]
        },
        {
            "name": _("Weekend"),
            "items": [
                {"label": _("Wake up"), "time_str": "08:00", "duration": 15, "category": "morning", "arasaac_id": 8988},
                {"label": _("Breakfast"), "time_str": "08:15", "duration": 30, "category": "meals", "arasaac_id": 4625},
                {"label": _("Get dressed"), "time_str": "08:45", "duration": 15, "category": "morning", "arasaac_id": 2781},
                {"label": _("Play"), "time_str": "09:00", "duration": 120, "category": "play", "arasaac_id": 11653},
                {"label": _("Lunch"), "time_str": "12:00", "duration": 30, "category": "meals", "arasaac_id": 4609},
                {"label": _("Rest"), "time_str": "12:30", "duration": 60, "category": "rest", "arasaac_id": 3299},
                {"label": _("Play"), "time_str": "14:00", "duration": 120, "category": "play", "arasaac_id": 11653},
                {"label": _("Snack"), "time_str": "16:00", "duration": 15, "category": "meals", "arasaac_id": 4694},
                {"label": _("Dinner"), "time_str": "17:30", "duration": 30, "category": "meals", "arasaac_id": 4592},
                {"label": _("Evening routine"), "time_str": "19:00", "duration": 30, "category": "evening", "arasaac_id": 6942},
                {"label": _("Bedtime"), "time_str": "20:00", "duration": 15, "category": "evening", "arasaac_id": 6027},
            ]
        },
        {
            "name": _("Holiday"),
            "items": [
                {"label": _("Wake up"), "time_str": "08:30", "duration": 15, "category": "morning", "arasaac_id": 8988},
                {"label": _("Breakfast"), "time_str": "08:45", "duration": 30, "category": "meals", "arasaac_id": 4625},
                {"label": _("Get dressed"), "time_str": "09:15", "duration": 15, "category": "morning", "arasaac_id": 2781},
                {"label": _("Play"), "time_str": "09:30", "duration": 120, "category": "play", "arasaac_id": 11653},
                {"label": _("Lunch"), "time_str": "12:00", "duration": 30, "category": "meals", "arasaac_id": 4609},
                {"label": _("Rest"), "time_str": "12:30", "duration": 60, "category": "rest", "arasaac_id": 3299},
                {"label": _("Play"), "time_str": "14:00", "duration": 180, "category": "play", "arasaac_id": 11653},
                {"label": _("Dinner"), "time_str": "17:30", "duration": 30, "category": "meals", "arasaac_id": 4592},
                {"label": _("Evening routine"), "time_str": "19:30", "duration": 30, "category": "evening", "arasaac_id": 6942},
                {"label": _("Bedtime"), "time_str": "20:30", "duration": 15, "category": "evening", "arasaac_id": 6027},
            ]
        },
    ]


def template_to_schedule(template_data):
    """Convert a template dict into a Schedule object.

    If items have arasaac_id, the corresponding pictogram images are
    downloaded (in a background thread) and assigned to the schedule items.
    """
    schedule = Schedule(name=template_data["name"])
    items_needing_images = []
    for item_data in template_data["items"]:
        si = ScheduleItem(
            label=item_data["label"],
            time_str=item_data["time_str"],
            duration=item_data["duration"],
            category=item_data.get("category", "other"),
        )
        arasaac_id = item_data.get("arasaac_id")
        if arasaac_id:
            # Try cached image first (instant)
            filename = f"arasaac_{arasaac_id}.png"
            if (get_images_dir() / filename).exists():
                si.image_filename = filename
            else:
                items_needing_images.append((si, arasaac_id))
        schedule.add_item(si)

    # Download missing images in background
    if items_needing_images:
        def _fetch_images():
            for sched_item, picto_id in items_needing_images:
                fname = _ensure_arasaac_image(picto_id)
                if fname:
                    sched_item.image_filename = fname
        thread = threading.Thread(target=_fetch_images, daemon=True)
        thread.start()

    return schedule


def save_as_template(schedule, name=None):
    """Save a schedule as a user template."""
    tpl = schedule.to_dict()
    if name:
        tpl["name"] = name
    safe_name = tpl["name"].replace(" ", "_").replace("/", "_")
    path = get_templates_dir() / f"{safe_name}.json"
    with open(path, "w") as f:
        json.dump(tpl, f, indent=2, ensure_ascii=False)
    return path


def list_user_templates():
    """List user-saved templates."""
    templates = []
    for p in get_templates_dir().glob("*.json"):
        try:
            with open(p) as f:
                data = json.load(f)
            templates.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    return templates
