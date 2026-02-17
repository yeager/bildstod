"""Schedule templates for Bildstöd."""

import json
from pathlib import Path

import gettext
_ = gettext.gettext

from bildstod.library import get_config_dir
from bildstod.schedule import Schedule, ScheduleItem


def get_templates_dir():
    p = get_config_dir() / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_builtin_templates():
    """Return built-in template definitions."""
    return [
        {
            "name": _("School Day"),
            "items": [
                {"label": _("Wake up"), "time_str": "06:30", "duration": 15, "category": "morning"},
                {"label": _("Breakfast"), "time_str": "06:45", "duration": 20, "category": "meals"},
                {"label": _("Get dressed"), "time_str": "07:05", "duration": 15, "category": "morning"},
                {"label": _("Brush teeth"), "time_str": "07:20", "duration": 10, "category": "hygiene"},
                {"label": _("Go to school"), "time_str": "07:30", "duration": 30, "category": "transport"},
                {"label": _("School"), "time_str": "08:00", "duration": 360, "category": "school"},
                {"label": _("Lunch"), "time_str": "11:30", "duration": 30, "category": "meals"},
                {"label": _("Come home"), "time_str": "14:00", "duration": 30, "category": "transport"},
                {"label": _("Snack"), "time_str": "14:30", "duration": 15, "category": "meals"},
                {"label": _("Play"), "time_str": "14:45", "duration": 60, "category": "play"},
                {"label": _("Dinner"), "time_str": "17:30", "duration": 30, "category": "meals"},
                {"label": _("Evening routine"), "time_str": "19:00", "duration": 30, "category": "evening"},
                {"label": _("Brush teeth"), "time_str": "19:30", "duration": 10, "category": "hygiene"},
                {"label": _("Bedtime"), "time_str": "19:45", "duration": 15, "category": "evening"},
            ]
        },
        {
            "name": _("Weekend"),
            "items": [
                {"label": _("Wake up"), "time_str": "08:00", "duration": 15, "category": "morning"},
                {"label": _("Breakfast"), "time_str": "08:15", "duration": 30, "category": "meals"},
                {"label": _("Get dressed"), "time_str": "08:45", "duration": 15, "category": "morning"},
                {"label": _("Play"), "time_str": "09:00", "duration": 120, "category": "play"},
                {"label": _("Lunch"), "time_str": "12:00", "duration": 30, "category": "meals"},
                {"label": _("Rest"), "time_str": "12:30", "duration": 60, "category": "rest"},
                {"label": _("Play"), "time_str": "14:00", "duration": 120, "category": "play"},
                {"label": _("Snack"), "time_str": "16:00", "duration": 15, "category": "meals"},
                {"label": _("Dinner"), "time_str": "17:30", "duration": 30, "category": "meals"},
                {"label": _("Evening routine"), "time_str": "19:00", "duration": 30, "category": "evening"},
                {"label": _("Bedtime"), "time_str": "20:00", "duration": 15, "category": "evening"},
            ]
        },
        {
            "name": _("Holiday"),
            "items": [
                {"label": _("Wake up"), "time_str": "08:30", "duration": 15, "category": "morning"},
                {"label": _("Breakfast"), "time_str": "08:45", "duration": 30, "category": "meals"},
                {"label": _("Get dressed"), "time_str": "09:15", "duration": 15, "category": "morning"},
                {"label": _("Play"), "time_str": "09:30", "duration": 120, "category": "play"},
                {"label": _("Lunch"), "time_str": "12:00", "duration": 30, "category": "meals"},
                {"label": _("Rest"), "time_str": "12:30", "duration": 60, "category": "rest"},
                {"label": _("Play"), "time_str": "14:00", "duration": 180, "category": "play"},
                {"label": _("Dinner"), "time_str": "17:30", "duration": 30, "category": "meals"},
                {"label": _("Evening routine"), "time_str": "19:30", "duration": 30, "category": "evening"},
                {"label": _("Bedtime"), "time_str": "20:30", "duration": 15, "category": "evening"},
            ]
        },
    ]


def template_to_schedule(template_data):
    """Convert a template dict into a Schedule object."""
    schedule = Schedule(name=template_data["name"])
    for item_data in template_data["items"]:
        si = ScheduleItem(
            label=item_data["label"],
            time_str=item_data["time_str"],
            duration=item_data["duration"],
            category=item_data.get("category", "other"),
        )
        schedule.add_item(si)
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
