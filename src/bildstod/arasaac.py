"""ARASAAC pictogram search with Swedish keyword support for Bildstöd.

Includes an interactive GTK4 search view and a provider class that supports
both Swedish (local lookup, 13,000+ terms) and English (API) search.

ARASAAC pictograms are licensed under Creative Commons BY-NC-SA 4.0
by the Government of Aragon, created by Sergio Palao.
"""

import json
import os
import threading
from importlib import resources
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

import gettext
_ = gettext.gettext

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, GdkPixbuf

from bildstod.library import get_images_dir, PictureLibrary

API_BASE = "https://api.arasaac.org/v1"
IMAGE_BASE = "https://static.arasaac.org/pictograms"

ATTRIBUTION = (
    "Pictograms by Sergio Palao, from ARASAAC (https://arasaac.org), "
    "licensed under CC BY-NC-SA 3.0"
)


def _load_json_data(filename: str) -> dict:
    """Load a JSON data file bundled with the package."""
    try:
        ref = resources.files("bildstod").joinpath("data").joinpath(filename)
        return json.loads(ref.read_text(encoding="utf-8"))
    except (TypeError, FileNotFoundError, ModuleNotFoundError):
        pass
    data_dir = Path(__file__).parent / "data"
    data_file = data_dir / filename
    if data_file.exists():
        return json.loads(data_file.read_text(encoding="utf-8"))
    return {}


# Lazy-loaded Swedish lookups
_sv_lookup = None   # {sv_term: [picto_id, ...]}
_en2sv = None       # {en_term: sv_term}


def _get_sv_lookup():
    global _sv_lookup
    if _sv_lookup is None:
        _sv_lookup = _load_json_data("arasaac_sv.json")
    return _sv_lookup


def _get_en2sv():
    global _en2sv
    if _en2sv is None:
        _en2sv = _load_json_data("arasaac_en2sv.json")
    return _en2sv


def search_pictograms_sv(keyword):
    """Search Swedish keyword locally. Returns list of dicts with _id."""
    lookup = _get_sv_lookup()
    term = keyword.lower().strip()
    ids = []
    # Exact match first
    if term in lookup:
        ids = lookup[term]
    else:
        # Prefix match
        for sv_term, picto_ids in lookup.items():
            if sv_term.startswith(term):
                ids.extend(picto_ids)
            if len(ids) >= 60:
                break
    return [{"_id": pid, "keywords": [{"keyword": keyword, "locale": "sv"}]}
            for pid in ids[:60]]


