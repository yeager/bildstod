"""Export/print functionality for Bildstöd schedules."""

import csv
import io
import json
import os
from datetime import datetime

import gettext
_ = gettext.gettext

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

from bildstod.library import get_images_dir


def schedule_to_csv(schedule):
    """Export schedule as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([_("Time"), _("Activity"), _("Duration (min)"), _("Category"), _("Done")])
    for item in schedule.items:
        writer.writerow([
            item.time_str,
            item.label,
            item.duration,
            item.category,
            _("Yes") if item.done else _("No"),
        ])
    return output.getvalue()


def schedule_to_json(schedule):
    """Export schedule as JSON string."""
    return json.dumps(schedule.to_dict(), indent=2, ensure_ascii=False)


def export_schedule_pdf(schedule, output_path):
    """Export schedule as a visual PDF using cairo."""
    try:
        import cairo
    except ImportError:
        try:
            import cairocffi as cairo
        except ImportError:
            return False

    try:
        from gi.repository import GdkPixbuf
    except Exception:
        pass

    width, height = 595, 842  # A4 in points
    surface = cairo.PDFSurface(output_path, width, height)
    ctx = cairo.Context(surface)

    # Title
    ctx.set_font_size(24)
    ctx.move_to(40, 50)
    ctx.show_text(schedule.name)

    ctx.set_font_size(14)
    ctx.move_to(40, 75)
    ctx.show_text(schedule.date)

    y = 110
    row_height = 80

    for item in schedule.items:
        if y + row_height > height - 40:
            surface.show_page()
            y = 40

        # Time
        ctx.set_font_size(16)
        ctx.move_to(40, y + 30)
        ctx.show_text(item.time_str)

        # Try to draw image
        img_path = str(get_images_dir() / item.image_filename) if item.image_filename else ""
        if img_path and os.path.exists(img_path) and not img_path.endswith(".svg"):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(img_path, 60, 60, True)
                # Convert pixbuf to cairo surface
                img_surface = cairo.ImageSurface(
                    cairo.FORMAT_ARGB32, pixbuf.get_width(), pixbuf.get_height()
                )
                # Simple pixel copy - for production use GdkPixbuf integration
                ctx.save()
                ctx.translate(100, y)
                ctx.set_source_surface(img_surface, 0, 0)
                ctx.paint()
                ctx.restore()
            except Exception:
                pass

        # Activity name
        ctx.set_font_size(18)
        if item.done:
            ctx.set_source_rgb(0.6, 0.6, 0.6)
        else:
            ctx.set_source_rgb(0, 0, 0)
        ctx.move_to(170, y + 30)
        ctx.show_text(item.label)

        # Duration
        ctx.set_font_size(12)
        ctx.set_source_rgb(0.5, 0.5, 0.5)
        ctx.move_to(170, y + 50)
        ctx.show_text(_("%d minutes") % item.duration)

        # Done indicator
        if item.done:
            ctx.set_source_rgb(0.18, 0.76, 0.49)
            ctx.move_to(500, y + 30)
            ctx.show_text("✓")

        ctx.set_source_rgb(0, 0, 0)

        # Separator line
        ctx.set_line_width(0.5)
        ctx.set_source_rgb(0.85, 0.85, 0.85)
        ctx.move_to(40, y + row_height - 5)
        ctx.line_to(width - 40, y + row_height - 5)
        ctx.stroke()
        ctx.set_source_rgb(0, 0, 0)

        y += row_height

    surface.finish()
    return True


def show_export_dialog(window, schedule, status_callback=None):
    """Show export dialog with CSV/JSON/PDF options."""
    dialog = Adw.AlertDialog.new(
        _("Export Schedule"),
        _("Choose export format:")
    )

    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("csv", _("CSV"))
    dialog.add_response("json", _("JSON"))
    dialog.add_response("pdf", _("PDF"))
    dialog.set_default_response("json")
    dialog.set_close_response("cancel")

    dialog.connect("response", _on_export_response, window, schedule, status_callback)
    dialog.present(window)


def _on_export_response(dialog, response, window, schedule, status_callback):
    if response == "cancel":
        return

    if response == "csv":
        _save_text_export(window, schedule, "csv", schedule_to_csv, status_callback)
    elif response == "json":
        _save_text_export(window, schedule, "json", schedule_to_json, status_callback)
    elif response == "pdf":
        _save_pdf_export(window, schedule, status_callback)


def _save_text_export(window, schedule, ext, converter, status_callback):
    dialog = Gtk.FileDialog.new()
    dialog.set_title(_("Save Export"))
    safe_name = schedule.name.replace(" ", "_")
    dialog.set_initial_name(f"{schedule.date}_{safe_name}.{ext}")
    dialog.save(window, None, _on_text_save_done, schedule, converter, ext, status_callback)


def _on_text_save_done(dialog, result, schedule, converter, ext, status_callback):
    try:
        gfile = dialog.save_finish(result)
    except GLib.Error:
        return
    try:
        content = converter(schedule)
        with open(gfile.get_path(), "w") as f:
            f.write(content)
        if status_callback:
            now = datetime.now().strftime("%H:%M:%S")
            status_callback(_("Exported %s at %s") % (ext.upper(), now))
    except Exception as e:
        if status_callback:
            status_callback(_("Export error: %s") % str(e))


def _save_pdf_export(window, schedule, status_callback):
    dialog = Gtk.FileDialog.new()
    dialog.set_title(_("Save PDF"))
    safe_name = schedule.name.replace(" ", "_")
    dialog.set_initial_name(f"{schedule.date}_{safe_name}.pdf")
    dialog.save(window, None, _on_pdf_save_done, schedule, status_callback)


def _on_pdf_save_done(dialog, result, schedule, status_callback):
    try:
        gfile = dialog.save_finish(result)
    except GLib.Error:
        return
    try:
        success = export_schedule_pdf(schedule, gfile.get_path())
        if success and status_callback:
            now = datetime.now().strftime("%H:%M:%S")
            status_callback(_("PDF exported at %s") % now)
        elif not success and status_callback:
            status_callback(_("PDF export requires cairo. Install pycairo."))
    except Exception as e:
        if status_callback:
            status_callback(_("Export error: %s") % str(e))
