#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
interface.py - a GTK+ frontend for the Apoo processor
Copyright (C) 2006, 2007 Ricardo Cruz <rpmcruz@alunos.dcc.fc.up.pt>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import os, sys
import ConfigParser
import gtk, pango, gobject

from vpu import *
from constants import *

VERSION = "2.1.0"

# Definitions (non-configurable)
APOO_CONFIG_FILE = os.path.join (os.environ.get("HOME"), ".apoo")
DOCS_PATH = "/usr/share/doc/apoo/"
if not os.path.exists (DOCS_PATH):
    dirname = os.path.dirname (sys.argv[0])
    if len (dirname): DOCS_PATH = dirname + "/docs/"
    else: DOCS_PATH = "docs/"
DOC_APOO = "help_apoo"
DOC_TESTER = "help_tester"
DOC_ASSEMBLY = "help_assembly"

# Configurable (via arguments):
test_mode = False  # --tester

# Configurable (via the preferences dialog):
# (up-case are variables we don't touch, so we know the defaults.)
REGISTERS_NB = registers_nb = 8
RAM_SIZE     = ram_size     = 1000
MAX_STEPS    = max_steps    = 1000   # to cut on infinite loops
INPUT_OUTPUT = input_output = 50001  # magic numbers
OUTPUT_ASCII = output_ascii = 50000
OUTPUT_CR    = output_cr    = 50010

SHORTCUTS_STYLE = shortcuts_style = "desktop"  # "desktop" or "emacs"
default_dir = None
MIRROR_MEMORY = mirror_memory = "no"  # "hor", "ver" or "no"

# Utilities
def digits_on (nb):  # returns the digits of a number (eg. 250 => 3)
    if nb < 10: return 1
    return digits_on (nb / 10) + 1
def is_blank (ch):  # helpers
	return ch == ' ' or ch == '\t' or ch == '\n' or ch == '\0'
def reverse_lookup (dict, value):
	for i in dict.keys():
		if dict[i] == value:
			return i
	return None

# We need to explicitely specify font size, so let's get what
# was the font size (which would be the default)
def set_monospace_font (widget):
	font_desc = widget.get_pango_context().get_font_description()
	font_desc.set_family ("monospace")
	widget.modify_font (font_desc)

# By specifying a tone (from 0 to 255) and a style, it calculates a
# proper color.
def get_tone_color (style, tone):
	# we find the highest color component, and calculate the ratios accordingly
	# so, eg: (84, 151, 213) -> (0.39, 0.71, 1.00)
	syscolor = style.bg [gtk.STATE_SELECTED]
	max_color = max (max (syscolor.red, syscolor.green), syscolor.blue)
	red_ratio   = (syscolor.red   * 1.0) / max_color
	green_ratio = (syscolor.green * 1.0) / max_color
	blue_ratio  = (syscolor.blue  * 1.0) / max_color

	red   = int (red_ratio   * tone)
	green = int (green_ratio * tone)
	blue  = int (blue_ratio  * tone)
	return get_color (red, green, blue)
def get_color (red, green, blue):
	return gtk.gdk.Color (red << 8, green << 8, blue << 8, 0)

## Our own widgets

# Extends GtkTextBuffer to add some basic functionality:
# * undo/redo, * file reading/writting
class TextBufferExt (gtk.TextBuffer):
	def __init__ (self):
		gtk.TextBuffer.__init__(self)
		# actions stacks, so we can undo/redo
		self.undo_reset()
		self.ignore_event = False

	# public:
	def undo_reset (self):
		self.do_stack = []  # of type [ ('i', 30, "text"), ('d', 20, "other") ]
		self.do_stack_ptr = 0

	def can_undo (self):
		return self.do_stack_ptr > 0
	def can_redo (self):
		return self.do_stack_ptr < len (self.do_stack)

	def undo (self):
		if self.can_undo():
			self.do_stack_ptr -= 1
			action = self.do_stack [self.do_stack_ptr]
			self.do (action, True)
	def redo (self):
		if self.can_redo():
			action = self.do_stack [self.do_stack_ptr]
			self.do_stack_ptr += 1
			self.do (action, False)

	def read (self, filename):
		try:
			file = open (filename, 'r')
			self.set_text (file.read())
			file.close()
		except IOError: return False
		self.undo_reset()
		self.set_modified (False)
		return True

	def write (self, filename):
		try:
			file = open (filename, 'w')
			file.write (self.get_text (self.get_start_iter(), self.get_end_iter(), False))
			file.close()
		except IOError: return False
		self.set_modified (False)
		return True

	def get_insert_iter (self):
		return self.get_iter_at_mark (self.get_insert())

	# private:
	def do_insert_text (self, iter, text, length):
		if not self.ignore_event:
			action = ('i', iter.get_offset(), text)
			self.do_stack [self.do_stack_ptr:] = [action]
			self.do_stack_ptr += 1
		gtk.TextBuffer.do_insert_text (self, iter, text, length)

	def do_delete_range (self, start_it, end_it):
		if not self.ignore_event:
			action = ('d', start_it.get_offset(), self.get_text (start_it, end_it, False))
			self.do_stack [self.do_stack_ptr:] = [action]
			self.do_stack_ptr += 1
		gtk.TextBuffer.do_delete_range (self, start_it, end_it)

	def do (self, action, undo):
		iter = self.get_iter_at_offset (action[1])
		if (action[0] == 'd' and undo) or (action[0] == 'i' and not undo):
			self.ignore_event = True
			self.insert (iter, action[2])
			self.ignore_event = False
		else:
			end_iter = self.get_iter_at_offset (action[1] + len (action[2]))
			self.ignore_event = True
			self.delete (iter, end_iter)
			self.ignore_event = False

gobject.type_register (TextBufferExt)

# Extends GtkTextBuffer (actually our TextBufferExt) to add Editor-specific
# functionality
class EditorBuffer (TextBufferExt):
	def __init__ (self, editor):
		TextBufferExt.__init__(self)
		self.create_tag("comment", foreground = "darkgrey",  style = pango.STYLE_OBLIQUE) 
		self.create_tag("assign",  foreground = "darkred")  # eg: function:
		self.create_tag("instruction", weight = pango.WEIGHT_BOLD)  # eg: loadn
		self.create_tag("error", underline = pango.UNDERLINE_ERROR)
		self.connect_after ("notify::cursor-position", self.cursor_moved_cb)

		self.cursor_line = 0
		self.line_edited = False  # was current line edited?
		self.editor = editor

	# cuts the line into [(word, start_iter, end_iter), ...]
	class Split:
		def __init__ (self, word, start_it, end_it):
			self.word = word
			self.start_it = start_it
			self.end_it = end_it
	def split_line (self, line):
		iter = self.get_iter_at_line (line)
		if iter.is_end():
			return None
		splits = []
		while not iter.ends_line():
			while is_blank (iter.get_char()) and not iter.ends_line():
				iter.forward_char()
			if iter.ends_line(): break
			start_iter = iter.copy()
			while not is_blank (iter.get_char()):
				iter.forward_char()
			word = start_iter.get_text (iter).encode()
			splits += [EditorBuffer.Split (word, start_iter, iter.copy())]
		return splits

	def remove_line_tags (self, line):
		line_iter = self.get_iter_at_line (line)
		if line_iter.ends_line():
			return  # blank line -- you'd cross to next
		line_end_iter = line_iter.copy()
		line_end_iter.forward_to_line_end()
		self.remove_all_tags (line_iter, line_end_iter)

	def is_word_register (self, word):
		if word == None: return False
		if len (word) < 2: return False
		if word[0] != 'r' and word[0] != 'R': return False
		if len (word) == 2:
			if  word[1] == 's' or word[1] == 'S' or word[1] == 'f' or word[1] == 'F':
				return True
		for i in xrange (1, len (word)):
			if word[i] < '0' or word[i] > '9':
				return False
		return True

	# as-you-type highlighting. Iterates every line touched.
	def apply_highlight (self, start_line, end_line):
		line = start_line
		while line <= end_line:
			splits = self.split_line (line)
			if splits == None:
				break
			self.remove_line_tags (line)
			line += 1

			length = len (splits)
			if length == 0:
				continue

			comment = None
			for i in xrange (len (splits)):
				if splits[i].word[0] == '#':
					comment = splits[i]
					length = i
					break

			address = None
			instr = None
			args = [None, None]
			args_nb = 0
			i = 0
			if splits[i].word[-1] == ':':
				address = splits[i]
				i += 1
			if length > i:
				instr = splits[i]
				i += 1
				args_nb = length - i
				if args_nb >= 1:
					args[0] = splits[i]
				if args_nb >= 2:
					args[1] = splits[i+1]

			if address != None:
				end_it = address.end_it.copy()
				end_it.backward_char()  # don't highlight the ':'
				self.apply_tag_by_name ("assign", address.start_it, end_it)
			match_instr = False
			if instr != None:
				for categories in inst:
					for i in categories:
						if instr.word == i:
							match_instr = True
							self.apply_tag_by_name ("instruction",
								instr.start_it, instr.end_it)
			if comment != None:
				self.apply_tag_by_name ("comment", comment.start_it, splits[-1].end_it)

			if line-1 != self.get_insert_iter().get_line() and (address != None or instr != None) and self.editor.mode.mode == Editor.Mode.EDIT:
				error = not match_instr or args_nb > 2
				if not error:
					# arguments semantics: ' ' - none, 'r' - register, 'n' - non-register
					error_inst = ((' ',' '), ('n',' '), ('r',' '), ('r','r'), ('n','r'),
					              ('r','n'))
					for i in xrange (6):
						for w in inst[i]:
							if w == instr.word:
								for j in xrange(2):
									if error_inst[i][j] == ' ':
										error = error or args[j] != None
									elif args[j] == None:
										error = True
									elif error_inst[i][j] == 'r':
										error = error or not self.is_word_register (args[j].word)
									elif error_inst[i][j] == 'n':
										error = error or self.is_word_register (args[j].word)

				if error:
					start_it = splits[0].start_it
					end_it = splits[length-1].end_it
					self.apply_tag_by_name ("error", start_it, end_it)

	def cursor_moved_cb (self, buffer, pos_ptr):
		line = self.get_insert_iter().get_line()
		if line != self.cursor_line:
			if self.line_edited:
				self.apply_highlight (self.cursor_line, self.cursor_line)
				self.line_edited = False
			self.cursor_line = line

	def do_insert_text (self, iter, text, length):
		TextBufferExt.do_insert_text (self, iter, text, length)
		self.line_edited = True

		# as-you-type highlighting
		start = iter.copy()
		start.set_offset (iter.get_offset() - length)
		self.apply_highlight (start.get_line(), iter.get_line())

		# simple auto-identation; if the user typed return, apply the same
		# identation of the previous line
		if length == 1 and text == "\n":
			start_it = iter.copy()
			if start_it.backward_line():
				end_it = start_it.copy()
				while end_it.get_char() == ' ' or end_it.get_char() == '\t':
					end_it.forward_char()

				if start_it.compare (end_it) != 0:  # there is identation
					ident = self.get_text (start_it, end_it)	
					self.insert (iter, ident)

	def do_delete_range (self, start_it, end_it):
		TextBufferExt.do_delete_range (self, start_it, end_it)
		self.apply_highlight (start_it.get_line(), end_it.get_line())

	# hooks for emacs-like region mark (ctrl+space)
	def cursor_moved (self, view, step_size, count, extend_selection):
		mark = self.get_mark ("emacs-mark")
		if mark:
			self.select_range (self.get_iter_at_mark (self.get_insert()),
			                   self.get_iter_at_mark (mark))
	def do_changed (self):  # disable emacs' mark region
		gtk.TextBuffer.do_changed (self)
		mark = self.get_mark ("emacs-mark")
		if mark: self.delete_mark (mark)

