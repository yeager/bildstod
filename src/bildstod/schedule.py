"""Daily schedule builder for Bildstöd."""

import json
import os
import uuid
from datetime import datetime, date
from pathlib import Path

import gettext
_ = gettext.gettext

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, GdkPixbuf

from bildstod.library import get_config_dir, get_images_dir, PictureLibrary


def get_schedules_dir():
    p = get_config_dir() / "schedules"
    p.mkdir(parents=True, exist_ok=True)
    return p


class ScheduleItem:
    """A single activity in a schedule."""

    def __init__(self, library_id="", label="", image_filename="",
                 time_str="08:00", duration=30, done=False, category="other"):
        self.id = str(uuid.uuid4())
        self.library_id = library_id
        self.label = label
        self.image_filename = image_filename
        self.time_str = time_str
        self.duration = duration  # minutes
        self.done = done
        self.category = category

    def to_dict(self):
        return {
            "id": self.id,
            "library_id": self.library_id,
            "label": self.label,
            "image_filename": self.image_filename,
            "time_str": self.time_str,
            "duration": self.duration,
            "done": self.done,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, d):
        item = cls()
        item.id = d.get("id", str(uuid.uuid4()))
        item.library_id = d.get("library_id", "")
        item.label = d.get("label", "")
        item.image_filename = d.get("image_filename", "")
        item.time_str = d.get("time_str", "08:00")
        item.duration = d.get("duration", 30)
        item.done = d.get("done", False)
        item.category = d.get("category", "other")
        return item

    @classmethod
    def from_library_item(cls, lib_item):
        item = cls()
        item.library_id = lib_item["id"]
        item.label = lib_item["label"]
        item.image_filename = lib_item["filename"]
        item.duration = lib_item.get("duration", 30) or 30
        item.category = lib_item.get("category", "other")
        return item


