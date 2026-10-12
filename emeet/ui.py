"""GTK4 + libadwaita window: live preview on the left, controls and presets on the right."""
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

# The vulkan renderer crashes with gtk4paintablesink textures. The GL renderer was called
# "ngl" up to GTK 4.18 and "gl" from 4.20; GTK reads this when the first window is realized.
os.environ.setdefault("GSK_RENDERER", "gl" if Gtk.MINOR_VERSION >= 20 else "ngl")

from .pipeline import default_size, pipeline_desc  # noqa: E402
from .quirks import ZOOM_HINT, zoom_has_no_effect  # noqa: E402

GROUPS = {
    "Image": ["brightness", "contrast", "sharpness", "saturation", "hue", "gamma"],
    "Color and light": ["white_balance_automatic", "white_balance_temperature", "auto_exposure", "exposure_time_absolute", "gain", "backlight_compensation", "power_line_frequency"],
    "Focus and zoom": ["focus_automatic_continuous", "focus_absolute", "zoom_absolute"],
}
LABELS = {
    "auto_exposure": "Automatic exposure", "exposure_time_absolute": "Exposure time", "power_line_frequency": "Anti-flicker",
    "white_balance_automatic": "Automatic white balance", "white_balance_temperature": "Temperature",
    "focus_automatic_continuous": "Autofocus", "focus_absolute": "Focus", "zoom_absolute": "Zoom",
    "backlight_compensation": "Backlight compensation",
}
AUTO_EXPOSURE_ON, AUTO_EXPOSURE_OFF = 3, 1  # UVC menu: 3 = aperture priority, 1 = manual
SIDEBAR_WIDTH = 420
CSS = ".preview-card { background: #0a0a0a; border-radius: 12px; }"


def label_for(name):
    return LABELS.get(name, name.replace("_", " ").capitalize())


def fmt_value(c, v):
    """Human value for a control: zoom as a factor, everything else as a percent of its range."""
    if c["name"] == "zoom_absolute":
        return f"{v / 100:.2f}×"
    return f"{round((v - c['min']) * 100 / (c['max'] - c['min']))}%"


def group_controls(controls):
    """Yield (group title, [control...]) following GROUPS, unknown controls last under Other."""
    by_name = {c["name"]: c for c in controls}
    known = {n for names in GROUPS.values() for n in names}
    groups = dict(GROUPS)
    groups["Other"] = [n for n in by_name if n not in known]
    for title, names in groups.items():
        found = [by_name[n] for n in names if n in by_name]
        if found:
            yield title, found


class Guard:
    """Blocks widget callbacks while the code itself is updating widgets."""

    def __init__(self):
        self.busy = False

    def __call__(self, fn):
        return lambda *a: None if self.busy else fn(*a)

    def run(self, fn):
        self.busy = True
        try:
            fn()
        finally:
            self.busy = False