# The Editor widget, an extension over gtk.TextView to support eg. line numbering
class Editor (gtk.TextView):
	class Mode(object):
		EDIT = 0
		RUN  = 1
		def __init__ (self, editor):
			self.editor = editor
			# Save normal/sensitive base color so we can mess with that
			self.normal_color = editor.style.base [gtk.STATE_NORMAL]
			self.insensitive_color = editor.style.base [gtk.STATE_INSENSITIVE]
			self.line_color = None
			self.set_mode (None)

		def set_mode (self, vpu):
			if vpu == None:
				self.mode = self.EDIT
				self.alternative_numbering = None
				self.fixed_line = -1
				self.editor.breakpoints = []
			else:
				if self.mode == self.RUN:
					self.editor.reload_breakpoints (vpu)
				self.mode = self.RUN
				self.alternative_numbering = {}
				for i in xrange (len (vpu.lines)):
					self.alternative_numbering [vpu.lines[i]-1] = i

			# We don't want to set the editor insensitive to allow users
			# to do selections and that. So we mimic half of it.
			editable = self.mode == self.EDIT
			self.editor.set_editable (editable)
			self.editor.set_cursor_visible (editable)
			if editable: self.editor.modify_base (gtk.STATE_NORMAL, self.normal_color)
			else:        self.editor.modify_base (gtk.STATE_NORMAL, self.insensitive_color)

		def set_current_line (self, line):
			if self.mode == self.EDIT:
				self.fixed_line = -1
			if line >= 0:
				buffer = self.editor.get_buffer()
				it = buffer.get_iter_at_line (line)
				buffer.place_cursor (it)
				# make line visible
				self.editor.scroll_to_iter (it, 0.10)
				self.fixed_line = line-1
			self.editor.queue_draw()  # update line highlight

		def set_current_line_color (self, color):
			if color == "white":
				color = None
			self.line_color = color
			self.editor.queue_draw()

		def get_current_line (self, window):
			if self.mode == self.EDIT:
				buffer = self.editor.get_buffer()
				iter = buffer.get_iter_at_mark (buffer.get_insert())
				curline = iter.get_line()

				fill_gc = self.editor.style.bg_gc [gtk.STATE_NORMAL]
				stroke_gc = None
			else:
				curline = self.fixed_line

				color = get_tone_color (self.editor.style, 255)
				if self.line_color != None:
					clr = self.line_color
					color = gtk.gdk.color_parse (clr)
				fill_gc = window.new_gc()
				fill_gc.set_rgb_fg_color (color)

				color = get_tone_color (self.editor.style, 150)
				if self.line_color != None:
					clr = self.line_color + "4"
					color = gtk.gdk.color_parse (clr)
				stroke_gc = window.new_gc()
				stroke_gc.set_rgb_fg_color (color)
			return (curline, fill_gc, stroke_gc)

		def get_line_number (self, line):
			if self.alternative_numbering:
				try:    line = self.alternative_numbering [line]
				except: line = -1
			else:
				line = line+1
			return line

	def __init__ (self, parent):
		buffer = EditorBuffer (self)
		gtk.TextView.__init__ (self, buffer)
		self.main_parent = parent

		self.set_tabs (pango.TabArray (4, False))
		set_monospace_font (self)
		self.set_wrap_mode (gtk.WRAP_WORD_CHAR)
		self.set_left_margin (1)

		font_desc = self.get_pango_context().get_font_description()
		metrics = self.get_pango_context().get_metrics (font_desc, None)
		self.digit_width = pango.PIXELS (metrics.get_approximate_digit_width())
		self.digit_height =  pango.PIXELS (metrics.get_ascent())
		self.digit_height += pango.PIXELS (metrics.get_descent())

		self.margin_digits = 99  # to force a margin calculation
		self.text_changed (self.get_buffer())  # sets the numbering margin

		self.do_stack = [] # of type [ ('i', 30, "text"), ('d', 20,"other") ]
		# for re/undo
		self.do_stack_ptr = 0

		# printing setup
		self.settings = None

		# editor mode: edit, run, or error
		self.mode = Editor.Mode (self)

		buffer.connect ("changed", self.text_changed)
		self.connect_after ("move-cursor", buffer.cursor_moved)  # for the emacs mark

	def get_text (self):
		buffer = self.get_buffer()
		return buffer.get_text (buffer.get_start_iter(), buffer.get_end_iter(),
		       False)

	def do_expose_event (self, event):  # draw command
		curline, fill_gc, stroke_gc = self.mode.get_current_line (event.window)

		# left window -- draw line numbering
		window = self.get_window (gtk.TEXT_WINDOW_LEFT)
		if event.window == window:
			visible_text = self.get_visible_rect()
			iter = self.get_iter_at_location (visible_text.x, visible_text.y)

			layout = pango.Layout (self.get_pango_context())
			last_loop = False
			while True:  # a do ... while would be nicer :/
				rect = self.get_iter_location (iter)
				x, y = self.buffer_to_window_coords (gtk.TEXT_WINDOW_LEFT, rect.x, rect.y)

				if y > event.area.y + event.area.height: break
				if y + self.digit_height > event.area.y:
					line = self.mode.get_line_number (iter.get_line())

					# draw a half arc at the numbering window to finish current line
					# rectangle nicely.
					if iter.get_line() == curline and stroke_gc != None:
						w = self.get_border_window_size (gtk.TEXT_WINDOW_LEFT)
						h = rect.height
						window.draw_arc (fill_gc, True, 0, y, w, h, 90*64, 180*64)
						window.draw_arc (stroke_gc, False, 0, y, w, h-1, 90*64, 180*64)

						window.draw_rectangle (fill_gc, True, w/2, y+1, w/2, h-1)
						window.draw_line (stroke_gc, w/2, y, w, y)
						window.draw_line (stroke_gc, w/2, y+h-1, w, y+h-1)

					# draw a circle for break points
					if self.mode.mode == Editor.Mode.RUN:
						if iter.get_line() in self.breakpoints:
							color = gtk.gdk.Color (237 << 8, 146 << 8, 146 << 8, 0)
							gc = event.window.new_gc()
							gc.set_rgb_fg_color (color)
							color = gtk.gdk.Color (180 << 8, 110 << 8, 110 << 8, 0)
							out_gc = event.window.new_gc()
							out_gc.set_rgb_fg_color (color)

							w = self.get_border_window_size (gtk.TEXT_WINDOW_LEFT)
							h = rect.height
							window.draw_arc (gc, True, 0, y, w, h, 0, 360*64)
							window.draw_arc (out_gc, False, 0, y, w-1, h-1, 0, 360*64)

					if line >= 0:
						text = str (line).rjust (self.margin_digits, " ")  # align at right

						if iter.get_line() == curline:
							text = "<b>" + text + "</b>"
						if self.mode.mode != Editor.Mode.EDIT:
							text = "<span foreground=\"blue\">" + text + "</span>"

						layout.set_markup (text)
						self.style.paint_layout (window, gtk.STATE_NORMAL, False, event.area,
						                         self, "", 2, y, layout)
				if last_loop:
					break
				if not iter.forward_line():
					last_loop = True

		# text window -- highlight current line
		window = self.get_window (gtk.TEXT_WINDOW_TEXT)
		if event.window == window:
			# do the current line highlighting now
			iter = self.get_buffer().get_iter_at_line (curline)
			y, h = self.get_line_yrange (iter)
			x, y = self.buffer_to_window_coords (gtk.TEXT_WINDOW_TEXT, 0, y)
			w = self.allocation.width
			"""
			rect = self.get_iter_location (iter)
			x, y = self.buffer_to_window_coords (gtk.TEXT_WINDOW_TEXT, 0, rect.y)
			w = self.allocation.width
			h = rect.height
			"""

			window.draw_rectangle (fill_gc, True, x, y, w, h)
			if stroke_gc != None:
				window.draw_line (stroke_gc, x, y, w, y)
				window.draw_line (stroke_gc, x, y + h - 1, w, y + h - 1)

		return gtk.TextView.do_expose_event (self, event)

	# button pressed on numbering pane -- move cursor to that line
	# for two clicks, set break point
	# parent is a hook to be able to access Interface
	def do_button_press_event (self, event):
		gtk.TextView.do_button_press_event (self, event)
		parent = self.main_parent
		if event.window == self.get_window (gtk.TEXT_WINDOW_LEFT):
			x, y = self.window_to_buffer_coords (gtk.TEXT_WINDOW_LEFT,
			                                     int (event.x), int (event.y))
			it = self.get_iter_at_location (x, y)
			self.get_buffer().place_cursor (it)

			if event.type == gtk.gdk._2BUTTON_PRESS and self.mode.mode == Editor.Mode.RUN:
				line = it.get_line()
				vpu = parent.vpu.vpu

				# see if there is already one -- if so, remove it
				if line in self.breakpoints:  # remove it
					try:
						i = vpu.lines.index (line+1)
					except ValueError:
						parent.message.write ("%s %s" % ("Cannot clear a break point in line",
						                      line+1), "white")
					else:
						try:
							vpu.clearbreak (i)
						except:
							parent.message.write ("Error: %s, %s" % (sys.exc_type,
							                      sys.exc_value), "red")
						else:
							self.breakpoints.remove (line)
				else:  # add break point
					try:
						i = vpu.lines.index (line+1)
					except ValueError:
						parent.message.write ("%s %s" % ("Cannot set a break point in line",
						                      line+1), "white")
					else:
						try:
							vpu.setbreak (i)
						except:
							parent.message.write ("Error: %s, %s" % (sys.exc_type, sys.exc_value),
							                      "red")
						else:
							self.breakpoints.append (line)

	def reload_breakpoints (self, vpu):
		for i in self.breakpoints:
			pt = vpu.lines.index (i+1)
			vpu.setbreak (pt)

	# we use this so we know when lines are inserted or removed and change the
	# line numbering border accordingly
	def text_changed (self, buffer):
		digits = max (digits_on (buffer.get_line_count()), 2)
		if digits != self.margin_digits:
			self.margin_digits = digits
			margin = (self.digit_width * digits) + 4
			self.set_border_window_size (gtk.TEXT_WINDOW_LEFT, margin)

	# Printing support
	def print_text (self, parent_window, title):
		print_data = self.PrintData()
		print_data.header_title = title
		print_op = gtk.PrintOperation()

		if self.settings != None:
			print_op.set_print_settings (self.settings)
  
		print_op.connect ("begin-print", self.print_begin_cb, print_data)
		print_op.connect ("draw-page", self.print_page_cb, print_data)

		try:
			res = print_op.run (gtk.PRINT_OPERATION_ACTION_PRINT_DIALOG, parent_window)
		except gobject.GError, ex:
			error_dialog = gtk.MessageDialog(main_window,
				gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
				"Error printing file:\n%s" % str (ex))
			error_dialog.run()
			error_dialog.destroy()
		else:
			if res == gtk.PRINT_OPERATION_RESULT_APPLY:
				self.settings = print_op.get_print_settings()

	class PrintData:
		layout = None
		page_breaks = None
		header_title = None
		header_height = 0
		header_layout = None

	def print_begin_cb (self, operation, context, print_data):
		width = context.get_width()
		height = context.get_height()
		print_data.layout = context.create_pango_layout()
		print_data.layout.set_font_description (pango.FontDescription ("Monospace 12"))
		print_data.layout.set_width (int (width * pango.SCALE))
		# create a layout based on the text with applied tags for printing
		it = self.get_buffer().get_start_iter()
		text = ""
		tags = self.get_buffer().get_tag_table()
		comment_tag = tags.lookup ("comment")
		assign_tag = tags.lookup ("assign")
		instruction_tag = tags.lookup  ("instruction")
		while not it.is_end():
			if it.ends_tag (None):
				text += "</span>"
			if it.starts_line():
				text += "<span weight='normal' style='normal' foreground='black'>"
				text += str (it.get_line()+1).rjust (self.margin_digits, " ")
				text += "</span>  "
			if it.begins_tag (comment_tag):
				text += "<span foreground='darkgrey' style='oblique'>"
			if it.begins_tag (assign_tag):
				text += "<span foreground='darkred'>"
			if it.begins_tag (instruction_tag):
				text += "<span weight='bold'>"
			text += it.get_char()
			it.forward_char()
		print_data.layout.set_markup (text)

		print_data.header_layout = context.create_pango_layout()
		print_data.header_layout.set_font_description (pango.FontDescription ("Sans 12"))
		print_data.header_layout.set_width (int (width * pango.SCALE))
		print_data.header_layout.set_text ("title")
		header_height = print_data.header_layout.get_extents()[1][3] / 1024.0
		print_data.header_height = header_height + 10

		num_lines = print_data.layout.get_line_count()
		page_breaks = []
		page_height = 0

		for line in xrange (num_lines):
			layout_line = print_data.layout.get_line (line)
			ink_rect, logical_rect = layout_line.get_extents()
			lx, ly, lwidth, lheight = logical_rect
			line_height = lheight / 1024.0
			if page_height + line_height + header_height > height:
				page_breaks.append (line)
				page_height = 0
			page_height += line_height

		operation.set_n_pages (len (page_breaks) + 1)
		print_data.page_breaks = page_breaks

	def print_page_cb (self, operation, context, page_nr, print_data):
		assert isinstance (print_data.page_breaks, list)
		if page_nr == 0:
			start = 0
		else:
			start = print_data.page_breaks [page_nr - 1]
		try:
			end = print_data.page_breaks [page_nr]
		except IndexError:
			end = print_data.layout.get_line_count()

		cr = context.get_cairo_context()
		cr.set_source_rgb(0, 0, 0)

		# print page header
		header_height = print_data.header_height
		header_layout = print_data.header_layout
		cr.move_to (0, header_height-4)
		cr.line_to (context.get_width(), header_height-4)
		cr.stroke()
		if print_data.header_title != None:
			cr.move_to (6, 3)
			header_layout.set_text (print_data.header_title)
			cr.show_layout (header_layout)
		header_layout.set_text ("Page %s of %s" % (page_nr+1,
		                        len (print_data.page_breaks)+1))
		x = header_layout.get_extents()[1][2] / 1024.0
		x = context.get_width() - x
		cr.move_to (x-6, 3)
		cr.show_layout (header_layout)

		# print body -- the text
		cr.set_source_rgb (0, 0, 0)
		i = 0
		start_pos = 0
		iter = print_data.layout.get_iter()
		while True:
			if i >= start:
				line = iter.get_line()
				_, logical_rect = iter.get_line_extents()
				lx, ly, lwidth, lheight = logical_rect
				baseline = iter.get_baseline()
				if i == start:
					start_pos = ly / 1024.0;
				cr.move_to (lx / 1024.0, baseline / 1024.0 - start_pos + header_height)
				cr.show_layout_line (line)
			i += 1
			if not (i < end and iter.next_line()):
				break

