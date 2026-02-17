"""Picture library management for Bildstöd."""

import json
import os
import shutil
import uuid
from pathlib import Path

import gettext
_ = gettext.gettext

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, GdkPixbuf

CATEGORIES = [
    ("morning", _("Morning Routine")),
    ("meals", _("Meals")),
    ("school", _("School")),
    ("play", _("Play")),
    ("hygiene", _("Hygiene")),
    ("transport", _("Transport")),
    ("rest", _("Rest")),
    ("evening", _("Evening Routine")),
    ("other", _("Other")),
]


def get_config_dir():
    p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "bildstod"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_data_dir():
    p = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "bildstod"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_images_dir():
    p = get_data_dir() / "images"
    p.mkdir(parents=True, exist_ok=True)
    return p


class PictureLibrary:
    """Manages the picture library stored in library.json."""

    def __init__(self):
        self.items = []
        self.path = get_config_dir() / "library.json"
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self.items = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.items = []
        else:
            self.items = []

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.items, f, indent=2, ensure_ascii=False)

    def add_image(self, source_path, label, category="other", duration=0):
        """Import an image into the library. Returns the new item dict."""
        src = Path(source_path)
        ext = src.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".svg"):
            return None
        uid = str(uuid.uuid4())
        dest = get_images_dir() / f"{uid}{ext}"
        shutil.copy2(src, dest)
        item = {
            "id": uid,
            "filename": dest.name,
            "label": label,
            "category": category,
            "duration": duration,
        }
        self.items.append(item)
        self.save()
        return item

    def remove_image(self, item_id):
        item = self.get_by_id(item_id)
        if item:
            img_path = get_images_dir() / item["filename"]
            if img_path.exists():
                img_path.unlink()
            self.items = [i for i in self.items if i["id"] != item_id]
            self.save()

    def get_by_id(self, item_id):
        for i in self.items:
            if i["id"] == item_id:
                return i
        return None

    def get_by_category(self, category):
        return [i for i in self.items if i["category"] == category]

    def get_image_path(self, item):
        return str(get_images_dir() / item["filename"])