def search_pictograms(keyword, lang="sv"):
    """Search ARASAAC. For Swedish, uses local lookup. For others, uses API."""
    if lang == "sv":
        return search_pictograms_sv(keyword)

    encoded = __import__('urllib.parse', fromlist=['quote']).quote(keyword)
    url = f"{API_BASE}/pictograms/{lang}/search/{encoded}"
    try:
        req = Request(url, headers={"User-Agent": "Bildstod/0.3.0"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def get_image_url(pictogram_id, size=500):
    return f"{IMAGE_BASE}/{pictogram_id}/{pictogram_id}_{size}.png"


def download_image(pictogram_id, dest_dir=None, size=500):
    if dest_dir is None:
        dest_dir = get_images_dir()
    dest = Path(dest_dir) / f"arasaac_{pictogram_id}.png"
    if dest.exists():
        return str(dest)
    url = get_image_url(pictogram_id, size)
    try:
        req = Request(url, headers={"User-Agent": "Bildstod/0.3.0"})
        with urlopen(req, timeout=15) as resp:
            with open(dest, "wb") as f:
                f.write(resp.read())
        return str(dest)
    except Exception:
        return None


def get_best_keyword(pictogram, lang="sv"):
    """Extract the best keyword. Prefers Swedish via local lookup."""
    for kw in pictogram.get("keywords", []):
        if kw.get("locale") == lang:
            return kw.get("keyword", "")
    # Try translating English keyword to Swedish
    en2sv = _get_en2sv()
    for kw in pictogram.get("keywords", []):
        en_word = kw.get("keyword", "").lower()
        if en_word in en2sv:
            return en2sv[en_word]
    # Fallback
    keywords = pictogram.get("keywords", [])
    if keywords:
        return keywords[0].get("keyword", "")
    return str(pictogram.get("_id", ""))


class ArasaacSearchView(Gtk.Box):
    """Search and browse ARASAAC pictograms with Swedish support."""

    def __init__(self, library, status_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.library = library
        self.status_callback = status_callback
        self._results = []

        # Search bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.set_margin_top(6)
        search_box.set_margin_bottom(6)
        search_box.set_margin_start(12)
        search_box.set_margin_end(12)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(
            _("Search pictograms (Swedish or English)..."))
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("activate", self._on_search)
        search_box.append(self.search_entry)

        search_btn = Gtk.Button(icon_name="edit-find-symbolic")
        search_btn.add_css_class("suggested-action")
        search_btn.connect("clicked", self._on_search)
        search_box.append(search_btn)

        self.append(search_box)

        # Attribution
        attr_label = Gtk.Label(label=ATTRIBUTION)
        attr_label.add_css_class("dim-label")
        attr_label.add_css_class("caption")
        attr_label.set_wrap(True)
        attr_label.set_margin_start(12)
        attr_label.set_margin_end(12)
        attr_label.set_margin_bottom(4)
        self.append(attr_label)

        self.append(Gtk.Separator())

        self.spinner = Gtk.Spinner()
        self.spinner.set_margin_top(12)
        self.spinner.set_visible(False)
        self.append(self.spinner)

        self.info_label = Gtk.Label(
            label=_("Search for pictograms to add to your library."))
        self.info_label.set_margin_top(24)
        self.info_label.add_css_class("dim-label")
        self.append(self.info_label)

        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(8)
        self.flowbox.set_min_children_per_line(3)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_column_spacing(12)
        self.flowbox.set_row_spacing(12)
        self.flowbox.set_margin_top(12)
        self.flowbox.set_margin_bottom(12)
        self.flowbox.set_margin_start(12)
        self.flowbox.set_margin_end(12)
        scroll.set_child(self.flowbox)
        self.append(scroll)

    def _detect_language(self, query):
        """Simple heuristic: if query contains åäö, it's Swedish."""
        swedish_chars = set('åäöÅÄÖ')
        if any(c in swedish_chars for c in query):
            return "sv"
        # Check if the term exists in Swedish lookup
        lookup = _get_sv_lookup()
        if query.lower().strip() in lookup:
            return "sv"
        return "en"

    def _on_search(self, *args):
        query = self.search_entry.get_text().strip()
        if not query:
            return

        self._clear_results()
        self.spinner.set_visible(True)
        self.spinner.start()
        self.info_label.set_text(_("Searching..."))
        self.info_label.set_visible(True)

        lang = self._detect_language(query)

        def do_search():
            results = search_pictograms(query, lang=lang)
            GLib.idle_add(self._on_results, results, query, lang)

        thread = threading.Thread(target=do_search, daemon=True)
        thread.start()

    def _on_results(self, results, query, lang="sv"):
        self.spinner.stop()
        self.spinner.set_visible(False)
        self._results = results

        if not results:
            self.info_label.set_text(
                _("No pictograms found for '%s'.") % query)
            self.info_label.set_visible(True)
            return

        self.info_label.set_text(_("%d pictograms found") % len(results))

        for picto in results[:60]:
            card = self._make_result_card(picto)
            self.flowbox.append(card)

        if self.status_callback:
            self.status_callback(
                _("ARASAAC: %d results for '%s'") % (len(results), query))

    def _make_result_card(self, picto):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(120, 160)

        image_widget = Gtk.Image.new_from_icon_name(
            "content-loading-symbolic")
        image_widget.set_pixel_size(96)
        box.append(image_widget)

        keyword = get_best_keyword(picto, lang="sv")
        label = Gtk.Label(label=keyword)
        label.set_ellipsize(3)
        label.set_max_width_chars(14)
        label.add_css_class("heading")
        box.append(label)

        add_btn = Gtk.Button(label=_("Add"))
        add_btn.add_css_class("pill")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", self._on_add_clicked, picto)
        box.append(add_btn)

        picto_id = picto["_id"]

        def load_thumb():
            path = download_image(picto_id, size=300)
            if path:
                GLib.idle_add(self._set_image, image_widget, path)

        thread = threading.Thread(target=load_thumb, daemon=True)
        thread.start()

        return box

    def _set_image(self, image_widget, path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, 96, 96, True)
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_size_request(96, 96)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            parent = image_widget.get_parent()
            if parent:
                next_sibling = image_widget.get_next_sibling()
                parent.remove(image_widget)
                if next_sibling:
                    parent.insert_child_after(
                        picture,
                        next_sibling.get_prev_sibling()
                        if next_sibling.get_prev_sibling() else None)
                else:
                    parent.append(picture)
                parent.reorder_child_after(picture, None)
        except Exception:
            pass

    def _on_add_clicked(self, btn, picto):
        btn.set_sensitive(False)
        btn.set_label(_("Adding..."))
        picto_id = picto["_id"]
        keyword = get_best_keyword(picto, lang="sv")

        def do_add():
            path = download_image(picto_id)
            GLib.idle_add(self._finish_add, path, picto_id, keyword, btn)

        thread = threading.Thread(target=do_add, daemon=True)
        thread.start()

    def _finish_add(self, path, picto_id, keyword, btn):
        if path:
            item = {
                "id": f"arasaac_{picto_id}",
                "filename": os.path.basename(path),
                "label": keyword,
                "category": "other",
                "duration": 0,
                "source": "arasaac",
                "arasaac_id": picto_id,
            }
            existing = self.library.get_by_id(item["id"])
            if not existing:
                self.library.items.append(item)
                self.library.save()

            btn.set_label("✓")
            btn.remove_css_class("suggested-action")
            if self.status_callback:
                self.status_callback(_("Added: %s") % keyword)
        else:
            btn.set_label(_("Error"))
            btn.add_css_class("destructive-action")

    def _clear_results(self):
        while True:
            child = self.flowbox.get_first_child()
            if child is None:
                break
            self.flowbox.remove(child)
        self._results = []
