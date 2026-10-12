"""Shared fixtures for testing multicursor.py without launching gedit.

Run with a headless display, for example:
    broadwayd :5 &
    GDK_BACKEND=broadway BROADWAY_DISPLAY=:5 .venv/bin/pytest
"""

import importlib.util
import pathlib
import sys
import time

import gi
import pytest

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkSource', '300')

from gi.repository import Gdk, Gtk, GtkSource  # noqa: E402

PLUGIN_PATH = pathlib.Path(__file__).resolve().parents[1] / 'multicursor.py'


class GeditView(GtkSource.View):
    # gedit's view is a GtkSourceView, which provides the undo and redo
    #  signals and a buffer with a style scheme
    pass


def _install_gedit_stub():
    # gedit's own GIR typelib isn't installed here, so provide the two
    # names the plugin needs: a view type and the ViewActivatable interface.
    class ViewActivatable(object):
        pass

    stub = type(sys)('gi.repository.Gedit')
    stub.View = GeditView
    stub.ViewActivatable = ViewActivatable
    sys.modules['gi.repository.Gedit'] = stub
    gi.repository.Gedit = stub


def _load_plugin_module():
    _install_gedit_stub()
    spec = importlib.util.spec_from_file_location('multicursor', PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


multicursor = _load_plugin_module()


def pump(until=None, timeout=2.0):
    """Process GTK events until `until()` is true or the timeout passes."""
    deadline = time.monotonic() + timeout
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration()
        if until is None or until() or time.monotonic() > deadline:
            return
        time.sleep(0.005)


class FakePointerEvent(object):
    """Stands in for a GDK pointer event, with the methods the plugin calls."""

    def __init__(self, event_type, x, y, ctrl=False, button1=False):
        self.type = event_type
        self._x = x
        self._y = y
        self._state = 0
        if ctrl:
            self._state |= Gdk.ModifierType.CONTROL_MASK
        if button1:
            self._state |= Gdk.ModifierType.BUTTON1_MASK

    def get_state(self):
        return (True, self._state)

    def get_coords(self):
        return (True, self._x, self._y)


class FakeButtonEvent(FakePointerEvent):

    def __init__(self, x, y, ctrl=False):
        super(FakeButtonEvent, self).__init__(
            Gdk.EventType.BUTTON_PRESS, x, y, ctrl=ctrl)


def window_point_for_offset(view, offset):
    """Return window coordinates of the character at `offset` in the buffer."""
    buf = view.get_buffer()
    rect = view.get_iter_location(buf.get_iter_at_offset(offset))
    return view.buffer_to_window_coords(
        Gtk.TextWindowType.TEXT, rect.x + 1, rect.y + 1)


class Editor(object):
    """A real TextView with the plugin attached, as gedit would do."""

    def __init__(self, text):
        self.window = Gtk.Window()
        self.view = GeditView()
        self.view.get_buffer().set_text(text)
        self.window.add(self.view)
        self.window.set_default_size(400, 300)
        self.window.show_all()
        pump(lambda: self.view.get_window(Gtk.TextWindowType.TEXT) is not None)

        self.plugin = multicursor.MultiCursor()
        self.plugin.view = self.view
        self.plugin.do_activate()

    @property
    def buffer(self):
        return self.view.get_buffer()

    def iter_at(self, offset):
        return self.buffer.get_iter_at_offset(offset)

    def cursor_offsets(self):
        return sorted(c.tag.get_start_iter().get_offset()
                      for c in self.plugin.cursors)

    def use_scheme(self, scheme_id):
        scheme = GtkSource.StyleSchemeManager.get_default().get_scheme(scheme_id)
        self.buffer.set_style_scheme(scheme)

    def cursor_selections(self):
        return sorted((c.tag.get_start_iter().get_offset(),
                       c.tag.get_end_iter().get_offset())
                      for c in self.plugin.cursors)

    def main_selection(self):
        bounds = self.buffer.get_selection_bounds()
        if not bounds:
            return None
        return (bounds[0].get_offset(), bounds[1].get_offset())

    def add_cursor_at(self, offset):
        it = self.iter_at(offset)
        self.plugin.add_cursor(it, it)

    def type_text(self, text):
        """Type text the way GTK does: one user action, replacing any selection."""
        self.buffer.begin_user_action()
        self.buffer.insert_interactive_at_cursor(text, len(text.encode()), True)
        self.buffer.end_user_action()

    def delete_range(self, start, end):
        self.buffer.begin_user_action()
        self.buffer.delete(self.iter_at(start), self.iter_at(end))
        self.buffer.end_user_action()

    def close(self):
        self.plugin.do_deactivate()
        self.window.destroy()


@pytest.fixture
def make_editor():
    editors = []

    def make(text):
        editor = Editor(text)
        editors.append(editor)
        return editor

    yield make

    for editor in editors:
        editor.close()