class LibraryView(Gtk.Box):
    """Grid view of the picture library with categories."""

    def __init__(self, library, status_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.library = library
        self.status_callback = status_callback
        self._on_item_activated = None

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)

        add_btn = Gtk.Button(label=_("Import Image"))
        add_btn.set_icon_name("list-add-symbolic")
        add_btn.connect("clicked", self._on_add_clicked)
        add_btn.add_css_class("suggested-action")
        toolbar.append(add_btn)

        remove_btn = Gtk.Button(label=_("Remove"))
        remove_btn.set_icon_name("list-remove-symbolic")
        remove_btn.connect("clicked", self._on_remove_clicked)
        remove_btn.add_css_class("destructive-action")
        toolbar.append(remove_btn)

        # Category filter
        self.category_dropdown = Gtk.DropDown.new_from_strings(
            [_("All Categories")] + [c[1] for c in CATEGORIES]
        )
        self.category_dropdown.connect("notify::selected", self._on_filter_changed)
        toolbar.append(self.category_dropdown)

        self.append(toolbar)
        self.append(Gtk.Separator())

        # Scrolled grid
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(8)
        self.flowbox.set_min_children_per_line(3)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_column_spacing(12)
        self.flowbox.set_row_spacing(12)
        self.flowbox.set_margin_top(12)
        self.flowbox.set_margin_bottom(12)
        self.flowbox.set_margin_start(12)
        self.flowbox.set_margin_end(12)
        self.flowbox.connect("child-activated", self._on_child_activated)
        scroll.set_child(self.flowbox)
        self.append(scroll)

        # Drag source setup on the flowbox children happens in _populate
        self._populate()

    def set_on_item_activated(self, callback):
        """Set callback for when an item is double-clicked/activated: callback(item_dict)."""
        self._on_item_activated = callback

    def _on_child_activated(self, flowbox, child):
        if self._on_item_activated and hasattr(child, '_item'):
            self._on_item_activated(child._item)

    def _populate(self):
        while True:
            child = self.flowbox.get_first_child()
            if child is None:
                break
            self.flowbox.remove(child)

        selected_cat = self.category_dropdown.get_selected()
        if selected_cat == 0:
            items = self.library.items
        else:
            cat_key = CATEGORIES[selected_cat - 1][0]
            items = self.library.get_by_category(cat_key)

        for item in items:
            card = self._make_card(item)
            self.flowbox.append(card)

    def _make_card(self, item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(120, 140)
        box._item = item

        img_path = self.library.get_image_path(item)
        if os.path.exists(img_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_path, 96, 96, True)
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                picture = Gtk.Picture.new_for_paintable(texture)
                picture.set_size_request(96, 96)
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                box.append(picture)
            except Exception:
                icon = Gtk.Image.new_from_icon_name("image-missing-symbolic")
                icon.set_pixel_size(64)
                box.append(icon)
        else:
            icon = Gtk.Image.new_from_icon_name("image-missing-symbolic")
            icon.set_pixel_size(64)
            box.append(icon)

        label = Gtk.Label(label=item.get("label", ""))
        label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        label.set_max_width_chars(14)
        label.add_css_class("heading")
        box.append(label)

        cat_label = Gtk.Label(label=self._category_name(item.get("category", "other")))
        cat_label.add_css_class("dim-label")
        cat_label.add_css_class("caption")
        box.append(cat_label)

        # Setup drag source
        drag = Gtk.DragSource.new()
        drag.set_actions(Gdk.DragAction.COPY)
        drag.connect("prepare", self._on_drag_prepare, item)
        box.add_controller(drag)

        return box

    def _on_drag_prepare(self, source, x, y, item):
        val = GLib.Bytes.new(json.dumps(item).encode())
        return Gdk.ContentProvider.new_for_bytes("application/x-bildstod-item", val)

    def _category_name(self, key):
        for k, v in CATEGORIES:
            if k == key:
                return v
        return _("Other")

    def _on_filter_changed(self, dropdown, pspec):
        self._populate()

    def _on_add_clicked(self, btn):
        dialog = Gtk.FileDialog.new()
        dialog.set_title(_("Import Image"))
        ff = Gtk.FileFilter()
        ff.set_name(_("Images"))
        ff.add_mime_type("image/png")
        ff.add_mime_type("image/jpeg")
        ff.add_mime_type("image/svg+xml")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(ff)
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        filepath = gfile.get_path()
        # Show a simple dialog to get label and category
        self._show_add_dialog(filepath)

    def _show_add_dialog(self, filepath):
        dialog = Adw.AlertDialog.new(_("Add to Library"), _("Enter a label for this image:"))

        # Add entry group using preferences
        entry_row_label = Gtk.Entry()
        entry_row_label.set_placeholder_text(_("Activity name"))
        entry_row_label.set_margin_start(24)
        entry_row_label.set_margin_end(24)
        dialog.set_extra_child(entry_row_label)

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("add", _("Add"))
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")

        dialog.connect("response", self._on_add_response, filepath, entry_row_label)
        dialog.present(self.get_root())

    def _on_add_response(self, dialog, response, filepath, entry):
        if response == "add":
            label = entry.get_text().strip()
            if not label:
                label = Path(filepath).stem
            # Use first category as default
            cat = "other"
            sel = self.category_dropdown.get_selected()
            if sel > 0:
                cat = CATEGORIES[sel - 1][0]
            self.library.add_image(filepath, label, cat)
            self._populate()
            if self.status_callback:
                self.status_callback(_("Image imported: %s") % label)

    def _on_remove_clicked(self, btn):
        selected = self.flowbox.get_selected_children()
        if not selected:
            return
        child = selected[0]
        child_widget = child.get_child()
        if hasattr(child_widget, '_item'):
            item = child_widget._item
            self.library.remove_image(item["id"])
            self._populate()
            if self.status_callback:
                self.status_callback(_("Image removed: %s") % item.get("label", ""))

    def refresh(self):
        self.library.load()
        self._populate()
