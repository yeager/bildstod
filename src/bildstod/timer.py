"""Timer/countdown for current activity in Bildstöd."""

import gettext
_ = gettext.gettext

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib


class TimerWidget(Gtk.Box):
    """Visual countdown timer with color-changing progress bar."""

    def __init__(self, status_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.status_callback = status_callback

        self.total_seconds = 0
        self.remaining_seconds = 0
        self.running = False
        self.timer_id = None
        self._on_finished = None
        self._on_skip = None

        # Big time display
        self.time_label = Gtk.Label(label="00:00")
        self.time_label.add_css_class("title-1")
        self.time_label.set_markup('<span size="72000" weight="bold">00:00</span>')
        self.append(self.time_label)

        # Progress bar
        self.progress = Gtk.ProgressBar()
        self.progress.set_size_request(300, 24)
        self.progress.set_show_text(False)
        self.append(self.progress)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        self.pause_btn = Gtk.Button(label=_("Pause"))
        self.pause_btn.set_icon_name("media-playback-pause-symbolic")
        self.pause_btn.connect("clicked", self._on_pause)
        self.pause_btn.set_size_request(120, 48)
        btn_box.append(self.pause_btn)

        self.skip_btn = Gtk.Button(label=_("Skip"))
        self.skip_btn.set_icon_name("media-skip-forward-symbolic")
        self.skip_btn.connect("clicked", self._on_skip_clicked)
        self.skip_btn.set_size_request(120, 48)
        btn_box.append(self.skip_btn)

        self.append(btn_box)

    def set_on_finished(self, callback):
        self._on_finished = callback

    def set_on_skip(self, callback):
        self._on_skip = callback

    def start(self, minutes):
        """Start countdown for given minutes."""
        self.total_seconds = int(minutes * 60)
        self.remaining_seconds = self.total_seconds
        self.running = True
        self.pause_btn.set_label(_("Pause"))
        self.pause_btn.set_icon_name("media-playback-pause-symbolic")
        self._update_display()
        if self.timer_id:
            GLib.source_remove(self.timer_id)
        self.timer_id = GLib.timeout_add(1000, self._tick)

    def stop(self):
        self.running = False
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def _tick(self):
        if not self.running:
            return False
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.remaining_seconds = 0
            self.running = False
            self._update_display()
            self._play_notification()
            if self._on_finished:
                self._on_finished()
            return False
        self._update_display()
        return True

    def _update_display(self):
        mins = self.remaining_seconds // 60
        secs = self.remaining_seconds % 60
        time_str = f"{mins:02d}:{secs:02d}"

        # Color based on progress
        if self.total_seconds > 0:
            fraction = self.remaining_seconds / self.total_seconds
        else:
            fraction = 0

        if fraction > 0.5:
            color = "#2ec27e"  # green
        elif fraction > 0.2:
            color = "#e5a50a"  # yellow
        else:
            color = "#e01b24"  # red

        self.time_label.set_markup(
            f'<span size="72000" weight="bold" foreground="{color}">{time_str}</span>'
        )

        if self.total_seconds > 0:
            self.progress.set_fraction(self.remaining_seconds / self.total_seconds)

        # Update progress bar CSS for color
        self.progress.remove_css_class("success")
        self.progress.remove_css_class("warning")
        self.progress.remove_css_class("error")
        if fraction > 0.5:
            self.progress.add_css_class("success")
        elif fraction > 0.2:
            self.progress.add_css_class("warning")
        else:
            self.progress.add_css_class("error")

    def _on_pause(self, btn):
        if self.running:
            self.running = False
            self.pause_btn.set_label(_("Resume"))
            self.pause_btn.set_icon_name("media-playback-start-symbolic")
        else:
            self.running = True
            self.pause_btn.set_label(_("Pause"))
            self.pause_btn.set_icon_name("media-playback-pause-symbolic")
            self.timer_id = GLib.timeout_add(1000, self._tick)

    def _on_skip_clicked(self, btn):
        self.stop()
        if self._on_skip:
            self._on_skip()

    def _play_notification(self):
        """Play a system bell / notification sound."""
        try:
            import subprocess
            # Try system bell
            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                # Fallback: terminal bell
                print("\a", end="", flush=True)
            except Exception:
                pass
        if self.status_callback:
            self.status_callback(_("Timer finished!"))
