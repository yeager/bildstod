#!/usr/bin/env python3
"""Bildstöd — Visual schedule and picture support tool for children with autism."""

import json
import sys
import gettext
from datetime import datetime
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, GLib

# Set up gettext
TEXTDOMAIN = 'bildstod'
gettext.textdomain(TEXTDOMAIN)
gettext.bindtextdomain(TEXTDOMAIN, '/usr/share/locale')
_ = gettext.gettext

from bildstod import __version__
from bildstod.library import PictureLibrary, LibraryView
from bildstod.arasaac import ArasaacSearchView
from bildstod.schedule import ScheduleView
from bildstod.now_view import NowView
from bildstod.templates import (
    get_builtin_templates, list_user_templates,
    template_to_schedule, save_as_template,
    prefetch_template_images,
)
from bildstod.export import show_export_dialog
from bildstod.accessibility import apply_large_text


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_default_size(1000, 700)
        self.set_title(_("Visual Support"))

        # Initialize data
        self.library = PictureLibrary()

        # Pre-download ARASAAC images used by built-in templates
        prefetch_template_images()

        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header bar
        header = Adw.HeaderBar()

        # View switcher in header
        self.view_stack = Adw.ViewStack()
        view_switcher = Adw.ViewSwitcher()
        view_switcher.set_stack(self.view_stack)
        view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(view_switcher)

        # Menu button
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu = Gio.Menu()
        menu.append(_("Templates"), "win.templates")
        menu.append(_("Export Schedule"), "app.export")
        menu.append(_("Preferences"), "app.preferences")
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About Visual Support"), "app.about")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        main_box.append(header)

        # Create views
        self.schedule_view = ScheduleView(self.library, status_callback=self._set_status)
        self.schedule_view.set_on_activity_changed(self._on_schedule_changed)

        self.now_view = NowView(status_callback=self._set_status)
        self.now_view.set_on_done(self._on_activity_done)
        self.now_view.set_on_skip(self._on_activity_done)

        self.library_view = LibraryView(self.library, status_callback=self._set_status)
        self.library_view.set_on_item_activated(self._on_library_item_activated)

        self.arasaac_view = ArasaacSearchView(self.library, status_callback=self._set_status)

        # Add views to stack
        self.view_stack.add_titled_with_icon(
            self.schedule_view, "schedule", _("Schedule"), "view-list-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.now_view, "now", _("Now"), "media-playback-start-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.library_view, "library", _("Library"), "folder-pictures-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.arasaac_view, "arasaac", _("ARASAAC"), "system-search-symbolic"
        )

        main_box.append(self.view_stack)

        # Show Library tab by default if schedule is empty
        if not self.schedule_view.schedule.items:
            self.view_stack.set_visible_child_name("library")

        # Status bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_box.set_margin_start(12)
        status_box.set_margin_end(12)
        status_box.set_margin_top(4)
        status_box.set_margin_bottom(4)

        self.status_label = Gtk.Label(label=_("Ready"))
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("caption")
        status_box.append(self.status_label)

        self.clock_label = Gtk.Label()
        self.clock_label.add_css_class("dim-label")
        self.clock_label.add_css_class("caption")
        status_box.append(self.clock_label)

        main_box.append(Gtk.Separator())
        main_box.append(status_box)

        # Update clock
        self._update_clock()
        GLib.timeout_add_seconds(30, self._update_clock)

        # Window actions
        templates_action = Gio.SimpleAction.new("templates", None)
        templates_action.connect("activate", self._show_templates)
        self.add_action(templates_action)

    def _set_status(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        self.status_label.set_text(f"[{now}] {text}")

    def _update_clock(self):
        self.clock_label.set_text(datetime.now().strftime("%Y-%m-%d %H:%M"))
        return True

    def _on_schedule_changed(self, schedule):
        self.now_view.update_schedule(schedule)

    def _on_activity_done(self, item):
        self.schedule_view.refresh()
        self._set_status(_("Completed: %s") % item.label)

    def _on_library_item_activated(self, item):
        """When a library item is activated, add it to the schedule."""
        from bildstod.schedule import ScheduleItem
        sched_item = ScheduleItem.from_library_item(item)
        self.schedule_view.schedule.add_item(sched_item)
        self.schedule_view.refresh()
        self.schedule_view._notify_change()
        self._set_status(_("Added to schedule: %s") % item["label"])

    def _show_templates(self, action, param):
        dialog = Adw.AlertDialog.new(
            _("Schedule Templates"),
            _("Load a template or save current schedule as template:")
        )

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.add_css_class("boxed-list")

        # Built-in templates
        builtin = get_builtin_templates()
        for tpl in builtin:
            row = Adw.ActionRow()
            row.set_title(tpl["name"])
            row.set_subtitle(_("%d activities") % len(tpl["items"]))
            row._template = tpl
            row._is_builtin = True
            listbox.append(row)

        # User templates
        user_templates = list_user_templates()
        for tpl in user_templates:
            row = Adw.ActionRow()
            row.set_title(tpl.get("name", _("Custom")))
            row.set_subtitle(_("%d activities (custom)") % len(tpl.get("items", [])))
            row._template = tpl
            row._is_builtin = False
            listbox.append(row)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(listbox)
        scroll.set_size_request(350, 300)
        dialog.set_extra_child(scroll)

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save Current as Template"))
        dialog.add_response("load", _("Load Selected"))
        dialog.set_response_appearance("load", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("load")
        dialog.set_close_response("cancel")

        dialog.connect("response", self._on_template_response, listbox)
        dialog.present(self)

    def _on_template_response(self, dialog, response, listbox):
        if response == "load":
            selected = listbox.get_selected_row()
            if selected and hasattr(selected, '_template'):
                schedule = template_to_schedule(selected._template)
                self.schedule_view.load_schedule(schedule)
                self._set_status(_("Template loaded: %s") % schedule.name)
                # Refresh after a short delay to show images downloaded in background
                GLib.timeout_add(2000, self._refresh_after_template)
        elif response == "save":
            schedule = self.schedule_view.schedule
            path = save_as_template(schedule)
            self._set_status(_("Template saved: %s") % path.name)

    def _refresh_after_template(self):
        """Refresh schedule view after template images have downloaded."""
        self.schedule_view.refresh()
        return False  # Don't repeat

    def show_about(self, action, param):
        about = Adw.AboutDialog(
            application_name=_("Visual Support"),
            application_icon="se.danielnylander.bildstod",
            developer_name="Daniel Nylander",
            version=__version__,
            website="https://github.com/yeager/bildstod",
            issue_url="https://github.com/yeager/bildstod/issues",
            support_url="https://www.autismappar.se",
            translate_url="https://app.transifex.com/danielnylander/bildstod",
            license_type=Gtk.License.GPL_3_0,
            developers=["Daniel Nylander <daniel@danielnylander.se>"],
            documenters=["Daniel Nylander"],
            artists=[_("ARASAAC pictograms (https://arasaac.org)")],
            copyright="© 2026 Daniel Nylander",
            comments=_(
                "Visual schedule and picture support tool with "
                "ARASAAC pictogram search for children with autism "
                "and language disorders.\n\n"
                "Part of the Autismappar suite — free tools for "
                "communication and daily structure."
            ),
            debug_info=f"TTS: {__import__('bildstod.tts', fromlist=['get_tts_info']).get_tts_info()}\nVersion: {__version__}\n"
                       f"GTK: {Gtk.get_major_version()}.{Gtk.get_minor_version()}\n"
                       f"Adwaita: {Adw.get_major_version()}.{Adw.get_minor_version()}\n"
                       f"Python: {sys.version}",
            debug_info_filename="bildstod-debug-info.txt",
        )
        about.add_link(_("Autismappar"), "https://www.autismappar.se")
        about.add_link("GTK 4", "https://gtk.org")
        about.add_link("libadwaita", "https://gnome.pages.gitlab.gnome.org/libadwaita/")
        about.add_link("ARASAAC", "https://arasaac.org")
        about.add_link("Piper TTS", "https://github.com/rhasspy/piper")
        about.add_link("espeak-ng", "https://github.com/espeak-ng/espeak-ng")
        about.add_link("pycairo", "https://pycairo.readthedocs.io/")
        about.present(self)

    def show_shortcuts(self, action, param):
        builder = Gtk.Builder()
        builder.add_from_string('''
        <interface>
          <object class="GtkShortcutsWindow" id="shortcuts">
            <property name="modal">True</property>
            <child>
              <object class="GtkShortcutsSection">
                <property name="section-name">shortcuts</property>
                <child>
                  <object class="GtkShortcutsGroup">
                    <property name="title" translatable="yes">General</property>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title" translatable="yes">Preferences</property>
                        <property name="accelerator">&lt;Primary&gt;comma</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title" translatable="yes">Export Schedule</property>
                        <property name="accelerator">&lt;Primary&gt;e</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title" translatable="yes">Refresh</property>
                        <property name="accelerator">F5</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title" translatable="yes">Keyboard Shortcuts</property>
                        <property name="accelerator">&lt;Primary&gt;slash</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title" translatable="yes">About</property>
                        <property name="accelerator">F1</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title" translatable="yes">Quit</property>
                        <property name="accelerator">&lt;Primary&gt;q</property>
                      </object>
                    </child>
                  </object>
                </child>
              </object>
            </child>
          </object>
        </interface>
        ''')
        shortcuts = builder.get_object("shortcuts")
        shortcuts.set_transient_for(self)
        shortcuts.present()


CONFIG_DIR = Path(GLib.get_user_config_dir()) / "bildstod"


def _load_settings():
    path = CONFIG_DIR / "settings.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "settings.json").write_text(
        json.dumps(settings, indent=2, ensure_ascii=False))


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id="se.danielnylander.bildstod")
        self.settings = _load_settings()

    def do_activate(self):
        apply_large_text()
        window = self.props.active_window
        if not window:
            window = MainWindow(application=self)
        self._apply_theme()
        window.present()
        if not self.settings.get("welcome_shown"):
            self._show_welcome(window)

    def do_startup(self):
        Adw.Application.do_startup(self)

        for name, cb, accel in [
            ("quit", self.quit_app, ["<Primary>q"]),
            ("about", self.show_about, ["F1"]),
            ("shortcuts", self.show_shortcuts, ["<Primary>slash"]),
            ("preferences", self._on_preferences, ["<Primary>comma"]),
            ("refresh", self.refresh_data, ["F5"]),
            ("export", self.export_schedule, ["<Primary>e"]),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            if accel:
                self.set_accels_for_action(f"app.{name}", accel)

    def _apply_theme(self):
        theme = self.settings.get("theme", "system")
        mgr = Adw.StyleManager.get_default()
        schemes = {
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "dark": Adw.ColorScheme.FORCE_DARK,
            "system": Adw.ColorScheme.DEFAULT,
        }
        mgr.set_color_scheme(schemes.get(theme, Adw.ColorScheme.DEFAULT))

    def _show_welcome(self, win):
        dialog = Adw.Dialog()
        dialog.set_title(_("Welcome"))
        dialog.set_content_width(420)
        dialog.set_content_height(480)

        page = Adw.StatusPage()
        page.set_icon_name("se.danielnylander.bildstod")
        page.set_title(_("Welcome to Visual Support"))
        page.set_description(_(
            "Picture-based communication and scheduling.\n\n"
            "✓ Create visual schedules with pictograms\n"
            "✓ Search 13,000+ ARASAAC pictograms\n"
            "✓ Search in Swedish or English\n"
            "✓ Export and share schedules"
        ))

        btn = Gtk.Button(label=_("Get Started"))
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", self._on_welcome_close, dialog)
        page.set_child(btn)

        box = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_show_title(False)
        box.add_top_bar(hb)
        box.set_content(page)
        dialog.set_child(box)
        dialog.present(win)

    def _on_welcome_close(self, btn, dialog):
        self.settings["welcome_shown"] = True
        _save_settings(self.settings)
        dialog.close()

    def _on_preferences(self, *_):
        prefs = Adw.PreferencesDialog()
        prefs.set_title(_("Preferences"))

        basic = Adw.PreferencesPage()
        basic.set_title(_("General"))
        basic.set_icon_name("preferences-system-symbolic")

        appearance = Adw.PreferencesGroup()
        appearance.set_title(_("Appearance"))

        theme_row = Adw.ComboRow()
        theme_row.set_title(_("Theme"))
        theme_row.set_subtitle(_("Choose light, dark, or follow system"))
        theme_row.set_model(Gtk.StringList.new(
            [_("System"), _("Light"), _("Dark")]))
        cur = {"system": 0, "light": 1, "dark": 2}.get(
            self.settings.get("theme", "system"), 0)
        theme_row.set_selected(cur)
        theme_row.connect("notify::selected", self._on_theme_changed)
        appearance.add(theme_row)

        size_row = Adw.ComboRow()
        size_row.set_title(_("Icon Size"))
        size_row.set_subtitle(_("Size of pictogram icons"))
        size_row.set_model(Gtk.StringList.new(
            [_("Small"), _("Medium"), _("Large")]))
        cur_size = {"small": 0, "medium": 1, "large": 2}.get(
            self.settings.get("icon_size", "medium"), 1)
        size_row.set_selected(cur_size)
        size_row.connect("notify::selected", self._on_icon_size_changed)
        appearance.add(size_row)

        basic.add(appearance)

        # ── Speech ──
        speech_group = Adw.PreferencesGroup()
        speech_group.set_title(_("Speech"))

        engine_row = Adw.ComboRow()
        engine_row.set_title(_("Speech Engine"))
        engine_row.set_subtitle(_("Piper gives natural voices, espeak is robotic but lightweight"))
        engine_row.set_model(Gtk.StringList.new(
            [_("Automatic"), _("Piper (natural)"), _("espeak-ng (robotic)")]))
        cur_engine = {"auto": 0, "piper": 1, "espeak": 2}.get(
            self.settings.get("tts_engine", "auto"), 0)
        engine_row.set_selected(cur_engine)
        engine_row.connect("notify::selected", self._on_tts_engine_changed)
        speech_group.add(engine_row)

        speed_row = Adw.ActionRow()
        speed_row.set_title(_("Speech Speed"))
        speed_row.set_subtitle(_("Slower speech can be easier to understand"))
        speed_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 2.0, 0.1)
        speed_scale.set_value(self.settings.get("tts_speed", 1.0))
        speed_scale.set_size_request(200, -1)
        speed_scale.set_valign(Gtk.Align.CENTER)
        speed_scale.set_draw_value(True)
        speed_scale.connect("value-changed", self._on_tts_speed_changed)
        speed_row.add_suffix(speed_scale)
        speech_group.add(speed_row)

        basic.add(speech_group)

        prefs.add(basic)

        advanced = Adw.PreferencesPage()
        advanced.set_title(_("Advanced"))
        advanced.set_icon_name("applications-engineering-symbolic")

        cache_group = Adw.PreferencesGroup()
        cache_group.set_title(_("ARASAAC Cache"))
        cache_dir = Path(GLib.get_user_cache_dir()) / "arasaac"
        cache_size = sum(f.stat().st_size for f in cache_dir.glob("*")
                         if f.is_file()) if cache_dir.exists() else 0
        cache_row = Adw.ActionRow()
        cache_row.set_title(_("Cached pictograms"))
        cache_row.set_subtitle(f"{cache_size / (1024*1024):.1f} MB")
        clear_btn = Gtk.Button(label=_("Clear"))
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self._on_clear_cache, cache_row)
        cache_row.add_suffix(clear_btn)
        cache_group.add(cache_row)
        advanced.add(cache_group)

        notif_group = Adw.PreferencesGroup()
        notif_group.set_title(_("Notifications"))
        notif_row = Adw.SwitchRow()
        notif_row.set_title(_("Activity reminders"))
        notif_row.set_subtitle(_("Show notifications before scheduled activities"))
        notif_row.set_active(self.settings.get("notifications", True))
        notif_row.connect("notify::active", self._on_notif_changed)
        notif_group.add(notif_row)
        advanced.add(notif_group)

        debug_group = Adw.PreferencesGroup()
        debug_group.set_title(_("Developer"))
        debug_row = Adw.SwitchRow()
        debug_row.set_title(_("Debug mode"))
        debug_row.set_subtitle(_("Show extra logging in terminal"))
        debug_row.set_active(self.settings.get("debug", False))
        debug_row.connect("notify::active", self._on_debug_changed)
        debug_group.add(debug_row)
        advanced.add(debug_group)

        prefs.add(advanced)
        prefs.present(self.props.active_window)

    def _on_theme_changed(self, row, *_):
        themes = {0: "system", 1: "light", 2: "dark"}
        self.settings["theme"] = themes.get(row.get_selected(), "system")
        _save_settings(self.settings)
        self._apply_theme()

    def _on_icon_size_changed(self, row, *_):
        sizes = {0: "small", 1: "medium", 2: "large"}
        self.settings["icon_size"] = sizes.get(row.get_selected(), "medium")
        _save_settings(self.settings)

    def _on_notif_changed(self, row, *_):
        self.settings["notifications"] = row.get_active()
        _save_settings(self.settings)

    def _on_clear_cache(self, btn, row):
        cache_dir = Path(GLib.get_user_cache_dir()) / "arasaac"
        if cache_dir.exists():
            for f in cache_dir.glob("*"):
                if f.is_file():
                    f.unlink()
        row.set_subtitle("0.0 MB")
        btn.set_sensitive(False)
        btn.set_label(_("Cleared"))

    def _on_debug_changed(self, row, *_):
        self.settings["debug"] = row.get_active()
        _save_settings(self.settings)

    def quit_app(self, action, param):
        self.quit()

    def show_about(self, action, param):
        window = self.props.active_window
        if window:
            window.show_about(action, param)

    def show_shortcuts(self, action, param):
        window = self.props.active_window
        if window:
            window.show_shortcuts(action, param)

    def refresh_data(self, action, param):
        window = self.props.active_window
        if window:
            window._set_status(_("Refreshing..."))
            window.library_view.refresh()
            window.schedule_view.refresh()
            GLib.timeout_add_seconds(1, lambda: window._set_status(_("Ready")))

    def export_schedule(self, action, param):
        window = self.props.active_window
        if window:
            show_export_dialog(window, window.schedule_view.schedule, window._set_status)


def main():
    app = Application()
    return app.run(sys.argv)


if __name__ == '__main__':
    main()