gobject.type_register (Editor)

# A very-visible colored-enabled message label
# NOTE: gtk.Label doesn't have a background and we shouldn't use a gtk.EventBox
# container because gtk-qt-engine doesn't honor its background, so we draw it
# ourselves.
class MessageLabel (gtk.Label):
	def __init__ (self):
		gtk.Label.__init__ (self)
		self.set_padding (0, 6)
		self.set_line_wrap (True)
		font = pango.FontDescription()
		font.set_weight (pango.WEIGHT_BOLD)
		font.set_size (12 * pango.SCALE)
		self.modify_font (font)

	def write (self, text, bg_color):
		if text == "":  # avoids asking for different sizes...
			text = " "
		if self.window != None:
			self.set_text (text)
			self.modify_bg (gtk.STATE_NORMAL, gtk.gdk.color_parse (bg_color))
			# if we want to also have a text_color parameter:
			#self.modify_fg (gtk.STATE_NORMAL, gtk.gdk.color_parse (text_color))

	def do_expose_event (self, event):
		self.style.paint_box (self.window, gtk.STATE_NORMAL, gtk.SHADOW_OUT, event.area,
		                      self, None, self.allocation.x, self.allocation.y,
		                      self.allocation.width, self.allocation.height)
		return gtk.Label.do_expose_event (self, event)

gobject.type_register (MessageLabel)

# A GtkEntry that only accepts numbers
class DigitEntry (gtk.Entry):
	def __init__ (self, can_be_negative = False, default_number = 0):
		gtk.Entry.__init__ (self)
		self.can_be_negative = can_be_negative
		self.set_value (default_number)

		self.connect ("insert-text", self.insert_text_cb)
		self.connect ("focus-out-event", self.focus_out_event_cb)

	def set_value (self, number):
		self.set_text (str (number))
	def get_value (self):
		try: value = int (self.get_text())
		except ValueError: return 0
		return value

	def insert_text_cb (self, editable, text, length, pos_ptr):
		pos = self.get_position()
		if not ((self.can_be_negative and pos == 0 and text == '-') or text.isdigit()):
			editable.emit_stop_by_name ("insert_text")
			gtk.gdk.beep()

	def focus_out_event_cb (self, widget, event):
		if self.get_text() == "":
			self.set_value (0)
		return False

# Explicit ratio horizontal box
# Simple stuff: don't care for widgets sizes
class RatioHBox (gtk.Container):
	def __init__ (self, padding):
		gtk.Container.__init__ (self)

		self.set_flags (gtk.NO_WINDOW)
		self.set_redraw_on_allocate (False)

		self.padding = padding
		self.sum_ratios = 0
		self.children = []  # of (gtk.Widget, ratio)

	def pack (self, child, ratio):
		self.children.append ((child, ratio))
		self.sum_ratios += ratio
		child.set_parent (self)

	def do_add (self, child):
		self.pack (child, 1)

	def do_remove (self, child):
		for i in self.children:
			if i[0] == child:
				self.sum_ratios -= i[1]
				self.children.remove (i)
				child.unparent()
				break

	def do_child_type (self):
		return gtk.TYPE_WIDGET

	def do_forall (self, include_internals, callback, callback_data):
		for i in self.children:
			callback (i[0], callback_data)

	def do_size_request (self, req):
		req.width = req.height = 0
		for child, ratio in self.children:
			size = child.size_request()
			req.height = max (req.height, size[1])

	def do_size_allocate (self, allocate):
		child_alloc = gtk.gdk.Rectangle (allocate.x, allocate.y, 0, allocate.height)
		width = allocate.width - (len (self.children)-1)*self.padding

		for child, ratio in self.children:
			child_alloc.width = (width * ratio) / self.sum_ratios
			child.size_allocate (child_alloc)
			child_alloc.x += child_alloc.width + self.padding

gobject.type_register (RatioHBox)

# The setup dialog
def read_config():
	config = ConfigParser.ConfigParser ()
	config.read (APOO_CONFIG_FILE)

	global shortcuts_style, mirror_memory
	if config.has_option ("appearance", "keys-shortcuts"):
		shortcuts_style = config.get ("appearance", "keys-shortcuts")
	if config.has_option ("appearance", "memory-mirror"):
		mirror_memory = config.get ("appearance", "memory-mirror")

	global registers_nb, ram_size, max_steps, input_output, output_ascii, output_cr
	if config.has_option ("vpu", "registers-nb"):
		registers_nb = config.getint ("vpu", "registers-nb")
	if config.has_option ("vpu", "ram-size"):
		ram_size = config.getint ("vpu", "ram-size")
	if config.has_option ("vpu", "max-steps"):
		max_steps = config.getint ("vpu", "max-steps")
	if config.has_option ("vpu", "input-output-mem"):
		input_output = config.getint ("vpu", "input-output-mem")
	if config.has_option ("vpu", "output-ascii-mem"):
		output_ascii = config.getint ("vpu", "output-ascii-mem")
	if config.has_option ("vpu", "output-cr-mem"):
		output_cr = config.getint ("vpu", "output-cr-mem")

	global default_dir
	if config.has_option ("session", "default-dir"):
		default_dir = config.get ("session", "default-dir")

def write_config():
	config = ConfigParser.ConfigParser ()

	config.add_section ("appearance")
	config.set ("appearance", "keys-shortcuts", shortcuts_style)
	config.set ("appearance", "memory-mirror", mirror_memory)

	config.add_section ("vpu")
	config.set ("vpu", "registers-nb", int (registers_nb))
	config.set ("vpu", "ram-size", int (ram_size))
	config.set ("vpu", "max-steps", int (max_steps))
	config.set ("vpu", "input-ouput-mem", int (input_output))
	config.set ("vpu", "output-ascii-mem", int (output_ascii))
	config.set ("vpu", "output-cr-mem", int (output_cr))

	if default_dir != None:
		config.add_section ("session")
		config.set ("session", "default-dir", default_dir)

	file = open (APOO_CONFIG_FILE, 'w')
	config.write (file)
	file.close()

