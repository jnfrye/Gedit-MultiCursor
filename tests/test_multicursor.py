from gi.repository import Gdk, Gtk

from conftest import FakeButtonEvent, window_point_for_offset


def test_ctrl_click_adds_cursor_where_clicked(make_editor):
    editor = make_editor("first line\nsecond line\nthird")
    x, y = window_point_for_offset(editor.view, 8)

    handled = editor.plugin.on_event(editor.view, FakeButtonEvent(x, y, ctrl=True))

    assert handled is True
    assert editor.cursor_offsets() == [8]


def test_plain_click_clears_extra_cursors(make_editor):
    editor = make_editor("abc\nabc\nabc")
    editor.add_cursor_at(5)
    editor.add_cursor_at(9)
    x, y = window_point_for_offset(editor.view, 1)

    handled = editor.plugin.on_event(editor.view, FakeButtonEvent(x, y, ctrl=False))

    assert handled is False
    assert editor.cursor_offsets() == []


def test_escape_clears_extra_cursors(make_editor):
    editor = make_editor("abc\nabc\nabc")
    editor.add_cursor_at(5)
    editor.add_cursor_at(9)
    _, entries = Gdk.Keymap.get_default().get_entries_for_keyval(Gdk.KEY_Escape)

    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.key.keyval = Gdk.KEY_Escape
    event.key.hardware_keycode = entries[0].keycode
    event.key.state = 0
    handled = editor.plugin.on_key_press(editor.view, event)

    assert handled is True
    assert editor.cursor_offsets() == []


def test_typing_inserts_at_every_cursor(make_editor):
    editor = make_editor("abc\nabc\nabc")
    editor.buffer.place_cursor(editor.iter_at(1))
    editor.add_cursor_at(5)
    editor.add_cursor_at(9)

    editor.type_text("X")

    assert editor.buffer.get_text(
        editor.buffer.get_start_iter(), editor.buffer.get_end_iter(), True
    ) == "aXbc\naXbc\naXbc"


def test_backspace_deletes_at_every_cursor(make_editor):
    editor = make_editor("abc\nabc\nabc")
    editor.buffer.place_cursor(editor.iter_at(3))
    editor.add_cursor_at(7)
    editor.add_cursor_at(11)

    editor.delete_range(2, 3)

    assert editor.buffer.get_text(
        editor.buffer.get_start_iter(), editor.buffer.get_end_iter(), True
    ) == "ab\nab\nab"


def test_arrow_movement_moves_every_cursor(make_editor):
    editor = make_editor("abc\nabc\nabc")
    editor.add_cursor_at(1)
    editor.add_cursor_at(5)

    editor.plugin.mc_move_cursor(
        editor.view, Gtk.MovementStep.LOGICAL_POSITIONS, 1, False)

    assert editor.cursor_offsets() == [2, 6]


def test_undo_clears_extra_cursors(make_editor):
    editor = make_editor("abc\nabc")
    editor.add_cursor_at(5)

    editor.plugin.undo(editor.view)

    assert editor.cursor_offsets() == []


def test_redo_clears_extra_cursors(make_editor):
    editor = make_editor("abc\nabc")
    editor.add_cursor_at(5)

    editor.plugin.redo(editor.view)

    assert editor.cursor_offsets() == []


def test_deactivate_removes_cursors_and_handlers(make_editor):
    editor = make_editor("abc\nabc")
    editor.add_cursor_at(5)

    editor.plugin.do_deactivate()

    assert editor.plugin.cursors == []
    assert editor.plugin._handlers == []
