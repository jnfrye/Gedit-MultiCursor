from gi.repository import GObject, Gtk, Gdk, Gedit


class MultiCursor(GObject.Object, Gedit.ViewActivatable):
  __gtype_name__ = "MultiCursor"
  view = GObject.property(type=Gedit.View)
  
  def __init__(self):
    GObject.Object.__init__(self)
    # handlers we've created so we can disconnect them
    self._handlers = [ ]
    # whether we're inside a user action block
    self._in_user_action = False
    # a list of functions to run when the user action is complete
    self._user_actions = [ ]
    # whether a paste has just happened
    self._handled_paste = False
    # the current undo stack level
    self.undo_level = 0
    # the contents of the clipboard on the last copy/cut operation
    self.clipboard = ''
    # a list of cursors besides the document cursor
    self.cursors = [ ]
    # the Ctrl+drag in progress, if any
    self._drag = None
    # map keyboard shortcuts
    self.keymap = {
      'Escape': self.clear_cursors
    }
    self.compile_keymap()

  # parse and cache accelerators for the main key bindings
  def compile_keymap(self):
    new_keymap = { }
    for (combo, action) in self.keymap.items():
      accel = Gtk.accelerator_parse(combo)
      new_keymap[accel] = { 
        'accel': accel,
        'action': action
      }
    self.keymap = new_keymap
  
  # hook and unhook from view events
  def do_activate(self):
    # retain a reference to the document
    self.doc = self.view.get_buffer()
    # bind events
    self.add_handler(self.view, 'event', self.on_event)
    self.add_handler(self.view, 'move-cursor', self.mc_move_cursor)
    self.add_handler(self.view, 'copy-clipboard', self.mc_save_clipboard)
    self.add_handler(self.view, 'cut-clipboard', self.mc_save_clipboard)
    self.add_handler(self.view, 'paste-clipboard', self.mc_paste_clipboard)
    self.add_handler(self.view, 'undo', self.undo)
    self.add_handler(self.view, 'redo', self.redo)
  def do_deactivate(self):
    self.clear_cursors()
    self.remove_handlers()

  # receive events from the document that control multiple cursors
  def hook_document(self):
    self.add_handler(self.doc, 'delete-range', self.delete)
    self.add_handler(self.doc, 'insert-text', self.insert)
    self.add_handler(self.doc, 'begin-user-action', self.begin_user_action)
    self.add_handler(self.doc, 'end-user-action', self.end_user_action, 'after')
    
  # stop receiving events from the document when there are no extra cursors
  def unhook_document(self):
    self.remove_handlers(self.doc)

  # add a signal handler for the given object
  def add_handler(self, obj, signal, handler, when=None):
    if (when == 'after'):
      self._handlers.append((obj, obj.connect_after(signal, handler)))
    else:
      self._handlers.append((obj, obj.connect(signal, handler)))
  # remove handlers for the given object, 
  #  or all handlers if no object is passed
  def remove_handlers(self, remove_obj=None):
    kept = [ ]
    for (obj, handler_id) in self._handlers:
      if ((remove_obj is None) or (remove_obj == obj)):
        obj.disconnect(handler_id)
      else:
        kept.append((obj, handler_id))
    self._handlers = kept

  def on_event(self, view, event):
    if event.type == Gdk.EventType.KEY_PRESS:
      return self.on_key_press(view, event)
    elif event.type == Gdk.EventType.BUTTON_PRESS:
      if (event.get_state()[1] & Gdk.ModifierType.CONTROL_MASK):
        (b, x, y) = event.get_coords()
        (x, y) = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, x, y)
        pos = view.get_iter_at_location(x, y)[1]
        self._drag = { 'start': pos.get_offset(), 'x': x, 'moved': False, 'cursors': [ ] }
        return(True)
      else:
        self.clear_cursors()
    elif event.type == Gdk.EventType.MOTION_NOTIFY:
      if ((self._drag is not None) and
          (event.get_state()[1] & Gdk.ModifierType.CONTROL_MASK) and
          (event.get_state()[1] & Gdk.ModifierType.BUTTON1_MASK)):
        (b, x, y) = event.get_coords()
        (x, y) = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, x, y)
        self.drag_to(view, x, y)
        return(True)
    elif event.type == Gdk.EventType.BUTTON_RELEASE:
      if (self._drag is not None):
        if (not self._drag['moved']):
          pos = self.doc.get_iter_at_offset(self._drag['start'])
          self.add_cursor(pos, pos)
        self._drag = None
        return(True)
    return False

  # place a cursor on each line between the press and the pointer, at the press column
  def drag_to(self, view, x, y):
    drag = self._drag
    if (not drag['moved']):
      self.doc.place_cursor(self.doc.get_iter_at_offset(drag['start']))
    drag['moved'] = True
    for cursor in drag['cursors']:
      self.remove_cursor(self.cursors.index(cursor))
    drag['cursors'] = [ ]
    press_line = self.doc.get_iter_at_offset(drag['start']).get_line()
    target_line = view.get_iter_at_location(x, y)[1].get_line()
    if (target_line >= press_line):
      lines = range(press_line + 1, target_line + 1)
    else:
      lines = range(target_line, press_line)
    for line in lines:
      start = self.doc.get_iter_at_line(line)
      end = start.copy()
      if (not end.ends_line()):
        end.forward_to_line_end()
      if (view.get_iter_location(end).x < drag['x']):
        continue
      rect = view.get_iter_location(start)
      pos = view.get_iter_at_location(drag['x'], rect.y + rect.height // 2)[1]
      self.add_cursor(pos, pos)
      drag['cursors'].append(self.cursors[-1])

  def on_key_press(self, view, event):
    _, keyval, _, _, _ = Gdk.Keymap.get_default().translate_keyboard_state(event.hardware_keycode, event.state, 0)
    mask = Gtk.accelerator_get_default_mod_mask() & event.state
    for shortcut in self.keymap.values():
      if ((shortcut['accel'][0] == keyval) and 
          (shortcut['accel'][1] == mask)):
        shortcut['action']()
        return(True)
    return(False)

  def order_iters(self, iters):
    if (iters[0].get_offset() <= iters[1].get_offset()):
      return(iters)
    else:
      return((iters[1], iters[0]))

  def get_selection_iters(self):
    start = self.doc.get_iter_at_mark(self.doc.get_insert())
    end = self.doc.get_iter_at_mark(self.doc.get_selection_bound())
    return((start, end))
  
  # add another cursor at the given position
  def add_cursor(self, start_iter, end_iter):
    if (len(self.cursors) == 0):
      self.hook_document()
      self.undo_level = 0
    # add the cursor
    cursor = Cursor(self.view, start_iter, end_iter)
    self.cursors.append(cursor)
    # save its initial state for the undo stack
    cursor.save_state(self.undo_level)

  # remove the cursor with the given index
  def remove_cursor(self, index):
    if (len(self.cursors) > 0):
      self.cursors[index].remove()
      del self.cursors[index]
      if (len(self.cursors) == 0):
        self.unhook_document()

  # remove all cursors
  def clear_cursors(self):
    if (len(self.cursors) > 0):
      while (len(self.cursors) > 0):
        self.remove_cursor(-1)
      
  # remove extra cursors before undo and redo so only the text is restored
  def undo(self, view):
    self.clear_cursors()
  def redo(self, view):
    self.clear_cursors()
  
  # schedule a multicursor insert for when the user's action is done
  def insert(self, doc, start, text, length):
    # if this is part of a user action, store and apply it at the end
    if (self._in_user_action):
      # get the offset from the insertion point
      (sel_start, sel_end) = self.order_iters(self.get_selection_iters())
      start_delta = start.get_offset() - sel_start.get_offset()
      # schedule this for when the user action is done
      self.store_user_action(self.mc_insert, (start_delta, text))

  # schedule a multicursor delete for when the user's action is done
  def delete(self, doc, start, end):
    # if this is part of a user action, store and apply it at the end
    if (self._in_user_action):
      # get the offset of the range from the insertion point
      (start, end) = self.order_iters((start, end))
      (sel_start, sel_end) = self.order_iters(self.get_selection_iters())
      start_delta = start.get_offset() - sel_start.get_offset()
      end_delta = end.get_offset() - sel_end.get_offset()
      # schedule this for when the user action is done
      self.store_user_action(self.mc_delete, (start_delta, end_delta))

  # clear the schedule of functions to be applied
  def begin_user_action(self, doc=None):
    # save the state of all the cursors before the user does something
    for cursor in self.cursors:
      cursor.save_state(self.undo_level)
    self._user_actions = [ ]
    self._in_user_action = True
  # schedule a function to be run when end_user_action is called
  def store_user_action(self, action, args):
    if (self._in_user_action):
      self._user_actions.append((action, args))
  # run scheduled functions
  def end_user_action(self, doc=None):
    self._in_user_action = False
    # execute the scheduled actions
    for (action, args) in self._user_actions:
      action(*args)
    self._user_actions = [ ]
    # save the state of all the cursors after the user does something
    self.undo_level += 1
    for cursor in self.cursors:
      cursor.save_state(self.undo_level)
    

  # insert text at every cursor
  def mc_insert(self, start_delta, text):
    # if a paste was just handled and we're inserting the global clipboard contents,
    #  insert local clipboard contents for each cursor
    if ((self._handled_paste) and (text == self.clipboard)):
      for cursor in self.cursors:
        if ((cursor.clipboard is not None) and (len(cursor.clipboard) > 0)):
          cursor.insert(start_delta, cursor.clipboard)
        else:
          cursor.insert(start_delta, text)
    else:
      for cursor in self.cursors:
        cursor.insert(start_delta, text)
    # any paste action has resulted in an insertion, so clear for next time
    self._handled_paste = False

  # delete text at every cursor
  def mc_delete(self, start_delta, end_delta):
    # do the delete relative to all cursors
    for cursor in self.cursors:
      cursor.delete(start_delta, end_delta)

  # move every cursor
  def mc_move_cursor(self, view, step_size, count, extend_selection):
    # clear all cursors if the movement would put them all in the same place
    if ((step_size == Gtk.MovementStep.BUFFER_ENDS) or
        (step_size == Gtk.MovementStep.PAGES)):
      self.clear_cursors()
      return
    for cursor in self.cursors:
      cursor.move(step_size, count, extend_selection)
    
  # copy the selection at every cursor
  def mc_save_clipboard(self, view):
    (sel_start, sel_end) = self.order_iters(self.get_selection_iters())
    self.clipboard = self.doc.get_text(sel_start, sel_end, True)
    # save the global clipboard so we can tell when it's being pasted
    for cursor in self.cursors:
      cursor.save_text()
      
  def mc_paste_clipboard(self, view):
    self._handled_paste = True


# this class manages a single extra cursor in the document
class Cursor:

  def __init__(self, view, start_iter, end_iter):
    # hook to the document
    self.view = view
    self.doc = self.view.get_buffer()
    # add marks for the cursor and selection area
    self.tag = MarkTag(self.view, 'multicursor', start_iter, end_iter)
    # make a clipboard local to this cursor
    self.clipboard = ''
    # safe the offset within the line for when the cursor crosses empty lines
    self.line_offset = None
    # make a place to save state for undo operations
    self.state = dict()
    self.initial_state_index = None
    
  # save the text to the local clipboard
  def save_text(self):
    self.clipboard = self.tag.get_text()
    
  # save state at the given index
  def save_state(self, index):
    self.state[index] = {
      'start': self.tag.get_start_iter().get_offset(),
      'end': self.tag.get_end_iter().get_offset()
    }
    if (self.initial_state_index is None):
      self.initial_state_index = index
  # recall the state at the given index
  def recall_state(self, index):
    if (index not in self.state):
      return
    state = self.state[index]
    start_iter = self.doc.get_iter_at_offset(state['start'])
    end_iter = self.doc.get_iter_at_offset(state['end'])
    self.tag.do_move_marks(start_iter, end_iter)

  # scroll so that this cursor is on-screen
  def scroll_onscreen(self):
    self.view.scroll_mark_onscreen(self.tag.end_mark)

  # remove the cursor from the document
  def remove(self):
    self.tag.remove()

  # insert text at the cursor
  def insert(self, start_delta, text):
    start_iter = self.doc.get_iter_at_offset(
      self.tag.get_start_iter().get_offset() + start_delta)
    self.tag.set_capturing_gravity(False)
    self.doc.insert(start_iter, text)
    self.tag.set_capturing_gravity(True)

  # delete text at the cursor
  def delete(self, start_delta, end_delta):
    # apply deltas
    start_iter = self.doc.get_iter_at_offset(
      self.tag.get_start_iter().get_offset() + start_delta)
    end_iter = self.doc.get_iter_at_offset(
      self.tag.get_end_iter().get_offset() + end_delta)
    # see if the length of the selection is going to zero, in which case
    #  we need to adjust the tag and marks below
    had_length = (self.tag.get_length() > 0)
    # delete the text
    self.doc.delete(start_iter, end_iter)
    # update the tag and marks if needed
    if ((self.tag.get_length() > 0) != had_length):
      self.tag.do_move_marks()

  # move the cursor
  def move(self, step_size, count, extend_selection):
    start_iter = self.tag.get_start_iter()
    end_iter = self.tag.get_end_iter()
    # extend the selection if needed
    if (extend_selection):
      sel_start = self.doc.get_iter_at_mark(self.doc.get_insert())
      sel_end = self.doc.get_iter_at_mark(self.doc.get_selection_bound())
      sel_delta = sel_start.get_offset() - sel_end.get_offset()
      move_end = (count > 0)
      if (sel_delta != 0):
        move_end = (sel_delta > 0)
      if (move_end):
        self.move_iter(end_iter, step_size, count)
      else:
        self.move_iter(start_iter, step_size, count)
    # collapse the selection if there is one and the insertion point moves
    elif (end_iter.get_offset() != start_iter.get_offset()):
      ch = ord(start_iter.get_char())
      if ch >= 0x600 and ch <= 0x6ff:
        if (count > 0):
          end_iter = start_iter.copy()
        else:
          start_iter = end_iter.copy()
      else:
        if (count < 0):
          end_iter = start_iter.copy()
        else:
          start_iter = end_iter.copy()
      if ((step_size != Gtk.MovementStep.LOGICAL_POSITIONS) and
          (step_size != Gtk.MovementStep.VISUAL_POSITIONS)):
        self.move_iter(start_iter, step_size, count)
        self.move_iter(end_iter, step_size, count)
    else:
      self.move_iter(start_iter, step_size, count)
      self.move_iter(end_iter, step_size, count)
    # update the tag
    self.tag.move_marks(start_iter, end_iter)

  def is_letter(self, ch):
    return (ch >= ord('a') and ch <= ord('z')) or (ch >= ord('A') and ch <= ord('Z')) or (ch >= 0x600 and ch <= 0x6ff) or ch == ord('_')

  def is_space(self, ch):
    return ch == ord(' ') or ch == ord('\t') or ch == ord('\r') or ch == ord('\n')

  def is_word_boundary(self, ch1, ch2):
    if self.is_space(ch2) and not self.is_space(ch1): return True
    elif self.is_space(ch1) and not self.is_space(ch2): return False
    elif self.is_letter(ch1) and not self.is_letter(ch2): return True
    elif self.is_letter(ch2) and not self.is_letter(ch1): return True
    else: return False

  def move_word_forward(self, pos):
    ch1 = ord(pos.get_char())
    pos.forward_char()
    if pos.is_end(): return
    ch2 = ord(pos.get_char())
    while not self.is_word_boundary(ch1, ch2):
      pos.forward_char()
      if pos.is_end(): return
      ch1 = ch2
      ch2 = ord(pos.get_char())
    
  def move_word_backward(self, pos):
    pos.backward_char()
    if pos.is_start(): return
    ch1 = ord(pos.get_char())
    pos.backward_char()
    if pos.is_start(): return
    ch2 = ord(pos.get_char())
    while not self.is_word_boundary(ch1, ch2):
      pos.backward_char()
      if pos.is_start(): return
      ch1 = ch2
      ch2 = ord(pos.get_char())
    pos.forward_char()

  # move an iter according to the kind of params we get from a 
  #  'cursor-move' signal from the view
  def move_iter(self, pos, step_size, count):
    if step_size == Gtk.MovementStep.LOGICAL_POSITIONS:
      if (count < 0):
        pos.backward_cursor_positions(abs(count))
      else:
        pos.forward_cursor_positions(abs(count))
    elif step_size == Gtk.MovementStep.VISUAL_POSITIONS:
      startOfLine = pos.copy()
      startOfLine.set_line_offset(0)
      endOfLine = startOfLine.copy()
      endOfLine.forward_line()
      lineText = pos.get_buffer().get_text(startOfLine, endOfLine, True)
      pangoLayout = self.view.create_pango_layout(lineText)
      newLineIndex,_ = pangoLayout.move_cursor_visually(True, pos.get_line_index(), 0, count)
      if newLineIndex >= 0:
        pos.set_line_index(newLineIndex)
    elif (step_size == Gtk.MovementStep.WORDS):
      startOfLine = pos.copy()
      startOfLine.set_line_offset(0)
      isRtl = False
      while not startOfLine.ends_line():
        ch = ord(startOfLine.get_char())
        if ch >= 0x600 and ch <= 0x6ff:
          isRtl = True
          break
        elif (ch >= ord('a') and ch <= ord('z')) or (ch >= ord('A') and ch <= ord('Z')):
          break
        startOfLine.forward_char()
      if isRtl:
        if (count > 0):
          for c in range(abs(count)): self.move_word_backward(pos)
        else:
          for c in range(abs(count)): self.move_word_forward(pos)
      else:
        if (count < 0):
          for c in range(abs(count)): self.move_word_backward(pos)
        else:
          for c in range(abs(count)): self.move_word_forward(pos)
    elif (step_size == Gtk.MovementStep.DISPLAY_LINES):
      if (self.line_offset is None):
        self.line_offset = pos.get_line_offset()
      pos.set_line_offset(0)
      pos.set_line(pos.get_line() + count)
      if (not pos.ends_line()):
        pos.forward_to_line_end()
      if (pos.get_line_offset() > 0):
        pos.set_line_offset(min(self.line_offset, pos.get_line_offset()))
    elif (step_size == Gtk.MovementStep.PARAGRAPHS):
      if (count < 0):
        pos.backward_visible_lines(abs(count))
        pos.set_line_offset(0)
      else:
        pos.forward_visible_lines(abs(count))
        pos.forward_to_line_end()
    elif ((step_size == Gtk.MovementStep.HORIZONTAL_PAGES) or 
          (step_size == Gtk.MovementStep.DISPLAY_LINE_ENDS)):
      if (count < 0):
        pos.set_line_offset(0)
      else:
        pos.forward_to_line_end()
    # clear the stored line offset if the cursor moves horizontally
    if (step_size != Gtk.MovementStep.DISPLAY_LINES):
      self.line_offset = None




# this class manages a GtkTextTag, anchoring it with GtkTextMarks instead of GtkTextIters
class MarkTag:

  def __init__(self, view, name, start_iter, end_iter):
    self.view = view
    self.doc = self.view.get_buffer()
    self.name = name
    self.start_mark = self.doc.create_mark(None, start_iter, True)
    self.end_mark = self.doc.create_mark(None, end_iter, False)
    # update the tag for its initial position
    self.do_move_marks()

  # get an iter at the beginning of the tagged area
  def get_start_iter(self):
    return(self.doc.get_iter_at_mark(self.start_mark))

  # get an iter at the end of the tagged area
  def get_end_iter(self):
    return(self.doc.get_iter_at_mark(self.end_mark))

  # get the length between the start and end
  def get_length(self):
    return(self.get_end_iter().get_offset() - 
           self.get_start_iter().get_offset())
           
  # get the text between the start and end
  def get_text(self):
    return(self.doc.get_text(self.get_start_iter(), self.get_end_iter(), True))

  # replace the text in the tag
  def set_text(self, text):
    start_iter = self.get_start_iter()
    end_iter = self.get_end_iter()
    self.doc.delete(start_iter, end_iter)
    self.doc.insert(start_iter, text)

  # move the start and end marks to the specified locations, doing nothing
  #  if the locations are not changing
  def move_marks(self, new_start_iter=None, new_end_iter=None):
    start_iter = self.doc.get_iter_at_mark(self.start_mark)
    end_iter = self.doc.get_iter_at_mark(self.end_mark)
    if (((new_start_iter is not None) and 
         (new_start_iter.get_offset() != start_iter.get_offset())) or
        ((new_end_iter is not None) and 
         (new_end_iter.get_offset() != end_iter.get_offset()))):
      self.do_move_marks(new_start_iter, new_end_iter)
  # update the tag to reflect the new locations
  def do_move_marks(self, new_start_iter=None, new_end_iter=None):
    self.remove_tag()
    if (new_start_iter is not None):
      self.doc.move_mark(self.start_mark, new_start_iter)
    if (new_end_iter is not None):
      self.doc.move_mark(self.end_mark, new_end_iter)
    # show a mark if there is no selection
    start_iter = self.doc.get_iter_at_mark(self.start_mark)
    end_iter = self.doc.get_iter_at_mark(self.end_mark)
    if (start_iter.get_offset() != end_iter.get_offset()):
      self.add_tag()
      self.start_mark.set_visible(False)
    else:
      self.start_mark.set_visible(self.name != 'tracker')

  # set whether the tag captures text inserted between it or not
  def set_capturing_gravity(self, capture):
    if (self.start_mark.get_left_gravity() != capture):
      start_iter = self.doc.get_iter_at_mark(self.start_mark)
      visible = self.start_mark.get_visible()
      self.doc.delete_mark(self.start_mark)
      self.start_mark = self.doc.create_mark(None, start_iter, capture)
      self.start_mark.set_visible(visible)
      
      
  # remove the tag and marks from the document
  def remove(self):
    self.start_mark.set_visible(False)
    self.remove_tag()
    self.doc.delete_mark(self.start_mark)
    self.doc.delete_mark(self.end_mark)

  # add a tag between the marks
  def add_tag(self):
    tag = self.get_tag()
    if (tag is not None):
      start_iter = self.doc.get_iter_at_mark(self.start_mark)
      end_iter = self.doc.get_iter_at_mark(self.end_mark)
      self.doc.apply_tag(tag, start_iter, end_iter)
    # remove search match tags on the cursor to avoid visual tag collision
    if (self.name == 'multicursor'):
      found_tag = self.doc.get_tag_table().lookup('found')
      if (found_tag):
        self.doc.remove_tag_by_name('found', start_iter, end_iter)

  # remove the tag from between the marks if there is one
  def remove_tag(self):
    if (self.doc.get_tag_table().lookup(self.name) is not None):
      start_iter = self.doc.get_iter_at_mark(self.start_mark)
      end_iter = self.doc.get_iter_at_mark(self.end_mark)
      self.doc.remove_tag_by_name(self.name, start_iter, end_iter)

  # get a styled tag to place between the marks
  def get_tag(self):
    # see if we already have this tag
    tag = self.doc.get_tag_table().lookup(self.name)
    if (tag is None):
      # style the selection part of a cursor
      if (self.name == 'multicursor'):
        background = self.get_view_color('selected_bg_color')
        foreground = self.get_view_color('selected_fg_color')
        (background, foreground) = self.get_scheme_colors( 
          'selection', (background, foreground))
        tag = self.doc.create_tag(self.name, 
                                   background=background, 
                                   foreground=foreground)
      # this shouldn't happen, but make it obvious just in case
      else:
        tag = self.doc.create_tag(self.name, 
                                   background="#FF0000", 
                                   foreground="#FFFFFF")
    return(tag)

  # get the default color for the given style property of the view
  def get_view_color(self, color_name):
    return(self.view.get_style().lookup_color(color_name)[1].to_string())
  
  # get the given foreground and background colors from the current 
  #  style scheme, falling back on the given defaults
  def get_scheme_colors(self, style_name, defaults):
    scheme = self.doc.get_style_scheme()
    if (scheme is not None):
      sel_style = scheme.get_style(style_name)
      if (sel_style is not None):
        return(sel_style.get_property('background'), 
               sel_style.get_property('foreground'))
    return(defaults)
    



