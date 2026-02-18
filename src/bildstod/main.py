#!/usr/bin/env python3
"""Bildstöd — Visual schedule and picture support tool for children with autism."""

import sys
import gettext
from datetime import datetime

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
from bildstod.schedule import ScheduleView
from bildstod.now_view import NowView
from bildstod.templates import (
    get_builtin_templates, list_user_templates,
    template_to_schedule, save_as_template,
)
from bildstod.export import show_export_dialog


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_default_size(1000, 700)
        self.set_title(_("Bildstöd"))

        # Initialize data
        self.library = PictureLibrary()

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
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About Bildstöd"), "app.about")
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

        main_box.append(self.view_stack)

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
        elif response == "save":
            schedule = self.schedule_view.schedule
            path = save_as_template(schedule)
            self._set_status(_("Template saved: %s") % path.name)

    def show_about(self, action, param):
        about = Adw.AboutDialog()
        about.set_application_name(_("Bildstöd"))
        about.set_application_icon("se.danielnylander.bildstod")
        about.set_developer_name("Daniel Nylander")
        about.set_developers(["Daniel Nylander <daniel@danielnylander.se>"])
        about.set_version(__version__)
        about.set_website("https://github.com/yeager/bildstod")
        about.set_issue_url("https://github.com/yeager/bildstod/issues")
        about.set_comments(
            _("Visual schedule and picture support tool for children with autism and language disorders.")
        )
        about.set_translator_credits(_("Translate this app: https://www.transifex.com/danielnylander/bildstod/"))
        about.set_license_type(Gtk.License.GPL_3_0)
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
                        <property name="title" translatable="yes">Show Shortcuts</property>
                        <property name="accelerator">&lt;Primary&gt;question</property>
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


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id="se.danielnylander.bildstod")

    def do_activate(self):
        window = self.props.active_window
        if not window:
            window = MainWindow(application=self)
        window.present()

    def do_startup(self):
        Adw.Application.do_startup(self)

        # Create actions
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self.quit_app)
        self.add_action(quit_action)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.show_about)
        self.add_action(about_action)

        shortcuts_action = Gio.SimpleAction.new("shortcuts", None)
        shortcuts_action.connect("activate", self.show_shortcuts)
        self.add_action(shortcuts_action)

        refresh_action = Gio.SimpleAction.new("refresh", None)
        refresh_action.connect("activate", self.refresh_data)
        self.add_action(refresh_action)

        export_action = Gio.SimpleAction.new("export", None)
        export_action.connect("activate", self.export_schedule)
        self.add_action(export_action)

        # Set keyboard shortcuts
        self.set_accels_for_action("app.quit", ["<Primary>q"])
        self.set_accels_for_action("app.shortcuts", ["<Primary>question"])
        self.set_accels_for_action("app.refresh", ["F5"])
        self.set_accels_for_action("app.export", ["<Primary>e"])

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