class ControlPanel:
    """Adw.PreferencesPage of sliders, switches and combos bound to the camera's controls."""

    def __init__(self, camera, cam_name=""):
        self.camera, self.cam_name = camera, cam_name
        self.guard = Guard()
        self.widgets = {}  # name -> (row, setter)
        self.hints = {}  # name -> hidden Gtk.Label under the slider
        self.blocked = set()  # controls the current stream mode ignores (quirks)
        self.page = Adw.PreferencesPage()
        for title, controls in group_controls(camera.controls()):
            group = Adw.PreferencesGroup(title=title)
            for c in controls:
                if row := self._row(c):
                    group.add(row)
            self.page.add(group)
        self.refresh()

    def set_ctrl(self, name, value):
        self.camera.set(name, value)
        GLib.idle_add(self.refresh)  # auto_* toggles flip siblings' inactive flag

    def apply(self, values):
        self.camera.apply(values)
        self.refresh()

    def refresh(self):
        def do():
            for c in self.camera.controls():
                if c["name"] in self.widgets:
                    row, setter = self.widgets[c["name"]]
                    row.set_sensitive(not c["inactive"] and c["name"] not in self.blocked)
                    setter(c)
        self.guard.run(do)
        return False

    def set_stream(self, fmt, w, h, fps):
        """Grey out controls the camera firmware ignores in this stream mode, with a hint."""
        self.blocked = {"zoom_absolute"} if zoom_has_no_effect(self.cam_name, fmt, w, h, fps) else set()
        for name, hint in self.hints.items():
            hint.set_visible(name in self.blocked)
        self.refresh()

    def _row(self, c):
        name, title = c["name"], label_for(c["name"])
        if c["type"] == "int" and c["min"] < c["max"]:
            return self._slider_row(c, title)
        if name == "auto_exposure":
            row = Adw.SwitchRow(title=title)
            row.connect("notify::active", self.guard(lambda r, _p: self.set_ctrl(name, AUTO_EXPOSURE_ON if r.get_active() else AUTO_EXPOSURE_OFF)))
            self.widgets[name] = (row, lambda c: row.set_active(c["value"] == AUTO_EXPOSURE_ON))
            return row
        if c["type"] == "bool":
            row = Adw.SwitchRow(title=title)
            row.connect("notify::active", self.guard(lambda r, _p: self.set_ctrl(name, r.get_active())))
            self.widgets[name] = (row, lambda c: row.set_active(bool(c["value"])))
            return row
        if c["type"] == "menu":
            keys = list(c["menu"])
            row = Adw.ComboRow(title=title, model=Gtk.StringList.new(list(c["menu"].values())))
            row.connect("notify::selected", self.guard(lambda r, _p: self.set_ctrl(name, keys[r.get_selected()])))
            self.widgets[name] = (row, lambda c: row.set_selected(keys.index(c["value"])))
            return row
        return None

    def _slider_row(self, c, title):
        name = c["name"]
        row = Gtk.ListBoxRow(activatable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=8, margin_bottom=8, margin_start=14, margin_end=14)
        head = Gtk.Box()
        head.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        value = Gtk.Label(label=fmt_value(c, c["value"]))
        value.add_css_class("dim-label")
        value.add_css_class("numeric")
        head.append(value)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, c["min"], c["max"], c["step"] or 1)
        scale.add_mark(c["default"], Gtk.PositionType.BOTTOM, None)

        def changed(s):
            value.set_label(fmt_value(c, int(s.get_value())))
            if not self.guard.busy:
                self.set_ctrl(name, s.get_value())

        scale.connect("value-changed", changed)
        box.append(head)
        box.append(scale)
        if name == "zoom_absolute":
            hint = Gtk.Label(label=ZOOM_HINT, xalign=0, wrap=True, visible=False)
            hint.add_css_class("dim-label")
            hint.add_css_class("caption")
            box.append(hint)
            self.hints[name] = hint
        row.set_child(box)
        self.widgets[name] = (row, lambda c: scale.set_value(c["value"]))
        return row


class PresetPanel:
    """Save / apply / delete named control sets."""

    def __init__(self, store, controls, get_window):
        self.store, self.controls, self.get_window = store, controls, get_window
        self.page = Adw.PreferencesPage()
        top = Adw.PreferencesGroup()
        save = Gtk.Button(label="Save current values as preset", halign=Gtk.Align.CENTER)
        save.add_css_class("pill")
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda _b: self.ask_name())
        top.add(save)
        self.page.add(top)
        self.group = Adw.PreferencesGroup(title="Saved presets", description="Click a preset to apply it")
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.group.add(self.list)
        self.page.add(self.group)
        self.reload()

    def reload(self):
        while child := self.list.get_first_child():
            self.list.remove(child)
        for name in self.store.names():
            row = Adw.ActionRow(title=name, subtitle=f"{len(self.store.get(name))} controls", activatable=True)
            row.connect("activated", lambda _r, n=name: self.controls.apply(self.store.get(n)))
            rm = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Delete preset")
            rm.add_css_class("flat")
            rm.connect("clicked", lambda _b, n=name: self.delete(n))
            row.add_suffix(rm)
            self.list.append(row)
        self.group.set_visible(bool(self.store.names()))

    def save(self, name):
        self.store.save(name, self.controls.camera.snapshot())
        self.reload()

    def delete(self, name):
        self.store.delete(name)
        self.reload()

    def ask_name(self):
        dlg = Adw.AlertDialog(heading="Save preset", body="Stores every active control value.")
        entry = Gtk.Entry(placeholder_text="Name")
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("save", "Save")
        dlg.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("save")
        dlg.connect("response", lambda _d, resp: resp == "save" and entry.get_text().strip() and self.save(entry.get_text().strip()))
        dlg.present(self.get_window())


