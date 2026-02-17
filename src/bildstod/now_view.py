"""Now View — full-screen current activity display for Bildstöd."""

import os
import gettext
_ = gettext.gettext

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, Gdk, GdkPixbuf

from bildstod.library import get_images_dir
from bildstod.timer import TimerWidget


class NowView(Gtk.Box):
    """Full-screen display of the current activity with timer."""

    def __init__(self, status_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.set_margin_top(48)
        self.set_margin_bottom(48)
        self.set_margin_start(48)
        self.set_margin_end(48)
        self.status_callback = status_callback
        self.schedule = None
        self.current_item = None
        self._on_done = None
        self._on_skip = None

        # Current activity image
        self.activity_image = Gtk.Picture()
        self.activity_image.set_size_request(256, 256)
        self.activity_image.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.append(self.activity_image)

        # Activity name — big text
        self.activity_label = Gtk.Label(label=_("No activity"))
        self.activity_label.set_markup(
            '<span size="36000" weight="bold">' + _("No activity") + '</span>'
        )
        self.append(self.activity_label)

        # Timer
        self.timer = TimerWidget(status_callback=status_callback)
        self.timer.set_on_finished(self._timer_finished)
        self.timer.set_on_skip(self._skip_activity)
        self.append(self.timer)

        # Done button
        self.done_btn = Gtk.Button(label=_("Done!"))
        self.done_btn.add_css_class("suggested-action")
        self.done_btn.add_css_class("pill")
        self.done_btn.set_size_request(200, 64)
        self.done_btn.set_halign(Gtk.Align.CENTER)
        self.done_btn.connect("clicked", self._on_done_clicked)
        self.append(self.done_btn)

        # Next activity preview
        self.next_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.next_box.set_halign(Gtk.Align.CENTER)

        next_label = Gtk.Label(label=_("Next:"))
        next_label.add_css_class("dim-label")
        next_label.add_css_class("title-4")
        self.next_box.append(next_label)

        self.next_image = Gtk.Picture()
        self.next_image.set_size_request(48, 48)
        self.next_image.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.next_box.append(self.next_image)

        self.next_name = Gtk.Label(label="")
        self.next_name.add_css_class("title-4")
        self.next_box.append(self.next_name)

        self.append(self.next_box)

    def set_on_done(self, callback):
        self._on_done = callback

    def set_on_skip(self, callback):
        self._on_skip = callback

    def update_schedule(self, schedule):
        """Update with a new schedule, show current activity."""
        self.schedule = schedule
        self.current_item = schedule.get_current_activity() if schedule else None
        self._update_display()

    def _update_display(self):
        if not self.current_item:
            self.activity_label.set_markup(
                '<span size="36000" weight="bold">' + _("All done! 🎉") + '</span>'
            )
            self.activity_image.set_paintable(None)
            self.timer.stop()
            self.done_btn.set_sensitive(False)
            self.next_box.set_visible(False)
            return

        item = self.current_item
        self.done_btn.set_sensitive(True)

        # Update image
        img_path = str(get_images_dir() / item.image_filename) if item.image_filename else ""
        if img_path and os.path.exists(img_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_path, 256, 256, True)
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                self.activity_image.set_paintable(texture)
            except Exception:
                self.activity_image.set_paintable(None)
        else:
            self.activity_image.set_paintable(None)

        # Update label
        self.activity_label.set_markup(
            f'<span size="36000" weight="bold">{GLib_markup_escape(item.label)}</span>'
        )

        # Start timer
        if item.duration > 0:
            self.timer.start(item.duration)
            self.timer.set_visible(True)
        else:
            self.timer.set_visible(False)

        # Next activity preview
        if self.schedule:
            next_item = self.schedule.get_next_activity(item)
            if next_item:
                self.next_box.set_visible(True)
                self.next_name.set_text(next_item.label)
                next_img = str(get_images_dir() / next_item.image_filename) if next_item.image_filename else ""
                if next_img and os.path.exists(next_img):
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(next_img, 48, 48, True)
                        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                        self.next_image.set_paintable(texture)
                    except Exception:
                        self.next_image.set_paintable(None)
                else:
                    self.next_image.set_paintable(None)
            else:
                self.next_box.set_visible(False)
        else:
            self.next_box.set_visible(False)

    def _on_done_clicked(self, btn):
        if self.current_item:
            self.current_item.done = True
            if self._on_done:
                self._on_done(self.current_item)
            # Move to next
            if self.schedule:
                self.current_item = self.schedule.get_current_activity()
            self._update_display()

    def _timer_finished(self):
        """Called when timer runs out."""
        if self.status_callback:
            self.status_callback(_("Time's up for: %s") % (self.current_item.label if self.current_item else ""))

    def _skip_activity(self):
        """Skip to next activity."""
        if self.current_item:
            self.current_item.done = True
            if self._on_skip:
                self._on_skip(self.current_item)
            if self.schedule:
                self.current_item = self.schedule.get_current_activity()
            self._update_display()


def GLib_markup_escape(text):
    """Escape text for Pango markup."""
    from gi.repository import GLib
    return GLib.markup_escape_text(text)