class Preferences (gtk.Dialog):
	def __init__ (self):
		gtk.Dialog.__init__ (self, "Preferences", None, 0,
		                     (gtk.STOCK_REVERT_TO_SAVED, 1, gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
		self.set_default_response (gtk.RESPONSE_CLOSE)
		self.set_has_separator (False)
		self.set_resizable (False)

		look_feel_box = gtk.VBox (False, 6)
		vpu_box = gtk.VBox (False, 6)

		# key shortcuts stuff
		self.desktop_keys = gtk.RadioButton (label = "_Desktop definitions")
		self.emacs_keys = gtk.RadioButton (label = "_Emacs defaults", group = self.desktop_keys)
		# set this data, so we can differ them
		keys_box = gtk.VBox (True, 2)
		keys_box.pack_start (self.desktop_keys)
		keys_box.pack_start (self.emacs_keys)
		if shortcuts_style == "emacs":
			self.emacs_keys.set_active (True)
			# the other is the default anyway
		self.desktop_keys.connect ("toggled", self.desktop_keys_cb)
		self.emacs_keys.connect ("toggled", self.emacs_keys_cb)

		# mirror memory stuff
		self.mirror_title = gtk.CheckButton ("<b>_Mirror Memory</b>")
		self.mirror_title.child.set_use_markup (True)
		self.mirror_hor = gtk.RadioButton (label = "_Horizontally")
		self.mirror_ver = gtk.RadioButton (label = "_Vertically", group = self.mirror_hor)
		mirror_box = gtk.VBox (True, 2)
		mirror_box.pack_start (self.mirror_hor)
		mirror_box.pack_start (self.mirror_ver)

		self.mirror_frame = self.create_frame (None, mirror_box)
		self.mirror_frame.set_label_widget (self.mirror_title)

		if mirror_memory == "no":
			self.mirror_frame.child.set_sensitive (False)
		else:
			self.mirror_title.set_active (True)
			if mirror_memory == "ver":
				self.mirror_ver.set_active (True)

		self.mirror_title.connect ("toggled", self.mirror_memory_cb)
		self.mirror_hor.connect ("toggled", self.mirror_memory_cb)
		self.mirror_ver.connect ("toggled", self.mirror_memory_cb)

		look_feel_box.pack_start (self.create_frame ("Key Shortcuts", keys_box), False)
		look_feel_box.pack_start (self.mirror_frame, False)

		self.regs_entry = DigitEntry (False, registers_nb)
		self.ram_entry = DigitEntry (False, ram_size)
		self.steps_entry = DigitEntry(False, max_steps)
		self.in_out_entry = DigitEntry (False, input_output)
		self.ascii_out_entry = DigitEntry (False, output_ascii)
		self.cr_out_entry = DigitEntry (False, output_cr)

		self.regs_entry.connect_after ("changed", self.regs_changed_cb)
		self.ram_entry.connect_after ("changed", self.ram_changed_cb)
		self.steps_entry.connect_after ("changed", self.steps_changed_cb)
		self.in_out_entry.connect_after ("changed", self.in_out_changed_cb)
		self.ascii_out_entry.connect_after ("changed", self.ascii_out_changed_cb)
		self.cr_out_entry.connect_after ("changed", self.cr_out_changed_cb)

		cpu_grid = self.create_grid ("Machine Processor",
			[ ("_Number of registers", self.regs_entry),
			  ("_RAM size", self.ram_entry),
			  ("_Maximum steps", self.steps_entry) ] )
		mem_grid = self.create_grid ("Memory Mapping",
			[ ("_Integer input/output", self.in_out_entry),
			  ("_ASCII output", self.ascii_out_entry),
			  ("_CR output", self.cr_out_entry) ] )

		info_box = gtk.HBox (False, 6)
		info_box.set_border_width (6)
		image = gtk.Image()
		image.set_from_stock (gtk.STOCK_DIALOG_INFO, gtk.ICON_SIZE_BUTTON)
		label = gtk.Label ("Changes will take effect on Load.")
		info_box.pack_start (image, False)
		info_box.pack_start (label, False)
		info_align = gtk.Alignment (0.5, 0, 0, 0)
		info_align.add (info_box)

		vpu_box.pack_start (cpu_grid, False)
		vpu_box.pack_start (mem_grid, False)
		vpu_box.pack_start (info_align, False)

		self.notebook = gtk.Notebook()
		self.notebook.append_page (look_feel_box, gtk.Label ("_Look 'n Feel"))
		self.notebook.append_page (vpu_box,  gtk.Label ("_VPU"))
		# we need to set the mnemonic in effect manually
		for i in self.notebook.get_children():
			label = self.notebook.get_tab_label (i)
			label.set_use_underline (True)
			label.set_mnemonic_widget (i)

		self.notebook.set_border_width (6)
		self.notebook.show_all()
		self.vbox.pack_start (self.notebook)

		self.connect ("response", self.response)
		self.connect ("delete-event", self.hide_on_delete)

	def response (self, dialog, response_id):
		if response_id == gtk.RESPONSE_NONE or response_id == gtk.RESPONSE_CLOSE:
			dialog.hide()
		if response_id == 1:  # revert
			# load defaults
			if SHORTCUTS_STYLE == "emacs":
				self.emacs_keys.set_active (True)
			else:
				self.desktop_keys.set_active (True)

			if MIRROR_MEMORY == "no":
				self.mirror_title.set_active (False)
			else:
				if MIRROR_MEMORY == "ver":
					self.mirror_ver.set_active (True)
				else:
					self.mirror_hor.set_active (True)
				self.mirror_title.set_active (True)

			self.regs_entry.set_value (REGISTERS_NB)
			self.ram_entry.set_value (RAM_SIZE)
			self.steps_entry.set_value (MAX_STEPS)
			self.in_out_entry.set_value (INPUT_OUTPUT)
			self.ascii_out_entry.set_value (OUTPUT_ASCII)
			self.cr_out_entry.set_value (OUTPUT_CR)

	def regs_changed_cb (self, entry):
		global registers_nb
		registers_nb = entry.get_value()
		return False

	def ram_changed_cb (self, entry):
		global ram_size
		ram_size = entry.get_value()
		return False

	def steps_changed_cb (self, entry):
		global max_steps
		max_steps = entry.get_value()
		return False

	def in_out_changed_cb (self, entry):
		global input_output
		input_output = entry.get_value()
		return False

	def ascii_out_changed_cb (self, entry):
		global output_ascii
		output_ascii = entry.get_value()
		return False

	def cr_out_changed_cb (self, entry):
		global output_cr
		output_cr = entry.get_value()
		return False

	def shortcut_keys_changed (self):
		for i in windows:
			i.load_menu()

	def desktop_keys_cb (self, button):
		global shortcuts_style
		if button.get_active():
			shortcuts_style = "desktop"
			self.shortcut_keys_changed()

	def emacs_keys_cb (self, button):
		global shortcuts_style
		if button.get_active():
			shortcuts_style = "emacs"
			self.shortcut_keys_changed()

	def mirror_memory_cb (self, widget):
		global mirror_memory
		if widget == self.mirror_title:
			mirror_memory = "no"
			if widget.get_active():
				if self.mirror_hor.get_active():
					widget = self.mirror_hor
				else:
					widget = self.mirror_ver
			self.mirror_frame.child.set_sensitive (widget.get_active())
		if widget == self.mirror_hor:
			mirror_memory = "hor"
		elif widget == self.mirror_ver:
			mirror_memory = "ver"
		for i in windows:
			for j in i.notebook.get_children():
				j.create_memory_table()

	# to cut down on code size
	def create_frame (self, title, widget):
		if title == None:
			frame = gtk.Frame()
		else:
			frame = gtk.Frame ("<b>" + title + "</b>")
			frame.get_label_widget().set_use_markup (True)
		frame.set_shadow_type (gtk.SHADOW_NONE)
		frame.set_border_width (6)

		# the sole purpose of the box is to set border and padding
		box = gtk.HBox (False, 0)
		box.pack_start (widget, padding = 11)
		box.set_border_width (4)
		frame.add (box)
		return frame

	def create_grid (self, title, entries):
		table = gtk.Table (2, len (entries))
		for i in entries:
			label = gtk.Label (i[0] + ":")
			widget = i[1]
			row = entries.index (i)
			table.attach (label, 0, 1, row, row+1, xoptions = gtk.FILL, yoptions = gtk.FILL)
			table.attach (widget, 1, 2, row, row+1, xoptions = gtk.FILL, yoptions = gtk.FILL)

			label.set_use_underline (True)
			label.set_mnemonic_widget (widget)
			label.set_alignment (0.0, 0.5)

		table.set_col_spacings (6)
		table.set_row_spacings (6)
		return self.create_frame (title, table)

preferences_dialog = None
def preferences_show (window):
	global preferences_dialog
	if preferences_dialog == None:
		preferences_dialog = Preferences()
	preferences_dialog.set_transient_for (window)
	preferences_dialog.notebook.set_current_page (0)
	preferences_dialog.present()

## The table stack pointer renderer
class CellRendererStackPointer (gtk.GenericCellRenderer):
	ARROW_WIDTH = ARROW_HEIGHT = 8
	# pointer enum
	POINTER_NONE   = 0
	POINTER_RF     = 1
	POINTER_MIDDLE = 2
	POINTER_RS     = 3
	POINTER_SAME   = 4

	__gproperties__ = {
		'pointer': (gobject.TYPE_INT, 'pointer property',
		             'Pointer relatively to the data being pointed to.',
		             0, 4, POINTER_NONE, gobject.PARAM_READWRITE),
    }

	def __init__(self):
		self.__gobject_init__()
		self.pointer = self.POINTER_NONE

	def do_get_property(self, pspec):
		if pspec.name == "pointer":
			return self.pointer
		else:
			raise AttributeError, 'unknown property %s' % pspec.name

	def do_set_property (self, pspec, value):
		if pspec.name == "pointer":
			self.pointer = value
			self.notify ("pointer")
		else:
			raise AttributeError, 'unknown property %s' % pspec.name

	def create_layout (self, widget, ptr):
		layout = pango.Layout (widget.get_pango_context())
		if ptr == self.POINTER_RF:
			layout.set_text ("rf")
		elif ptr == self.POINTER_RS:
			layout.set_text ("rs")
		else:
			layout.set_text ("r")
		return layout

	def do_render (self, window, widget, bg_area, cell_area, expose_area, flags):
		if self.pointer == self.POINTER_NONE:
			return

		bg_gc = window.new_gc()
		bg_gc.set_rgb_fg_color (get_tone_color (widget.style, 255))
		fg_gc = window.new_gc()
		fg_gc.set_rgb_fg_color (get_tone_color (widget.style, 140))
		fg_gc.set_line_attributes (2, gtk.gdk.LINE_SOLID, gtk.gdk.CAP_ROUND,
		                           gtk.gdk.JOIN_MITER)

		# pointer drawing
		x = cell_area.x
		y = bg_area.y
		w = cell_area.width  # self.ARROW_WIDTH
		h = bg_area.height
		if self.pointer == self.POINTER_MIDDLE:
			window.draw_line (fg_gc, x + w/2, y, x + w/2, y+h)

		if self.pointer != self.POINTER_MIDDLE:
			x = cell_area.x
			w = self.ARROW_WIDTH
			y = cell_area.y + cell_area.height/2
			h = self.ARROW_HEIGHT

			points = [ (x, y), (x + w, y - h/2), (x + w, y + h/2) ]
			window.draw_polygon (bg_gc, True, points)
			window.draw_polygon (fg_gc, False, points)

			layout = self.create_layout (widget, self.pointer)
			lw, lh = layout.get_pixel_size()
			lx = cell_area.x + self.ARROW_WIDTH + 4
			ly = (cell_area.height - lh)/2 + cell_area.y

			widget.style.paint_layout (window, gtk.STATE_NORMAL, True, expose_area,
			                           widget, None, lx, ly, layout)

	def do_get_size (self, widget, cell_area):
		layout = self.create_layout (widget, self.POINTER_RS)
		w, h = layout.get_pixel_size()
		h = max (h, self.ARROW_HEIGHT)
		w += self.ARROW_WIDTH + 6
		return 0, 0, w, h

# Doesn't need to be registered, since it is a PyGtk instance
#gobject.type_register (CellRendererStackPointer)

class ButtonWithSpin (gtk.Button):
	def __init__ (self, label):
		gtk.Button.__init__ (self, label)
		self.label = label
		self.value = 1
		self.popup = gtk.Menu()
		for i in xrange (1,21):
			item = gtk.MenuItem (str (i))
			item.connect ("activate", self.popup_menu_item_cb, i)
			item.show()
			self.popup.append (item)
		self.popup.attach_to_widget (self, None)

	def get_value (self):
		return self.value

	def set_value (self, value):
		self.value = value
		label = self.label + " " + str (value)
		self.set_label (label)

	def popup_menu_item_cb (self, item, value):
		self.set_value (value)
	def do_button_press_event (self, event):
		gtk.Button.do_button_press_event (self, event)
		if event.button == 3:
			self.popup.popup (None, None, None, 3, event.time)

gobject.type_register (ButtonWithSpin)

## VPU Model

class VpuModel:
	class ListModel (gtk.GenericTreeModel):
		def __init__ (self, list):
			gtk.GenericTreeModel.__init__ (self)
			self.list = list
		def on_get_flags (self):
			return gtk.TREE_MODEL_ITERS_PERSIST|gtk.TREE_MODEL_LIST_ONLY	
		def on_get_iter (self, path):
			index = path[0]
			if index < len (self.list):
				return index
			return None
		def on_get_path (self, index):
			return (index,)
		def on_iter_next (self, index):
			if index+1 < len (self.list):
				return index+1
			return None

		def on_iter_has_child (self, iter):
			return False
		def on_iter_parent(self, child):
			return None
		def on_iter_n_children (self, iter):
			if iter == None:
				len (self.list)
			return 0
		def on_iter_nth_child (self, parent, n):
			if n < len (self.list):
				return [n]
			return None
		def on_iter_children (self, parent):
			return self.on_iter_nth_child (parent, 0)

	class RamModel (ListModel):
		def __init__ (self, vpu):
			VpuModel.ListModel.__init__ (self, vpu.RAM)
			self.vpu = vpu

		INDEX_COL = 0
		LABEL_COL = 1
		VALUE_COL = 2
		INDEX_COLOR_COL = 3
		LABEL_COLOR_COL = 4
		VALUE_COLOR_COL = 5
		BACKGROUND_COLOR_COL = 6
		REGS_POINTER_COL = 7
		def on_get_n_columns (self):
			return 8

		def on_get_column_type (self, col):
			if col == self.INDEX_COL:
				return str
			elif col == self.LABEL_COL:
				return str
			elif col == self.VALUE_COL:
				return str
			elif col == self.INDEX_COLOR_COL:
				return str
			elif col == self.LABEL_COLOR_COL:
				return str
			elif col == self.VALUE_COLOR_COL:
				return str
			elif col == self.BACKGROUND_COLOR_COL:
				return gtk.gdk.Color
			elif col == self.REGS_POINTER_COL:
				return int

		def on_get_value (self, index, col):
			if col == self.INDEX_COL:
				return str (index)
			elif col == self.LABEL_COL:
				label = reverse_lookup (self.vpu.labelm, index)
				if label == None:
					label = ""
				return label
			elif col == self.VALUE_COL:
				return str (self.list [index])
			elif col == self.INDEX_COLOR_COL:
				if index in self.vpu.mem_changed:
					return "red"
				return "blue"
			elif col == self.LABEL_COLOR_COL:
				if index in self.vpu.mem_changed:
					return "red"
				return "darkred"
			elif col == self.VALUE_COLOR_COL:
				if index in self.vpu.mem_changed:
					return "red"
				return "black"
			elif col == self.BACKGROUND_COLOR_COL:
				rf = self.vpu.reg [-2]
				rs = self.vpu.reg [-1]
				if index < rf or index > rs:
					if index % 2 == 1:
						return get_color (242, 171, 171)
					return get_color (255, 180, 180)
				if index % 2 == 1:
					return get_color (238, 238, 238)
				return get_color (255, 255, 255)
			elif col == self.REGS_POINTER_COL:
				if len (self.vpu.reg) >= 2:
					rf = self.vpu.reg [-2]
					rs = self.vpu.reg [-1]
					if index == rf:
						if index == rs:
							return CellRendererStackPointer.POINTER_SAME
						return CellRendererStackPointer.POINTER_RF
					if index == rs:
						return CellRendererStackPointer.POINTER_RS
					if index > rf and index < rs:
						return CellRendererStackPointer.POINTER_MIDDLE
				return CellRendererStackPointer.POINTER_NONE

		def sync (self):
			changed = {}
			for i in self.vpu.mem_changed:
				changed[i] = True
			for i in self.vpu.last_mem_changed:
				changed[i] = True
			rf = self.vpu.reg [-2]
			rs = self.vpu.reg [-1]
			last_rf = self.vpu.last_reg [-2]
			last_rs = self.vpu.last_reg [-1]
			if last_rs != rs or last_rf != rf:
				for i in xrange (min (last_rf, last_rs), max (last_rf, last_rs)+1):
					changed[i] = True
				for i in xrange (min (rf, rs), max (rf, rs)+1):
					changed[i] = True
			for i in changed:
				if i >= 0:
					path = (i,)
					iter = self.get_iter (path)
					self.row_changed (path, iter)

	class RegModel (ListModel):
		def __init__ (self, vpu):
			VpuModel.ListModel.__init__ (self, vpu.reg)
			self.vpu = vpu

		INDEX_COL = 0
		LABEL_COL = 1
		VALUE_COL = 2
		COLOR_COL = 3
		def on_get_n_columns (self):
			return 4

		def on_get_column_type (self, col):
			if col == self.INDEX_COL:
				return str
			elif col == self.LABEL_COL:
				return str
			elif col == self.VALUE_COL:
				return str
			elif col == self.COLOR_COL:
				return str

		def on_get_value (self, index, col):
			if col == self.INDEX_COL:
				return "R%d" % index
			elif col == self.LABEL_COL:
				if self.vpu.nreg >= 2:
					if index == self.vpu.nreg-2:
						return "RF"
					elif index == self.vpu.nreg-1:
						return "RS"
				return ""
			elif col == self.VALUE_COL:
				return str (self.list [index])
			elif col == self.COLOR_COL:
				if index in self.vpu.reg_changed:
					return "red"
				return "black"

		def sync (self):
			changed = {}
			for i in self.vpu.reg_changed:
				changed[i] = True
			for i in self.vpu.last_reg_changed:
				changed[i] = True
			for i in changed:
				path = (i, )
				iter = self.get_iter (path)
				self.row_changed (path, iter)

	class Listener:
		def set_ram_model (self, model): pass
		def set_reg_model (self, model): pass
		def set_ram_scroll (self, path): pass
		def set_reg_scroll (self, path): pass
		def set_output_buffer (self, buffer): pass
		def set_program_counter (self, value): pass
		def set_timer_counter (self, value): pass
		def set_message (self, message, status, color): pass
		def get_program_code (self): pass

	def __init__ (self, listener):
		self.listener = listener
		self.ram_model = None
		self.reg_model = None

	def load (self):
		self.vpu = Vpu (registers_nb,
		                { output_ascii:("val = 0", "self.Inter.output_inst (val, True)"),
		                  input_output:("val = self.Inter.input_inst()",
		                                "self.Inter.output_inst (val)"),
		                  output_cr:("val = 0", "self.Inter.output_inst()") }, self,
		                ram_size)
		self.vpu.last_reg = self.vpu.reg
		self.vpu.mem_changed = []
		self.vpu.reg_changed = []
		self.vpu.last_mem_changed = []
		self.vpu.last_reg_changed = []

		program = self.listener.get_program_code()
		try:
			self.vpu.load (program)
		except vpuLoadError,error:
			message = "Parsing Error (Ln %d): %s" % (error.line, error.message)
			self.listener.set_message (message, "parsing error", "red", error.line)
			return False
		except:
			message = "Parsing Error: %s, %s" % (sys.exc_type, sys.exc_value)
			self.listener.set_message (message, "parsing error", "red")
			return False

		self.listener.set_message ("Program Loaded", "loaded", "white")
		self.ram_model = VpuModel.RamModel (self.vpu)
		self.reg_model = VpuModel.RegModel (self.vpu)
		self.listener.set_ram_model (self.ram_model)
		self.listener.set_reg_model (self.reg_model)
		self.output_buffer = gtk.TextBuffer()
		self.listener.set_output_buffer (self.output_buffer)

		self.sync()
		return True

	def clear (self):
		self.ram_model = None
		self.reg_model = None
		self.output_buffer = None
		self.listener.set_ram_model (None)
		self.listener.set_reg_model (None)
		self.listener.set_output_buffer (None)
		self.listener.set_program_counter (0)
		self.listener.set_timer_counter (0)
		self.vpu = None

	def sync (self):
		self.ram_model.sync()
		self.reg_model.sync()
		if len (self.vpu.mem_changed) > 0:
			self.listener.set_ram_scroll ((self.vpu.mem_changed[0],))
		if len (self.vpu.reg_changed) > 0:
			self.listener.set_reg_scroll ((self.vpu.reg_changed[0],))

		self.listener.set_program_counter (self.vpu.PC)
		self.listener.set_timer_counter (self.vpu.time)

	def advance (self, steps_nb, honor_breakpoint):
		if self.ram_model == None: return  # not loaded
		self.listener.set_message ("Running", "running", "white")

		self.vpu.last_mem_changed = self.vpu.mem_changed[:]
		self.vpu.last_reg_changed = self.vpu.reg_changed[:]

		step = 0
		while True:
			self.vpu.last_reg = self.vpu.reg[:]
			self.vpu.mem_changed = []
			self.vpu.reg_changed = []

			try:
				mem_changed = self.vpu.step()
				if mem_changed != (None, None) and not mem_changed[0] in self.vpu.mem_changed:
					self.vpu.mem_changed.append (mem_changed[0])
				if step > max_steps:
					raise TooManySteps (step)
			except OutOfMemory, error:
				message = "%s: memory address %s not reserved" % (error.message, error.add)
				self.message.write (message, "end of program", error.colour)
			except vpuError, error:
				self.listener.set_message (error.message, "end of program", error.colour)
			except:
				message = "Error: %s, %s" % (sys.exc_type, sys.exc_value)
				self.listener.set_message (message, "end of program error", "red")
			else:
				if step != -1:
					step += 1
					if step == steps_nb:
						self.listener.set_message ("Next Step", "running", "white")
						break
				if honor_breakpoint and self._is_on_breakpoint():
					self.listener.set_message ("Continue Program", "at break point", "white")
					break
				continue
			break

		# vpu.mem_changed set while stepping; similar procedure for registers
		for i in xrange (self.vpu.nreg):
			if self.vpu.reg[i] != self.vpu.last_reg[i]:
				self.vpu.reg_changed.append (i)
		self.sync()

	def _is_on_breakpoint (self):
		try:
			line = self.vpu.lines [self.vpu.PC]
			try:
				i = self.vpu.lines.index (line)
			except ValueError:
				return False
			try:
				b = self.vpu.BreakP.index (i)
			except ValueError:
				return False
			return True
		except IndexError:
			return False

	# graphical-dependent instructions
	def output_inst (self, value = '\n', convert_ascii = False):
		if convert_ascii:
			value = ("%c" % value).decode()
			# TODO: validate the string to see whether it is representable
		buffer = self.output_buffer
		buffer.insert (buffer.get_end_iter(), "%s" % value)

	def input_inst (self):
		dialog = gtk.Dialog ("Insert Input", self.listener.get_toplevel(),
		                     gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
		                     (gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
		dialog.set_has_separator (False)
		dialog.set_default_response (gtk.RESPONSE_ACCEPT)

		label = gtk.Label ("Input:")
		entry = DigitEntry (True, 0)
		entry.set_activates_default (True)

		box = gtk.HBox (False, 6)
		box.set_border_width (6)
		box.pack_start (label, expand = False)
		box.pack_start (entry, expand = True)
		box.show_all()
		dialog.vbox.pack_start (box)

		while dialog.run() != gtk.RESPONSE_ACCEPT:
			pass  # force user to accept

		value = entry.get_value()
		dialog.destroy()
		return int (value)

## The view

class Interface (gtk.VBox, VpuModel.Listener):
	def __init__ (self, filename):
		gtk.VBox.__init__ (self)
		self.main_parent = None
		self.vpu = VpuModel (self)

		# Editor (the text view)
		self.editor = Editor (self)
		editor_window = gtk.ScrolledWindow()
		editor_window.add (self.editor)
		editor_window.set_policy (gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
		editor_window.set_shadow_type (gtk.SHADOW_IN)

		# the vpu/editor "status bar"
		statusbar = gtk.HBox (False, 6)

		if gtk.pygtk_version >= (2,10,0):
			# gtk 2.10.0 has introduced a nice way to follow the cursor...
			self.editor_status = gtk.Label ("")
			self.editor_status.set_alignment (0.0, 0.5)
			self.editor.get_buffer().connect ("notify::cursor-position",
				                              self.cursor_moved_cb)
			statusbar.pack_start (self.editor_status, True)

		self.vpu_status = gtk.Label ("ready")
		self.vpu_status.set_alignment (1.0, 0.5)
		statusbar.pack_start (self.vpu_status, True)

		if not test_mode:
			editor_unlock_button = gtk.Button ("_Edit")  # to unlock the editor
			editor_unlock_button.connect ("clicked", self.edit_button_cb)
			editor_unlock_button.set_size_request (80, -1)
			statusbar.pack_start (editor_unlock_button, False)

		editor_box = gtk.VBox (False, 0)
		editor_box.pack_start (editor_window, expand = True)
		editor_box.pack_start (statusbar, expand = False)
		#editor_box.pack_start (gtk.HSeparator(), expand = False, padding = 2)

		# Buttons
		buttons_box = gtk.VBox (True, 0)
		self.load_button = gtk.Button ("_Load")
		self.run_button = gtk.Button ("_Run")
		self.step_button = ButtonWithSpin ("_Step")
		self.continue_button = gtk.Button ("_Continue")
		self.clear_button = gtk.Button ("Cle_ar")

		self.load_button.connect  ("clicked", self.load_button_cb)
		self.run_button.connect   ("clicked", self.run_button_cb)
		self.step_button.connect  ("clicked", self.step_button_cb)
		self.continue_button.connect ("clicked", self.continue_button_cb)
		self.clear_button.connect ("clicked", self.clear_button_cb)

		buttons_box.pack_start (self.load_button)
		buttons_box.pack_start (self.run_button)
		buttons_box.pack_start (self.step_button)
		buttons_box.pack_start (self.continue_button)
		buttons_box.pack_start (self.clear_button)

		# Informative entries (Program counter & timer)
		self.counter, counter_box = self.create_informative ("_Program Counter")
		self.timer, timer_box = self.create_informative ("_Timer")
		self.counter.modify_text (gtk.STATE_NORMAL, gtk.gdk.Color (0, 0, 65500))

		informative_box = gtk.HBox (False, 12)
		informative_box.pack_start (gtk.Label(), expand = True)
		informative_box.pack_start (counter_box, expand = False)
		informative_box.pack_start (timer_box, expand = False)
		informative_box.pack_start (gtk.Label(), expand = True)

		# Output text
		self.output = gtk.TextView()
		set_monospace_font (self.editor)
		self.output.set_editable (False)
		self.output.set_cursor_visible (False)
		self.output.set_size_request (40, -1)

		output_win = gtk.ScrolledWindow()
		output_win.add (self.output)
		output_win.set_policy (gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
		output_win.set_shadow_type (gtk.SHADOW_IN)

		label = gtk.Label ("<span foreground=\"red\"><b>_Output</b></span>")
		label.set_use_markup (True)
		label.set_use_underline (True)
		label.set_mnemonic_widget (self.output)

		output_box = gtk.VBox (False, 4)
		output_box.pack_start (label, expand = False)
		output_box.pack_start (output_win, expand = True)

		# Registers table
		self.registers, registers_win, registers_box = self.create_list ("Re_gisters")
		self.registers.set_search_column (VpuModel.RegModel.INDEX_COL)
		renderer = gtk.CellRendererText()
		renderer.set_property ("cell-background-gdk", gtk.gdk.Color(255<<8, 255<<8, 255<<8))
		column = gtk.TreeViewColumn ("", renderer,
			text = VpuModel.RegModel.LABEL_COL, foreground = VpuModel.RegModel.COLOR_COL)
		column.set_sizing (gtk.TREE_VIEW_COLUMN_FIXED)
		layout = pango.Layout (self.registers.get_pango_context())
		layout.set_text ("RS")
		width, _ = layout.get_pixel_size()
		column.set_fixed_width (width+8)
		column.set_expand (False)
		renderer = gtk.CellRendererText()
		renderer.set_property ("cell-background-gdk", gtk.gdk.Color(255<<8, 255<<8, 255<<8))
		self.registers.append_column (column)
		column = gtk.TreeViewColumn ("", renderer,
			text = VpuModel.RegModel.INDEX_COL, foreground = VpuModel.RegModel.COLOR_COL)
		column.set_expand (True)
		column.set_sizing (gtk.TREE_VIEW_COLUMN_FIXED)
		self.registers.append_column (column)
		renderer = gtk.CellRendererText()
		renderer.set_property ("cell-background-gdk", gtk.gdk.Color(255<<8, 255<<8, 255<<8))
		column = gtk.TreeViewColumn ("", renderer,
			text = VpuModel.RegModel.VALUE_COL, foreground = VpuModel.RegModel.COLOR_COL)
		column.set_expand (True)
		column.set_sizing (gtk.TREE_VIEW_COLUMN_FIXED)
		self.registers.append_column (column)

		# A memory box will be created to allow for easy replacement
		self.memory_box = gtk.EventBox()
		self.create_memory_table()

		# Message label
		self.message = MessageLabel()

		# so we can set a border to it
		message_box = gtk.EventBox()
		message_box.add (self.message)
		message_box.set_border_width (6)

		# Layout
		editor_buttons_box = gtk.HBox (False, 12)
		editor_buttons_box.pack_start (editor_box, expand = True)
		editor_buttons_box.pack_start (buttons_box, expand = False)
		editor_buttons_box.set_border_width (6)

		lists_box = RatioHBox (12)
		lists_box.pack (output_box, 1)
		lists_box.pack (registers_box, 1)
		lists_box.pack (self.memory_box, 2)

		informations_box = gtk.VBox (False, 12)
		informations_box.pack_start (informative_box, expand = False)
		informations_box.pack_start (lists_box, expand = True)
		informations_box.set_border_width (6)

		self.editor_lists_pane = gtk.VPaned()
		self.editor_lists_pane.pack1 (editor_buttons_box, True, False)
		self.editor_lists_pane.pack2 (informations_box, True, False)
		self.editor_lists_pane.connect ("size-allocate", self.pane_size_allocate_cb, None)
		self.first_allocate = True

		# main_box usage is to have a border around the widgets
		self.pack_start (self.editor_lists_pane, expand = True)
		self.pack_start (message_box, expand = False)

		self.file_read (filename)
		self.vpu.clear()
		self.show_all()

	def pane_size_allocate_cb (self, widget, alloc, _data):
		# we can't set ratios on the pane sides, so we tune it at first allocate
		if self.first_allocate:
			self.first_allocate = False
			pos = int (alloc.height * 0.60)
			self.editor_lists_pane.set_position (pos)
			self.editor.grab_focus()  # is realized by now

	## Functions to cut down on code size
	def create_list (self, title):
		list = gtk.TreeView()
		list.set_headers_visible (False)
		list.get_selection().set_mode (gtk.SELECTION_NONE)
		if gtk.pygtk_version >= (2,10,0):
			list.set_grid_lines (gtk.TREE_VIEW_GRID_LINES_BOTH)
		list.set_rules_hint (True)
		list.set_fixed_height_mode (True)

		window = gtk.ScrolledWindow()
		window.set_shadow_type (gtk.SHADOW_IN)
		window.set_policy (gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
		window.add (list)

		if title != None:
			label = gtk.Label ("<span foreground=\"red\"><b>" + title + "</b></span>")
			label.set_use_markup (True)
			label.set_use_underline (True)
			label.set_mnemonic_widget (list)

			box = gtk.VBox (False, 4)
			box.pack_start (label, expand = False)
			box.pack_start (window, expand = True)
			return (list, window, box)
		else:
			return (list, window)

	def create_memory_table (self):
		if self.memory_box.child != None:
			self.memory_box.remove (self.memory_box.child)

		memory, memory_win = self.create_list (None)
		self.memory = [memory]
		self.init_memory_table (memory, True, mirror_memory != "hor")

		label = gtk.Label ("<span foreground=\"red\"><b>Memory Data</b></span>")
		label.set_use_markup (True)
		label.set_use_underline (True)
		label.set_mnemonic_widget (memory)

		hbox = gtk.HBox (False, 12)
		hbox.pack_start (memory_win, expand = True)

		child = vbox = gtk.VBox (False, 4)
		vbox.pack_start (label, expand = False)
		vbox.pack_start (hbox, expand = True)

		if mirror_memory != "no":
			memory2, memory2_win = self.create_list (None)
			self.memory += [memory2]
			self.init_memory_table (memory2, mirror_memory == "ver", True)
			if mirror_memory == "hor":
				hbox.pack_start (memory2_win)
			else:
				vbox.pack_start (memory2_win)

		child.show_all()
		self.memory_box.add (child)

	def init_memory_table (self, memory, show_label, show_pointer):
		memory.set_model (self.vpu.ram_model)
		memory.set_headers_visible (True)

		if show_label:
			cell = gtk.CellRendererText()
			column = gtk.TreeViewColumn ("Label", cell,
				text = VpuModel.RamModel.LABEL_COL,
				foreground = VpuModel.RamModel.LABEL_COLOR_COL,
				cell_background_gdk = VpuModel.RamModel.BACKGROUND_COLOR_COL)
			column.set_expand (True)
			column.set_sizing (gtk.TREE_VIEW_COLUMN_FIXED)
			memory.append_column (column)

		cell = gtk.CellRendererText()
		column = gtk.TreeViewColumn ("Address", cell,
			text = VpuModel.RamModel.INDEX_COL,
			foreground = VpuModel.RamModel.INDEX_COLOR_COL,
			cell_background_gdk = VpuModel.RamModel.BACKGROUND_COLOR_COL)
		column.set_expand (True)
		column.set_sizing (gtk.TREE_VIEW_COLUMN_FIXED)
		memory.append_column (column)
		memory.set_search_column (VpuModel.RamModel.INDEX_COL)

		cell = gtk.CellRendererText()
		column = gtk.TreeViewColumn ("Contents", cell,
			text = VpuModel.RamModel.VALUE_COL,
			foreground = VpuModel.RamModel.VALUE_COLOR_COL,
			cell_background_gdk = VpuModel.RamModel.BACKGROUND_COLOR_COL)
		column.set_expand (True)
		column.set_sizing (gtk.TREE_VIEW_COLUMN_FIXED)
		memory.append_column (column)

		if show_pointer:
			cell = CellRendererStackPointer()
			_, _, w, h = cell.do_get_size (memory, None)
			cell.set_fixed_size (w, h)
			column = gtk.TreeViewColumn ("", cell,
				pointer = VpuModel.RamModel.REGS_POINTER_COL,
				cell_background_gdk = VpuModel.RamModel.BACKGROUND_COLOR_COL)
			column.set_fixed_width (w)
			column.set_sizing (gtk.TREE_VIEW_COLUMN_FIXED)
			column.set_expand (False)
			memory.append_column (column)

	def create_informative (self, title):
		entry = gtk.Entry()
		entry.set_editable (False)  # let's make people see the entry is un-editable...
		entry.modify_base (gtk.STATE_NORMAL, entry.style.base [gtk.STATE_INSENSITIVE]);
		entry.set_size_request (40, -1)

		label = gtk.Label ("<span foreground=\"red\"><b>" + title + ":</b></span>")
		label.set_use_markup (True)
		label.set_use_underline (True)
		label.set_mnemonic_widget (entry)

		box = gtk.HBox (False, 4)
		box.pack_start (label, expand = False)
		box.pack_start (entry, expand = False)
		return (entry, box)

	## Interface methods
	def set_editable (self, editable):
		self.message.write ("", "white")
		if editable:
			self.vpu.clear()
			self.set_vpu_status ("editing")
			if gtk.pygtk_version >= (2,10,0):
				self.cursor_moved_cb (self.editor.get_buffer(), 0)
		else:
			self.vpu.load()
			if gtk.pygtk_version >= (2,10,0):
				self.editor_status.set_text ("")
		self.editor.mode.set_mode (self.vpu.vpu)

		self.run_button.set_sensitive (not editable)
		self.step_button.set_sensitive (not editable)
		self.continue_button.set_sensitive (not editable)
		self.clear_button.set_sensitive (not editable)

		if self.main_parent != None:
			self.main_parent.load_menu_sensitive()

	def get_editable (self):
		return self.editor.get_editable()

	def set_vpu_status (self, vpu_status):
		self.vpu_status.set_text ("Status: " + vpu_status)

	## VPU bridge

	# cuts text into a list of instructions, like [(1, ["x", "rtn", "R2"]), ...]
	def get_program_code (self):
		buffer = self.editor.get_buffer()
		program = []
		line = 0
		while line < buffer.get_line_count():
			splits = buffer.split_line (line)
			line += 1
			if splits == None: break
			if len (splits) == 0: continue
			word = splits[0].word
			if splits[0].word[0] == '#':
				continue
			linep = []
			if word[-1] == ':':
				linep.append (word[:-1])
			else:
				linep.append ([])
				linep.append (word)
			for i in xrange (1, len (splits)):
				word = splits[i].word
				if word[0] == '#':
					break
				else:
					linep.append (word)
			program.append ((line, linep))
		return program

	def set_ram_model (self, model):
		for i in self.memory:
			i.set_model (model)
	def set_reg_model (self, model):
		self.registers.set_model (model)

	def set_ram_scroll (self, path):
		self.memory[-1].scroll_to_cell (path)
	def set_reg_scroll (self, path):
		self.registers.scroll_to_cell (path)

	def set_output_buffer (self, buffer):
		if buffer == None:
			buffer = gtk.TextBuffer()
		self.output.set_buffer (buffer)

	def set_program_counter (self, value):
		self.counter.set_text (str (value))
		# set current line to the VPU one
		try: line = self.vpu.vpu.lines [value]
		except: pass
		else:
			self.editor.mode.set_current_line (line)
	def set_timer_counter (self, value):
		self.timer.set_text (str (value))

	def set_message (self, text, status, color, line = -1):
		self.message.write (text, color)
		self.set_vpu_status (status)
		self.editor.mode.set_current_line_color (color)
		self.editor.mode.set_current_line (line)

	# interface callbacks
	def edit_button_cb (self, button):
		self.set_editable (True)
		self.editor.grab_focus()

	def load_button_cb (self, button):
		self.set_editable (False)

	def run_button_cb (self, button):
		self.vpu.advance (-1, False)
	def step_button_cb (self, button):
		self.vpu.advance (button.get_value(), False)
	def continue_button_cb (self, button):
		self.vpu.advance (-1, True)

	def clear_button_cb (self, button):
		self.editor.breakpoints = []
		self.editor.queue_draw()
		self.vpu.BreakP = []
		self.message.write ("All break points removed", "white")

	def cursor_moved_cb (self, buffer, pos_ptr):  # for gtk >= 2.10
		if self.get_editable():
			iter = buffer.get_insert_iter()
			col = iter.get_line_offset() + 1
			lin = iter.get_line() + 1
			status = "Ln %d, Col %d" % (lin, col)
			self.editor_status.set_text (status)

	# file orders -- from menu
	def file_read (self, filename):
		self.set_editable (not test_mode)

		if filename == None:
			buffer = self.editor.get_buffer()
			buffer.delete (buffer.get_start_iter(), buffer.get_end_iter())
		else:
			if not self.editor.get_buffer().read (filename):
				msg = "Couldn't read from file: " + filename
				dialog = gtk.MessageDialog (self.get_toplevel(),
					gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR,
					gtk.BUTTONS_OK, msg)
				dialog.run()
				dialog.destroy()
				filename = None
				if test_mode: sys.exit (2)
		self.filename = filename
		return False

	def file_save (self, filename):
		if self.editor.get_buffer().write (filename):
			self.filename = filename
		else:
			msg = "Couldn't save to file: " + filename
			dialog = gtk.MessageDialog (self.get_toplevel(),
				gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR,
				gtk.BUTTONS_OK, msg)
			dialog.format_secondary_text ("Check file permissions")
			dialog.run()
			dialog.destroy()

	def file_print (self):
		self.editor.print_text (self.main_parent, self.filename)

	# edit orders -- from menu
	def edit_undo (self):
		if not self.editor.get_editable(): return
		self.editor.get_buffer().undo()
	def edit_redo (self):
		if not self.editor.get_editable(): return
		self.editor.get_buffer().redo()

	def edit_can_undo (self):
		return self.editor.get_buffer().can_undo()
	def edit_can_redo (self):
		return self.editor.get_buffer().can_redo()

	def edit_cut (self):
		buffer = self.editor.get_buffer()
		clipboard = gtk.clipboard_get()
		buffer.cut_clipboard (clipboard, self.editor.get_editable())
	def edit_copy (self):
		buffer = self.editor.get_buffer()
		clipboard = gtk.clipboard_get()
		buffer.copy_clipboard (clipboard)
	def edit_paste (self):
		if not self.editor.get_editable(): return
		buffer = self.editor.get_buffer()
		clipboard = gtk.clipboard_get()
		buffer.paste_clipboard (clipboard, None, True)

	def edit_kill_line (self):
		if not self.editor.get_editable(): return

		buffer = self.editor.get_buffer()
		line = buffer.get_iter_at_mark (buffer.get_insert()).get_line()
		start_it = buffer.get_iter_at_line (line)
		end_it = start_it.copy()
		end_it.forward_line()

		clipboard = gtk.clipboard_get()
		clipboard.set_text (buffer.get_text (start_it, end_it, False))
		buffer.delete (start_it, end_it)

	def edit_yank (self):
		self.edit_paste_cb (item)

	def edit_mark_region (self):
		if not self.editor.get_editable(): return

		buffer = self.editor.get_buffer()
		it = buffer.get_iter_at_mark (buffer.get_insert())
		mark = buffer.get_mark ("emacs-mark")
		if mark:
			buffer.move_mark (mark, it)
		else:
			buffer.create_mark ("emacs-mark", it, True)

	def edit_kill_region (self):
		if not self.editor.get_editable(): return

		buffer = self.editor.get_buffer()
		buffer.delete_selection (True)

	def edit_copy_region_as_kill (self):
		self.edit_cut_cb (item)

	def edit_line_home (self):
		buffer = self.editor.get_buffer()
		it = buffer.get_iter_at_mark (buffer.get_insert())
		it.set_line_offset(0)
		buffer.place_cursor (it)

	def edit_line_end (self):
		buffer = self.editor.get_buffer()
		it = buffer.get_iter_at_mark (buffer.get_insert())
		it.forward_to_line_end()
		buffer.place_cursor (it)

	def edit_buffer_home (self):
		buffer = self.editor.get_buffer()
		it = buffer.get_start_iter()
		buffer.place_cursor (it)

	def edit_buffer_end (self):
		buffer = self.editor.get_buffer()
		it = buffer.get_end_iter()
		buffer.place_cursor (it)

	def edit_delete_right_char (self):
		if not self.editor.get_editable(): return
		buffer = self.editor.get_buffer()
		start_it = buffer.get_iter_at_mark (buffer.get_insert())
		end_it = start_it.copy()
		if end_it.forward_char():
			buffer.delete (start_it, end_it)

gobject.type_register (Interface)

# used as a ref to keep gtk loop alive until there are still windows open, and
# also to apply settings changes to all windows.
windows = []

class Window (gtk.Window):
	def __init__ (self, filenames = [], interface = None):
		gtk.Window.__init__ (self)
		if test_mode:
			self.set_title ("Apoo Tester")
		else:
			self.set_title ("Apoo Workbench")
		self.set_default_size (460, 550)
		self.connect ("delete-event", self.ask_close_window_cb)
		self.connect ("destroy", self.close_window_cb)

		self.menu = gtk.MenuBar()
		# needed for the menu key shortcuts
		self.accel_group = gtk.AccelGroup()
		self.add_accel_group (self.accel_group)
		self.load_menu()

		self.notebook = gtk.Notebook()
		self.notebook.set_group_id (0)
		self.notebook.set_scrollable (True)
		self.notebook.connect ("page-added", self.notebook_page_added_cb)
		self.notebook.connect_after ("page-removed", self.notebook_page_changed_cb)
		self.notebook.connect_after ("switch-page", self.notebook_page_changed_cb)
		self.notebook_popup = gtk.Menu()
		item = gtk.MenuItem ("Move to New Window")
		item.connect ("activate", self.notebook_detach_child_cb)
		item.show()
		self.notebook_popup.append (item)
		self.notebook_popup.attach_to_widget (self.notebook, None)
		self.notebook.connect ("button-press-event", self.notebook_button_press_cb)

		box = gtk.VBox (False, 0)
		box.pack_start (self.menu, expand = False)
		box.pack_start (self.notebook, expand = True)
		self.add (box)

		for i in filenames:
			self.open_file (i)
		if interface != None:
			self.add_child (interface)
		elif len (filenames) == 0:
			self.add_child (Interface (None))
		self.show_all()

		global windows
		windows.append (self)

	## Interface handling
	def get_child (self):
		return self.notebook.get_nth_page (self.notebook.get_current_page())

	def add_child (self, child):
		label = gtk.HBox (False, 0)
		# close button based on GEdit -- make it small
		close_image = gtk.Image()
		close_image.set_from_stock (gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
		close_button = gtk.Button()
		close_button.add (close_image)
		close_button.set_relief (gtk.RELIEF_NONE)
		close_button.set_focus_on_click (False)
		gtk.rc_parse_string (
			"style \"zero-thickness\"\n" +
			"{\n" +
			"	xthickness = 0\n" +
			"	ythickness = 0\n" +
			"}\n" +
			"widget \"*.pagebutton\" style \"zero-thickness\""
		)
		close_button.set_name ("pagebutton")
		if gtk.pygtk_version >= (2,12,0):
			close_button.set_tooltip_text ("Close document")
		close_button.connect ("clicked", self.notebook_page_close_cb, child)
		close_button.connect ("style-set", self.notebook_close_button_style_set_cb)

		label.label = gtk.Label ("")

		label.pack_start (label.label, True)
		label.pack_start (close_button, False)
		label.show_all()

		page_num = self.notebook.append_page (child, label)
		self.notebook.set_current_page (page_num)
		self.load_child_title (child)
		if gtk.pygtk_version >= (2,10,0):
			self.notebook.set_tab_reorderable (child, True)
			self.notebook.set_tab_detachable (child, True)

		child.editor.get_buffer().connect ("modified-changed", self.child_edited_cb, child)

	def close_child (self, child):
		self.notebook.remove_page (self.notebook.page_num (child))

	def open_file (self, filename):  # None for empty
		if filename != None:
			# close page if it is blank
			pages = self.notebook.get_children()
			if len (pages) > 0:
				page = pages [len (pages)-1]
				if page.filename == None and not page.editor.get_buffer().get_modified():
					self.close_child (page)
		self.add_child (Interface (filename))
		self.file_accessed (filename)

	def save_file (self, ask, child = None):
		if child == None:
			child = self.get_child()
		filename = child.filename
		if filename == None:
			ask = True
		if ask:
			global default_dir
			dialog = gtk.FileChooserDialog ("Save File", self, gtk.FILE_CHOOSER_ACTION_SAVE,
			                                buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
			                                           gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT))
			if default_dir != None:
				dialog.set_current_folder (default_dir)
			filter = gtk.FileFilter()
			filter.set_name ("Apoo programs")
			filter.add_pattern ("*.apoo")
			dialog.set_filter (filter)
			dialog.set_default_response (gtk.RESPONSE_ACCEPT)

			ret = dialog.run()
			if ret == gtk.RESPONSE_ACCEPT:
				default_dir = dialog.get_current_folder()
				filename = dialog.get_filename()
				if not filename.endswith (".apoo"):
					filename += ".apoo"
				dialog.destroy()
			else:
				dialog.destroy()
				return False			

		child.file_save (filename)
		self.file_accessed (filename)
		if ask:
			self.load_child_title (child)
		return True

	def file_accessed (self, filename):
		if gtk.pygtk_version >= (2,10,0):
			manager = gtk.recent_manager_get_default()
			data = { 'mime_type': "text/plain", 'app_name': "apoo", 'app_exec': "apoo",
			         'display_name': os.path.basename (filename), 'groups': ['apoo'],
			         'is_private': bool (False), 'description': "Apoo program" }
			uri = filename
			if filename[0] != '/':
				uri = os.path.join (os.getcwd(), filename)
			uri = "file:/" + uri
			manager.add_full (uri, data)

	def load_child_title (self, child):
		if child.filename == None:
			title = "(unnamed)"
		else:
			title = os.path.basename (child.filename)
		if child.editor.get_buffer().get_modified():
			title = "<i>" + title + "</i>"
		label = self.notebook.get_tab_label (child)
		label.label.set_markup (title)

	## Events callbacks
	def notebook_page_added_cb (self, notebook, child, page_num):
		child.main_parent = self
		self.load_menu_sensitive()

	def notebook_page_changed_cb (self, notebook, page_ptr, page_num):
		# either removed or just a switch
		self.load_menu_sensitive()

	def notebook_page_close_cb (self, button, child):
		if self.confirm_child_changes (child):
			self.close_child (child)

	def notebook_close_button_style_set_cb (self, button, prev_style):
		w, h = gtk.icon_size_lookup_for_settings (button.get_settings(), gtk.ICON_SIZE_MENU)
		button.set_size_request (w+2, h+2)

	def notebook_get_page_at (self, x, y):  # utility for press button
		page_num = 0
		while (page_num < self.notebook.get_n_pages()):
			page = self.notebook.get_nth_page (page_num)
			label = self.notebook.get_tab_label (page)
			if label.window.is_visible():
				label_x, label_y = label.window.get_origin()
				alloc = label.get_allocation()
				label_x += alloc.x
				label_y += alloc.y
				if x >= label_x and x <= label_x+alloc.width and y >= label_y and y <= label_y+alloc.height:
					return (page_num, page)
			page_num += 1
		return (-1, None)

	def notebook_button_press_cb (self, notebook, event):
		if event.button == 3 and event.type == gtk.gdk.BUTTON_PRESS:
			page_num, _ = self.notebook_get_page_at (event.x_root, event.y_root)
			if page_num != -1:
				self.notebook.set_current_page (page_num)
				self.notebook_popup.popup (None, None, None, 3, event.time)
		return False

	def notebook_detach_child_cb (self, item):
		child = self.get_child()
		self.close_child (child)
		Window (interface = child)

	def child_edited_cb (self, buffer, child):
		self.load_child_title (child)

	def file_new_cb (self, item):
		self.open_file (None)

	def file_open_cb (self, item):
		dialog = gtk.FileChooserDialog ("Open File", self, gtk.FILE_CHOOSER_ACTION_OPEN,
			buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OPEN, gtk.RESPONSE_ACCEPT))
		global default_dir
		if default_dir != None:
			dialog.set_current_folder (default_dir)
		filter = gtk.FileFilter()
		filter.set_name ("Apoo programs")
		filter.add_pattern ("*.apoo")
		dialog.set_filter (filter)
		dialog.set_select_multiple (True)
		dialog.set_default_response (gtk.RESPONSE_ACCEPT)

		if dialog.run() == gtk.RESPONSE_ACCEPT:
			default_dir = dialog.get_current_folder()
			for i in dialog.get_filenames():
				self.open_file (i)
		dialog.destroy()

	def file_open_recent_cb (self, chooser):
		uri = chooser.get_current_uri()
		if len (uri) > 6 and uri[0:6] == "file:/":
			uri = uri[6:]
		self.open_file (uri)

	def file_save_cb (self, item):
		self.save_file (False)

	def file_save_as_cb (self, item):
		self.save_file (True)

	def file_print_cb (self, item):
		self.get_child().file_print()

	def file_close_cb (self, item):
		child = self.get_child()
		if self.confirm_child_changes (child):
			self.close_child (child)

	def file_quit_cb (self, item):
		if self.confirm_changes():
			self.destroy()

	def edit_undo_cb (self, item):
		self.get_child().edit_undo()
	def edit_redo_cb (self, item):
		self.get_child().edit_redo()

	def edit_cut_cb (self, item):
		self.get_child().edit_cut()
	def edit_copy_cb (self, item):
		self.get_child().edit_copy()
	def edit_paste_cb (self, item):
		self.get_child().edit_paste()

	def edit_kill_line_cb (self, item):
		self.get_child().edit_kill_line()
	def edit_yank_cb (self, item):
		self.get_child().edit_yank()
	def edit_mark_region_cb (self, item):
		self.get_child().edit_mark_region()
	def edit_kill_region_cb (self, item):
		self.get_child().edit_kill_region()
	def edit_copy_region_as_kill_cb (self, item):
		self.get_child().edit_copy_region_as_kill()
	def edit_buffer_home_cb (self, item):
		self.get_child().edit_buffer_home()
	def edit_buffer_end_cb (self, item):
		self.get_child().edit_buffer_end()
	def edit_line_home_cb (self, item):
		self.get_child().edit_line_home()
	def edit_line_end_cb (self, item):
		self.get_child().edit_line_end()
	def edit_delete_right_char_cb (self, item):
		self.get_child().edit_delete_right_char()

	def edit_preferences_cb (self, item):
		preferences_show (self)

	def show_file_text_dialog (self, title, path,filename):
		dialog = gtk.Dialog (title, self,
		                     buttons = (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
		dialog.set_default_response (gtk.RESPONSE_CLOSE)
		dialog.connect ("response", self.close_file_text_dialog_cb)
		dialog.set_default_size (-1, 450)

		buffer = gtk.TextBuffer()
		file = open (path+filename + ".txt", 'r')
		buffer.set_text (file.read())
		file.close()

		view = gtk.TextView (buffer)
		view.set_editable (False)
		view.set_cursor_visible (False)
		set_monospace_font (view)

		window = gtk.ScrolledWindow()
		window.set_policy (gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)
		window.set_shadow_type (gtk.SHADOW_IN)
		window.add (view)

		dialog.vbox.pack_start (window, True)
		dialog.show_all()  # not run() because we don't want it modal

	def close_file_text_dialog_cb (self, dialog, response):
		dialog.destroy()

	def help_interface_cb (self, item):
		if test_mode: doc = DOC_TESTER
		else:         doc = DOC_APOO
		self.show_file_text_dialog ("Help on the Apoo Interface",
					    DOCS_PATH,doc)

	def help_language_cb (self, item):
		self.show_file_text_dialog("Help on the Apoo Assembly Language",
					   DOCS_PATH,DOC_ASSEMBLY)

	def help_about_cb (self, item):
		dialog = gtk.AboutDialog()
		dialog.set_transient_for (self)
		dialog.set_name ("Apoo")
		dialog.set_version (VERSION)
		dialog.set_copyright("Licensed under the GNU General Public License")
		dialog.set_website ("http://www.ncc.up.pt/apoo")
		dialog.set_authors (["Rogerio Reis <rvr@ncc.up.pt>", "Nelma Moreira <nam@ncc.up.pt>",
		                     "(Apoo main developers)", "",
		                     "Ricardo Cruz <rpmcruz@alunos.dcc.fc.up.pt>", "(interface developer)"])
		dialog.run()
		dialog.destroy()

	def run_confirm_dialog (self, nb, content):
		if nb > 1:
			msg = "There are " + str (nb) + " documents unsaved.\n"
		else:
			msg = "Document modified. "
		msg += "Save changes?"
		dialog = gtk.MessageDialog (self, gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT,
			gtk.MESSAGE_QUESTION, gtk.BUTTONS_NONE, msg)
		dialog.add_button ("Don't Save", gtk.RESPONSE_REJECT)
		dialog.add_button (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
		dialog.add_button (gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
		if content != None:
			dialog.vbox.pack_start (content)
			content.show_all()
		ret = dialog.run()
		dialog.destroy()
		return ret

	def confirm_child_changes (self, child):
		if not child.editor.get_buffer().get_modified():
			return True
		response = self.run_confirm_dialog (1, None)
		if response == gtk.RESPONSE_CANCEL:
			return False
		if response == gtk.RESPONSE_ACCEPT:
			return self.save_file (False, child)
		return True
	def confirm_changes (self):
		model = gtk.ListStore (bool, str, int)
		editors = self.notebook.get_children()
		modified = 0
		for i in xrange (len (editors)):
			if editors[i].editor.get_buffer().get_modified():
				iter = model.append()
				name = editors[i].filename
				if name == None:
					name = "(page " + str (self.notebook.page_num (editors[i])+1) + ")"
				model.set (iter, 0, True, 1, name, 2, i)
				modified += 1
		if modified == 0:
			return True

		view = gtk.TreeView (model)
		view.set_headers_visible (False)
		view.get_selection().set_mode (gtk.SELECTION_NONE)
		view.set_search_column (1)

		renderer = gtk.CellRendererToggle()
		renderer.connect ("toggled", self.confirm_filename_toggled_cb, model)
		view.connect ("row-activated", self.confirm_filename_activated_cb, model)
		column = gtk.TreeViewColumn ("", renderer, active = 0)
		view.append_column (column)
		column = gtk.TreeViewColumn ("Filename", gtk.CellRendererText(), text = 1)
		view.append_column (column)

		scroll = gtk.ScrolledWindow()
		scroll.set_policy (gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		scroll.set_shadow_type (gtk.SHADOW_OUT)
		scroll.set_size_request (-1, 80)
		scroll.add (view)

		response = self.run_confirm_dialog (modified, scroll)
		if response == gtk.RESPONSE_ACCEPT:
			iter = model.get_iter_first()
			while iter != None:
				value = model.get_value (iter, 0)
				if value:
					i = model.get_value (iter, 2)
					if not self.save_file (False, editors[i]):
						return False
 				iter = model.iter_next (iter) 
			return True
		return response == gtk.RESPONSE_REJECT
	def confirm_filename_toggle (self, model, iter):
		value = model.get_value (iter, 0)
		model.set (iter, 0, not value)
	def confirm_filename_toggled_cb (self, cell, path_str, model):
		iter = model.get_iter_from_string (path_str)
		self.confirm_filename_toggle (model, iter)
	def confirm_filename_activated_cb (self, view, path, col, model):
		iter = model.get_iter (path)
		self.confirm_filename_toggle (model, iter)

	def ask_close_window_cb (self, window, event):
		if self.confirm_changes():
			return False
		else:
			return True

	def close_window_cb (self, window):
		global windows
		windows.remove (self)
		if len (windows) == 0:
			gtk.main_quit()
		return False

	## Menu builder
	def load_menu_sensitive (self):
		pages_nb = self.notebook.get_n_pages()
		editing = False
		if pages_nb > 0:
			editing = self.get_child().get_editable()

		for i in self.menu_page_items:
			i.set_sensitive (pages_nb > 0)
		for i in self.menu_edit_items:
			i.set_sensitive (editing)

	def load_menu (self):
		# remove any current entries
		for i in self.menu.get_children():
			self.menu.remove (i)
		self.menu_page_items = []
		self.menu_edit_items = []

		file_menu = gtk.Menu()
		item = self.add_menu_item (self.menu, "_File")
		item.set_submenu (file_menu)
		if not test_mode:
			self.add_menu_item (file_menu, "_New", gtk.STOCK_NEW, self.file_new_cb)
			self.add_menu_item (file_menu, "_Open", gtk.STOCK_OPEN, self.file_open_cb)
			if gtk.pygtk_version >= (2,10,0):
				manager = gtk.recent_manager_get_default()
				recents_menu = gtk.RecentChooserMenu (manager)
				recents_menu.set_show_numbers (True)
				recents_menu.set_local_only (True)
				recents_menu.set_sort_type (gtk.RECENT_SORT_MRU)
				recents_menu.set_limit (10)
				filter = gtk.RecentFilter()
				filter.add_pattern ("*.apoo")
				recents_menu.set_filter (filter)
				item = self.add_menu_item (file_menu, "Open _Recent")
				item.set_submenu (recents_menu)
				recents_menu.connect ("item-activated", self.file_open_recent_cb)
			self.add_menu_item (file_menu, "-")
			self.add_menu_item (file_menu, "_Save", gtk.STOCK_SAVE, self.file_save_cb,
				group = self.menu_page_items)
			self.add_menu_item (file_menu, "Save _As", gtk.STOCK_SAVE_AS, self.file_save_as_cb,
				group = self.menu_page_items)
			self.add_menu_item (file_menu, "-")
		if gtk.pygtk_version >= (2,10,0):
			self.add_menu_item (file_menu, "_Print", gtk.STOCK_PRINT, self.file_print_cb,
			                    (gtk.gdk.CONTROL_MASK, ord ('p')),
				group = self.menu_page_items)
			self.add_menu_item (file_menu, "-")
		self.add_menu_item (file_menu, "_Close", gtk.STOCK_CLOSE, self.file_close_cb,
			group = self.menu_page_items)
		self.add_menu_item (file_menu, "_Quit", gtk.STOCK_QUIT, self.file_quit_cb)

		edit_menu = gtk.Menu()
		item = self.add_menu_item (self.menu, "_Edit")
		item.set_submenu (edit_menu)
		if not test_mode:
			self.add_menu_item (edit_menu, "_Undo", gtk.STOCK_UNDO, self.edit_undo_cb,
				(gtk.gdk.CONTROL_MASK, ord ('z')), self.menu_edit_items)
			self.add_menu_item (edit_menu, "_Redo", gtk.STOCK_REDO, self.edit_redo_cb,
				(gtk.gdk.CONTROL_MASK|gtk.gdk.SHIFT_MASK, ord ('z')), self.menu_edit_items)
			self.add_menu_item (edit_menu, "-")

			if shortcuts_style == "emacs":
				self.add_menu_item (edit_menu, "Kill Line", None, self.edit_kill_line_cb,
				                    (gtk.gdk.CONTROL_MASK, ord ('k')), self.menu_edit_items)
				self.add_menu_item (edit_menu, "Yank", None, self.edit_yank_cb,
				                    (gtk.gdk.CONTROL_MASK, ord ('y')), self.menu_edit_items)
				self.add_menu_item (edit_menu, "-")
				self.add_menu_item (edit_menu, "Mark Region", None, self.edit_mark_region_cb,
				                    (gtk.gdk.CONTROL_MASK, ord (' ')), self.menu_edit_items)
				# GTK+ doesn't support an accelerator like Esc+W
				self.add_menu_item (edit_menu, "Copy Region as Kill", None,
				                    self.edit_copy_region_as_kill_cb,
				                    (gtk.gdk.CONTROL_MASK, 65307), self.menu_edit_items)
				self.add_menu_item (edit_menu, "Kill Region", None, self.edit_kill_region_cb,
				                    (gtk.gdk.CONTROL_MASK, ord ('w')), self.menu_edit_items)
				self.add_menu_item (edit_menu, "-")
				self.add_menu_item (edit_menu, "Line Home", None, self.edit_line_home_cb,
				                    (gtk.gdk.CONTROL_MASK, ord ('a')), self.menu_edit_items)
				self.add_menu_item (edit_menu, "Line End", None, self.edit_line_end_cb,
				                    (gtk.gdk.CONTROL_MASK, ord ('e')), self.menu_edit_items)
				self.add_menu_item (edit_menu, "-")
				self.add_menu_item (edit_menu, "Delete Right Character", None,
				                    self.edit_delete_right_char_cb,
				                    (gtk.gdk.CONTROL_MASK, ord ('d')), self.menu_edit_items)
			else:  # "desktop"
				self.add_menu_item (edit_menu, "Cu_t", gtk.STOCK_CUT, self.edit_cut_cb,
					group = self.menu_edit_items)
				self.add_menu_item (edit_menu, "_Copy", gtk.STOCK_COPY, self.edit_copy_cb,
					group = self.menu_page_items)
				self.add_menu_item (edit_menu, "_Paste", gtk.STOCK_PASTE, self.edit_paste_cb,
					group = self.menu_edit_items)
			self.add_menu_item (edit_menu, "-")
		self.add_menu_item (edit_menu, "_Preferences...", gtk.STOCK_PREFERENCES,
		                    self.edit_preferences_cb)

		help_menu = gtk.Menu()
		item = self.add_menu_item (self.menu, "_Help")
		item.set_submenu (help_menu)
		self.add_menu_item (help_menu, "_Interface Help", gtk.STOCK_HELP,
		                    self.help_interface_cb, (0, 0xFFBE)) # F1
		self.add_menu_item (help_menu, "_Assembly Help", gtk.STOCK_HELP,
		                    self.help_language_cb, (0, 0xFFBF)) # F2
		self.add_menu_item (help_menu, "_About", gtk.STOCK_ABOUT, self.help_about_cb)
		self.menu.show_all()

	# convience methods to create the menu to cut down on code
	def add_menu_item (self, parent, label, image = None, callback = None,
	                   shortcut = None, group = None):  # shortcut = (modified, key)
		if label == '-':
			item = gtk.SeparatorMenuItem()
		else:
			# we'll create the item widget ourselves since pygtk isn't very nice here
			box = gtk.HBox (False, 6)
			glabel = gtk.AccelLabel (label)
			glabel.set_use_underline (True)
			glabel.set_alignment (0, 0.5)
			if image:
				gimage = gtk.Image()
				gimage.set_from_stock (image, gtk.ICON_SIZE_MENU)
				box.pack_start (gimage, False)
			box.pack_start (glabel, True)

			item = gtk.MenuItem()
			item.add (box)
			glabel.set_accel_widget (item)

			if shortcut == None and image != None:
				# set stock image assigned key
				info = gtk.stock_lookup (image)
				shortcut = (info[2], info[3])
				# some stock icons have bad shortcuts, so do a check...
				if shortcut[1] <= 0:
					shortcut = None
			if shortcut != None:
				key = shortcut[1]
				modifier = shortcut[0]
				item.add_accelerator ("activate", self.accel_group, key,
				                      modifier, gtk.ACCEL_VISIBLE)
			if callback != None:
				item.connect ("activate", callback)

		parent.append (item)
		item.show_all()
		if group != None:
			group.append (item)
		return item

if __name__ == "__main__":
	# parse arguments at first
	filenames = []
	argv = sys.argv
	for i in xrange (1, len (argv)):
		if argv[i] == "--tester" or argv[i] == "-t":
			test_mode = True

		elif argv[i] == "--help" or argv[i] == "-h":
			print "Usage: " + argv[0] + " [OPTIONS] [FILENAME]"
			print "Options may be:"
			print "\t--tester, -t\tExecute-only mode"
			print "\t--help, -h\tShow this help text"
			print ""
			sys.exit (0)

		elif argv[i][0] == '-':
			print "Unrecognized argument: " + argv[i]
			print "For usage: " + argv[0] + " --help"
			sys.exit (1)
		else:
			filenames.append (argv[i])

	if test_mode and len (filenames) == 0:
		print "Usage: " + argv[0] + " --tester filename"
		sys.exit (1)

	# go on, now
	read_config()

	Window (filenames)
	gtk.main()

	write_config()