class StreamBar:
    """Format / resolution / fps dropdowns plus a mirror switch. Calls on_change(fmt, w, h, fps, mirror).

    `initial` is a saved (fmt, w, h, fps, mirror); anything not offered by the camera falls back to 720p.
    """

    def __init__(self, formats, on_change, initial=None):
        self.formats, self.on_change = formats, on_change
        self.guard = Guard()
        self.fmt = Gtk.DropDown.new_from_strings(list(formats))
        self.res = Gtk.DropDown()
        self.fps = Gtk.DropDown()
        self.mirror = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.box = Gtk.Box(spacing=8, margin_top=12)
        for w in (self.fmt, self.res, self.fps):
            self.box.append(w)
        self.box.append(Gtk.Box(hexpand=True))
        self.box.append(Gtk.Label(label="Mirror"))
        self.box.append(self.mirror)
        self.fmt.connect("notify::selected", self.guard(lambda *_: self.fmt_changed()))
        self.res.connect("notify::selected", self.guard(lambda *_: self.res_changed()))
        self.fps.connect("notify::selected", self.guard(lambda *_: self.emit()))
        self.mirror.connect("notify::active", self.guard(lambda *_: self.emit()))
        self.select(*self.resolve(initial))

    def resolve(self, initial):
        """(fmt, size, fps, mirror) for a saved mode if the camera offers it, else the default."""
        if initial:
            fmt, w, h, fps, mirror = initial
            if fmt in self.formats and (w, h) in self.formats[fmt] and fps in self.formats[fmt][(w, h)]:
                return fmt, (w, h), fps, mirror
        fmt = list(self.formats)[0]
        sizes = list(self.formats[fmt])
        size = sizes[default_size(sizes)]
        return fmt, size, self.formats[fmt][size][0], False

    def select(self, fmt, size, fps, mirror):
        """Set all four widgets without firing callbacks, then emit once.

        Models are only replaced when their key changes: replacing a dropdown's model from
        inside its own notify handler re-queues the notification and loops forever.
        """
        sizes, rates = list(self.formats[fmt]), self.formats[fmt][size]

        def do():
            self.fmt.set_selected(list(self.formats).index(fmt))
            if getattr(self, "_res_key", None) != fmt:
                self.res.set_model(Gtk.StringList.new([f"{w}×{h}" for w, h in sizes]))
                self._res_key = fmt
            self.res.set_selected(sizes.index(size))
            if getattr(self, "_fps_key", None) != (fmt, size):
                self.fps.set_model(Gtk.StringList.new([f"{f:g} fps" for f in rates]))
                self._fps_key = (fmt, size)
            self.fps.set_selected(rates.index(fps))
            self.mirror.set_active(mirror)

        self.guard.run(do)
        self.emit()

    def current(self):
        fmt = list(self.formats)[self.fmt.get_selected()]
        size = list(self.formats[fmt])[self.res.get_selected()]
        return fmt, *size, self.formats[fmt][size][self.fps.get_selected()], self.mirror.get_active()

    def emit(self):
        self.on_change(*self.current())

    def res_changed(self):
        fmt = list(self.formats)[self.fmt.get_selected()]
        size = list(self.formats[fmt])[self.res.get_selected()]
        self.select(fmt, size, self.formats[fmt][size][0], self.mirror.get_active())

    def fmt_changed(self):
        fmt = list(self.formats)[self.fmt.get_selected()]
        sizes = list(self.formats[fmt])
        size = sizes[default_size(sizes)]
        self.select(fmt, size, self.formats[fmt][size][0], self.mirror.get_active())


