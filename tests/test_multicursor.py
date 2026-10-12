from gi.repository import Gdk, Gtk

from conftest import (FakeButtonEvent, FakePointerEvent, system_clipboard_text,
                      set_system_clipboard_text, window_point_for_offset)


def ctrl_drag(editor, start, end):
    """Press with Ctrl at `start`, then drag with Ctrl held to `end`."""
    view = editor.view
    x, y = window_point_for_offset(view, start)
    editor.plugin.on_event(view, FakePointerEvent(
        Gdk.EventType.BUTTON_PRESS, x, y, ctrl=True))
    ctrl_drag_move(editor, end)


def ctrl_drag_move(editor, end):
    x, y = window_point_for_offset(editor.view, end)
    editor.plugin.on_event(editor.view, FakePointerEvent(
        Gdk.EventType.MOTION_NOTIFY, x, y, ctrl=True, button1=True))


def ctrl_drag_release(editor, end):
    x, y = window_point_for_offset(editor.view, end)
    editor.plugin.on_event(editor.view, FakePointerEvent(
        Gdk.EventType.BUTTON_RELEASE, x, y, ctrl=True, button1=True))


def test_ctrl_click_adds_cursor_where_clicked(make_editor):
    editor = make_editor("first line\nsecond line\nthird")
    x, y = window_point_for_offset(editor.view, 8)

    handled = editor.plugin.on_event(editor.view, FakeButtonEvent(x, y, ctrl=True))
    editor.plugin.on_event(editor.view, FakePointerEvent(
        Gdk.EventType.BUTTON_RELEASE, x, y, ctrl=True))

    assert handled is True
    assert editor.cursor_offsets() == [8]