class Schedule:
    """A daily schedule containing multiple activities."""

    def __init__(self, name="", schedule_date=None):
        self.name = name or _("New Schedule")
        self.date = schedule_date or date.today().isoformat()
        self.items = []

    def add_item(self, item):
        self.items.append(item)

    def remove_item(self, item_id):
        self.items = [i for i in self.items if i.id != item_id]

    def to_dict(self):
        return {
            "name": self.name,
            "date": self.date,
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_dict(cls, d):
        s = cls()
        s.name = d.get("name", _("New Schedule"))
        s.date = d.get("date", date.today().isoformat())
        s.items = [ScheduleItem.from_dict(i) for i in d.get("items", [])]
        return s

    def save(self, filename=None):
        if not filename:
            safe_name = self.name.replace(" ", "_").replace("/", "_")
            filename = f"{self.date}_{safe_name}.json"
        path = get_schedules_dir() / filename
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def get_current_activity(self):
        """Get the first non-done activity."""
        for item in self.items:
            if not item.done:
                return item
        return None

    def get_next_activity(self, current):
        """Get the activity after current."""
        found = False
        for item in self.items:
            if found and not item.done:
                return item
            if item.id == current.id:
                found = True
        return None


class ScheduleView(Gtk.Box):
    """Vertical timeline schedule builder."""

    def __init__(self, library, status_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.library = library
        self.schedule = Schedule()
        self.status_callback = status_callback
        self._on_activity_changed = None

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)

        # Schedule name entry
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(self.schedule.name)
        self.name_entry.set_hexpand(True)
        self.name_entry.connect("changed", self._on_name_changed)
        toolbar.append(self.name_entry)

        # Date label
        self.date_label = Gtk.Label(label=self.schedule.date)
        self.date_label.add_css_class("dim-label")
        toolbar.append(self.date_label)

        save_btn = Gtk.Button(icon_name="document-save-symbolic")
        save_btn.set_tooltip_text(_("Save Schedule"))
        save_btn.connect("clicked", self._on_save)
        toolbar.append(save_btn)

        load_btn = Gtk.Button(icon_name="document-open-symbolic")
        load_btn.set_tooltip_text(_("Load Schedule"))
        load_btn.connect("clicked", self._on_load)
        toolbar.append(load_btn)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text(_("Add Activity"))
        add_btn.connect("clicked", self._on_add_activity)
        add_btn.add_css_class("suggested-action")
        toolbar.append(add_btn)

        self.append(toolbar)
        self.append(Gtk.Separator())

        # Timeline area
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.timeline_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.timeline_box.set_margin_top(12)
        self.timeline_box.set_margin_bottom(12)
        self.timeline_box.set_margin_start(12)
        self.timeline_box.set_margin_end(12)

        # Drop target for drag from library
        drop_target = Gtk.DropTarget.new(GLib.Bytes, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop)
        self.timeline_box.add_controller(drop_target)

        scroll.set_child(self.timeline_box)
        self.append(scroll)

        self._populate_timeline()

    def set_on_activity_changed(self, callback):
        self._on_activity_changed = callback

    def _notify_change(self):
        if self._on_activity_changed:
            self._on_activity_changed(self.schedule)

    def _on_name_changed(self, entry):
        self.schedule.name = entry.get_text()

    def _populate_timeline(self):
        while True:
            child = self.timeline_box.get_first_child()
            if child is None:
                break
            self.timeline_box.remove(child)

        if not self.schedule.items:
            placeholder = Gtk.Label(label=_("No activities yet.\nAdd from the library or click + to add."))
            placeholder.add_css_class("dim-label")
            placeholder.set_vexpand(True)
            placeholder.set_valign(Gtk.Align.CENTER)
            self.timeline_box.append(placeholder)
            return

        current = self.schedule.get_current_activity()
        for item in self.schedule.items:
            is_current = (current and item.id == current.id)
            row = self._make_timeline_row(item, is_current)
            self.timeline_box.append(row)

    def _make_timeline_row(self, item, is_current=False):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        row.set_margin_start(6)
        row.set_margin_end(6)

        if is_current:
            row.add_css_class("card")
            # Add colored left border via CSS
            row.set_margin_start(2)
            row.set_margin_end(2)

        # Time
        time_label = Gtk.Label(label=item.time_str)
        time_label.set_size_request(60, -1)
        time_label.add_css_class("heading")
        if item.done:
            time_label.add_css_class("dim-label")
        row.append(time_label)

        # Image thumbnail
        img_path = str(get_images_dir() / item.image_filename) if item.image_filename else ""
        if img_path and os.path.exists(img_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_path, 64, 64, True)
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                picture = Gtk.Picture.new_for_paintable(texture)
                picture.set_size_request(64, 64)
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                row.append(picture)
            except Exception:
                icon = Gtk.Image.new_from_icon_name("image-missing-symbolic")
                icon.set_pixel_size(48)
                row.append(icon)
        else:
            icon = Gtk.Image.new_from_icon_name("emblem-photos-symbolic")
            icon.set_pixel_size(48)
            row.append(icon)

        # Label and duration
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)

        name_label = Gtk.Label(label=item.label, xalign=0)
        name_label.add_css_class("title-3")
        if item.done:
            name_label.add_css_class("dim-label")
            # Strikethrough via attributes
            attrs = name_label.get_attributes()
            if attrs is None:
                from gi.repository import Pango
                attrs = Pango.AttrList.new()
            from gi.repository import Pango
            attrs.insert(Pango.attr_strikethrough_new(True))
            name_label.set_attributes(attrs)
        info_box.append(name_label)

        dur_label = Gtk.Label(label=_("%d minutes") % item.duration, xalign=0)
        dur_label.add_css_class("dim-label")
        dur_label.add_css_class("caption")
        info_box.append(dur_label)

        row.append(info_box)

        # Time entry for editing
        time_entry = Gtk.Entry()
        time_entry.set_text(item.time_str)
        time_entry.set_max_width_chars(5)
        time_entry.set_width_chars(5)
        time_entry.set_tooltip_text(_("Time (HH:MM)"))
        time_entry.connect("changed", self._on_time_changed, item)
        row.append(time_entry)

        # Done button
        done_btn = Gtk.CheckButton()
        done_btn.set_active(item.done)
        done_btn.set_tooltip_text(_("Mark as done"))
        done_btn.connect("toggled", self._on_done_toggled, item)
        row.append(done_btn)

        # Remove button
        remove_btn = Gtk.Button(icon_name="edit-delete-symbolic")
        remove_btn.set_tooltip_text(_("Remove activity"))
        remove_btn.add_css_class("flat")
        remove_btn.connect("clicked", self._on_remove_item, item)
        row.append(remove_btn)

        return row

    def _on_time_changed(self, entry, item):
        item.time_str = entry.get_text()

    def _on_done_toggled(self, btn, item):
        item.done = btn.get_active()
        self._populate_timeline()
        self._notify_change()

    def _on_remove_item(self, btn, item):
        self.schedule.remove_item(item.id)
        self._populate_timeline()
        self._notify_change()

    def _on_drop(self, target, value, x, y):
        try:
            data = json.loads(value.get_data().decode())
            sched_item = ScheduleItem.from_library_item(data)
            self.schedule.add_item(sched_item)
            self._populate_timeline()
            self._notify_change()
            if self.status_callback:
                self.status_callback(_("Added: %s") % sched_item.label)
            return True
        except Exception:
            return False

    def _on_add_activity(self, btn):
        """Show a dialog to pick from library items."""
        if not self.library.items:
            dialog = Adw.AlertDialog.new(
                _("Library Empty"),
                _("Add images to the library first.")
            )
            dialog.add_response("ok", _("OK"))
            dialog.present(self.get_root())
            return

        dialog = Adw.AlertDialog.new(
            _("Add Activity"),
            _("Select an activity from the library:")
        )

        # Create a list of library items
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.add_css_class("boxed-list")
        listbox.set_size_request(-1, 300)

        for item in self.library.items:
            row = Adw.ActionRow()
            row.set_title(item["label"])
            row.set_subtitle(item.get("category", ""))
            row._library_item = item
            listbox.append(row)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(listbox)
        scroll.set_size_request(300, 300)
        dialog.set_extra_child(scroll)

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("add", _("Add"))
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")

        dialog.connect("response", self._on_add_dialog_response, listbox)
        dialog.present(self.get_root())

    def _on_add_dialog_response(self, dialog, response, listbox):
        if response == "add":
            selected = listbox.get_selected_row()
            if selected and hasattr(selected, '_library_item'):
                sched_item = ScheduleItem.from_library_item(selected._library_item)
                self.schedule.add_item(sched_item)
                self._populate_timeline()
                self._notify_change()
                if self.status_callback:
                    self.status_callback(_("Added: %s") % sched_item.label)

    def _on_save(self, btn):
        try:
            path = self.schedule.save()
            if self.status_callback:
                self.status_callback(_("Schedule saved: %s") % path.name)
        except Exception as e:
            if self.status_callback:
                self.status_callback(_("Error saving: %s") % str(e))

    def _on_load(self, btn):
        dialog = Gtk.FileDialog.new()
        dialog.set_title(_("Load Schedule"))
        dialog.set_initial_folder(Gio.File.new_for_path(str(get_schedules_dir())))
        ff = Gtk.FileFilter()
        ff.set_name(_("Schedule files"))
        ff.add_pattern("*.json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(ff)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_load_done)

    def _on_load_done(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        try:
            self.schedule = Schedule.load(gfile.get_path())
            self.name_entry.set_text(self.schedule.name)
            self.date_label.set_text(self.schedule.date)
            self._populate_timeline()
            self._notify_change()
            if self.status_callback:
                self.status_callback(_("Schedule loaded: %s") % self.schedule.name)
        except Exception as e:
            if self.status_callback:
                self.status_callback(_("Error loading: %s") % str(e))

    def load_schedule(self, schedule):
        """Load a schedule object directly."""
        self.schedule = schedule
        self.name_entry.set_text(schedule.name)
        self.date_label.set_text(schedule.date)
        self._populate_timeline()
        self._notify_change()

    def refresh(self):
        self._populate_timeline()