class Preview:
    """Gtk.Picture fed by a GStreamer pipeline.

    The picture sits as an overlay on an empty expanding box, so the layout never
    follows the frame size: switching resolution (paintable briefly 0×0) or
    picking a smaller mode must not move the sidebar.
    """

    def __init__(self, dev):
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        self.Gst, self.dev, self.pipe = Gst, dev, None
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN)
        self.widget = Gtk.Overlay(child=Gtk.Box(hexpand=True, vexpand=True))
        self.widget.add_overlay(self.picture)

    def start(self, fmt, w, h, fps, mirror):
        self.stop()
        self.pipe = self.Gst.parse_launch(pipeline_desc(self.dev, fmt, w, h, fps, mirror))
        self.picture.set_paintable(self.pipe.get_by_name("sink").props.paintable)
        self.pipe.set_state(self.Gst.State.PLAYING)

    def stop(self):
        if self.pipe:
            self.pipe.set_state(self.Gst.State.NULL)
            self.pipe = None


class App(Adw.Application):
    def __init__(self, camera, store, title, settings=None):
        super().__init__(application_id="io.github.breno5g.emeet")
        self.camera, self.store, self.title, self.settings = camera, store, title, settings
        self.win = None
        self.connect("activate", self.activate)

    def activate(self, _app):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        preview = Preview(self.camera.dev)
        card = Gtk.Box(hexpand=True, vexpand=True, overflow=Gtk.Overflow.HIDDEN)
        card.add_css_class("preview-card")
        card.append(preview.widget)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        left.append(card)

        controls = ControlPanel(self.camera, self.title)
        presets = PresetPanel(self.store, controls, lambda: self.win)
        # Explicit hexpand=False stops the rows' expanding labels from propagating up; natural width stays SIDEBAR_WIDTH,
        # so the preview column always takes the rest and never moves when the frame size changes.
        stack = Adw.ViewStack(hexpand=False)
        for page, name, title, icon in ((controls.page, "video", "Video", "video-display-symbolic"), (presets.page, "presets", "Presets", "starred-symbolic")):
            stack.add_titled_with_icon(Gtk.ScrolledWindow(child=page, width_request=SIDEBAR_WIDTH, propagate_natural_width=False), name, title, icon)

        content = Gtk.Box()
        content.append(left)
        content.append(stack)

        reset = Gtk.Button(icon_name="edit-undo-symbolic", tooltip_text="Reset all controls to defaults")
        reset.connect("clicked", lambda _b: controls.apply(self.camera.defaults()))
        header = Adw.HeaderBar(title_widget=Adw.ViewSwitcher(stack=stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        header.pack_end(reset)
        view = Adw.ToolbarView(content=content)
        view.add_top_bar(header)

        self.win = Adw.ApplicationWindow(application=self, content=view, title=self.title, default_width=1280, default_height=820)
        self.win.connect("close-request", lambda _w: preview.stop() or False)

        def stream_changed(fmt, w, h, fps, mirror):
            preview.start(fmt, w, h, fps, mirror)
            controls.set_stream(fmt, w, h, fps)
            if self.settings:
                self.settings.set("stream", [fmt, w, h, fps, mirror])  # becomes the mode the app opens with next time

        initial = self.settings.stream() if self.settings else None
        left.append(StreamBar(self.camera.formats(), stream_changed, initial).box)  # builds and starts the first stream
        self.win.present()