def test_ctrl_drag_down_adds_cursor_on_each_line_at_press_column(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")

    ctrl_drag(editor, start=2, end=16)

    assert editor.cursor_offsets() == [9, 16]


def test_typing_after_ctrl_drag_inserts_on_every_line(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=2, end=16)
    ctrl_drag_release(editor, end=16)

    editor.type_text("X")

    assert editor.buffer.get_text(
        editor.buffer.get_start_iter(), editor.buffer.get_end_iter(), True
    ) == "abXcdef\nabXcdef\nabXcdef\nabcdef"


def test_repeated_motion_does_not_duplicate_carets(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=2, end=16)

    ctrl_drag_move(editor, end=23)
    ctrl_drag_move(editor, end=16)

    assert editor.cursor_offsets() == [9, 16]


def test_motion_after_release_adds_no_carets(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=2, end=16)
    ctrl_drag_release(editor, end=16)

    ctrl_drag_move(editor, end=23)

    assert editor.cursor_offsets() == [9, 16]


def test_drag_without_ctrl_adds_no_carets(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    x, y = window_point_for_offset(editor.view, 2)
    editor.plugin.on_event(editor.view, FakePointerEvent(
        Gdk.EventType.BUTTON_PRESS, x, y))
    x, y = window_point_for_offset(editor.view, 19)
    editor.plugin.on_event(editor.view, FakePointerEvent(
        Gdk.EventType.MOTION_NOTIFY, x, y, button1=True))

    assert editor.cursor_offsets() == []


def test_ctrl_drag_down_and_right_selects_a_box(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")

    ctrl_drag(editor, start=1, end=18)

    assert editor.main_selection() == (1, 4)
    assert editor.cursor_selections() == [(8, 11), (15, 18)]


def test_vertical_ctrl_drag_makes_carets_not_selections(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")

    ctrl_drag(editor, start=2, end=16)

    assert editor.main_selection() is None
    assert editor.cursor_selections() == [(9, 9), (16, 16)]


def test_dragging_left_selects_the_same_box_as_dragging_right(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")

    ctrl_drag(editor, start=4, end=15)

    assert editor.main_selection() == (1, 4)
    assert editor.cursor_selections() == [(8, 11), (15, 18)]


def test_dragging_up_and_right_selects_lines_above(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")

    ctrl_drag(editor, start=15, end=4)

    assert editor.main_selection() == (15, 18)
    assert editor.cursor_selections() == [(1, 4), (8, 11)]


def test_moving_back_to_press_column_returns_to_carets(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=2, end=18)

    ctrl_drag_move(editor, end=16)

    assert editor.main_selection() is None
    assert editor.cursor_selections() == [(9, 9), (16, 16)]


def test_box_selection_works_with_a_style_scheme(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    editor.use_scheme('oblivion')

    ctrl_drag(editor, start=1, end=18)

    assert editor.main_selection() == (1, 4)
    assert editor.cursor_selections() == [(8, 11), (15, 18)]


def test_box_selection_uses_the_scheme_selection_colors(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    editor.use_scheme('oblivion')

    ctrl_drag(editor, start=1, end=18)

    tag = editor.buffer.get_tag_table().lookup('multicursor')
    expected = Gdk.RGBA()
    expected.parse('#888a85')
    assert tag.get_property('background-rgba').to_string() == expected.to_string()


def test_box_selection_color_follows_a_scheme_change(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    editor.use_scheme('oblivion')
    ctrl_drag(editor, start=1, end=18)
    ctrl_drag_release(editor, end=18)

    editor.use_scheme('cobalt')

    tag = editor.buffer.get_tag_table().lookup('multicursor')
    expected = Gdk.RGBA()
    expected.parse('#0088ff')
    assert tag.get_property('background-rgba').to_string() == expected.to_string()


def test_typing_replaces_the_box_on_every_line_dragging_right(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=1, end=18)
    ctrl_drag_release(editor, end=18)

    editor.type_text("X")

    assert editor.text() == "aXef\naXef\naXef\nabcdef"


def test_typing_replaces_the_box_on_every_line_dragging_left(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=4, end=15)
    ctrl_drag_release(editor, end=15)

    editor.type_text("X")

    assert editor.text() == "aXef\naXef\naXef\nabcdef"


def test_backspace_removes_the_box_on_every_line(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=1, end=18)
    ctrl_drag_release(editor, end=18)

    editor.press_backspace()

    assert editor.text() == "aef\naef\naef\nabcdef"


def test_delete_key_removes_the_box_on_every_line(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=4, end=15)
    ctrl_drag_release(editor, end=15)

    editor.press_delete()

    assert editor.text() == "aef\naef\naef\nabcdef"


def test_copying_a_box_puts_every_line_on_the_clipboard(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=1, end=18)
    ctrl_drag_release(editor, end=18)

    editor.view.emit('copy-clipboard')

    assert system_clipboard_text() == "bcd\nbcd\nbcd"


def test_copying_a_plain_selection_copies_just_that_text(make_editor):
    editor = make_editor("abcdef\nabcdef")
    editor.buffer.select_range(editor.iter_at(1), editor.iter_at(4))

    editor.view.emit('copy-clipboard')

    assert system_clipboard_text() == "bcd"


def test_single_caret_pastes_multi_line_text_with_line_breaks(make_editor):
    editor = make_editor("xyz")
    editor.buffer.place_cursor(editor.iter_at(1))
    set_system_clipboard_text("bcd\nBCD")

    editor.paste()

    assert editor.text() == "xbcd\nBCDyz"


def test_matching_line_counts_paste_one_line_per_caret(make_editor):
    editor = make_editor("xyz\nxyz")
    ctrl_drag(editor, start=1, end=5)
    ctrl_drag_release(editor, end=5)
    set_system_clipboard_text("bcd\nBCD")

    editor.paste()

    assert editor.text() == "xbcdyz\nxBCDyz"


def test_mismatched_line_counts_paste_the_full_text_at_each_caret(make_editor):
    editor = make_editor("xyz\nxyz")
    ctrl_drag(editor, start=1, end=5)
    ctrl_drag_release(editor, end=5)
    set_system_clipboard_text("bcd\nBCD\nxxx")

    editor.paste()

    assert editor.text() == "xbcd\nBCD\nxxxyz\nxbcd\nBCD\nxxxyz"


def test_pasting_over_a_box_replaces_it_line_by_line(make_editor):
    editor = make_editor("abcdef\nabcdef")
    ctrl_drag(editor, start=1, end=11)
    ctrl_drag_release(editor, end=11)
    set_system_clipboard_text("X\nY")

    editor.paste()

    assert editor.text() == "aXef\naYef"


def test_line_ending_inside_box_is_selected_to_its_end(make_editor):
    editor = make_editor("abcdef\nabcd\na\nabcdef")

    ctrl_drag(editor, start=2, end=19)

    assert editor.main_selection() == (2, 5)
    assert editor.cursor_selections() == [(9, 11), (16, 19)]


def test_release_keeps_selections_and_later_motion_does_nothing(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")
    ctrl_drag(editor, start=1, end=18)
    ctrl_drag_release(editor, end=18)

    ctrl_drag_move(editor, end=23)

    assert editor.main_selection() == (1, 4)
    assert editor.cursor_selections() == [(8, 11), (15, 18)]


def test_ctrl_drag_back_up_removes_carets_and_adds_above(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")

    ctrl_drag(editor, start=9, end=23)
    assert editor.cursor_offsets() == [16, 23]

    ctrl_drag_move(editor, end=2)
    assert editor.cursor_offsets() == [2]


def test_ctrl_drag_skips_lines_shorter_than_press_column(make_editor):
    editor = make_editor("abcdef\na\nabcdef\nabcdef")

    ctrl_drag(editor, start=2, end=13)

    assert editor.cursor_offsets() == [11]


def test_ctrl_drag_moves_main_caret_to_press_point(make_editor):
    editor = make_editor("abcdef\nabcdef\nabcdef\nabcdef")

    ctrl_drag(editor, start=2, end=16)

    caret = editor.buffer.get_iter_at_mark(editor.buffer.get_insert())
    assert caret.get_offset() == 2


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
