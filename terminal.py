# -*- coding: utf8 -*-

# terminal.py - Embeded VTE terminal for gedit
# This file is part of gedit
#
# Copyright (C) 2005-2006 - Paolo Borelli
#
# gedit is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# gedit is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with gedit; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor,
# Boston, MA  02110-1301  USA

import os
import re

import time

import gi
gi.require_version('Gedit', '3.0')
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import GObject, GLib, Gio, Pango, Gdk, Gtk, Gedit, Vte

try:
    import gettext
    gettext.bindtextdomain('gedit-plugins')
    gettext.textdomain('gedit-plugins')
    _ = gettext.gettext
except:
    _ = lambda s: s

class GeditTerminal(Vte.Terminal):

    defaults = {
        'audible_bell'          : False,
    }

    TARGET_URI_LIST = 200
    XTRA_SCROLL_LINES = 2
    
    VTE_REGEX_FLAGS =  0x400

    #HIGHLIGHT_REGEX_STR = r'''([^:(),"'\s]*?[/.][^:(),"'\s]*)(:\d+)?:?'''
    HIGHLIGHT_REGEX_STR = r'''^([^:(),"'\s]*?[/.][^:(),"'\s]*)(:\d+)?:?'''
    CLICK_REGEX_STR = r'''([^:(),"'\s]+)(?::(\d+))?:?'''

    HIGHLIGHT_VREGEX = Vte.Regex.new_for_match(HIGHLIGHT_REGEX_STR, len(HIGHLIGHT_REGEX_STR), VTE_REGEX_FLAGS)
    CLICK_VREGEX = Vte.Regex.new_for_match(CLICK_REGEX_STR, len(CLICK_REGEX_STR), VTE_REGEX_FLAGS)
    CLICK_PATTERN = re.compile(CLICK_REGEX_STR)
    
    __gsignals__ = {
        "file-clicked": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (GObject.TYPE_STRING,GObject.TYPE_INT,)
        )
    }

    def __init__(self):
        Vte.Terminal.__init__(self)

        self.set_size(self.get_column_count(), 7)
        self.set_size_request(200, 130)

        tl = Gtk.TargetList.new([])
        tl.add_uri_targets(self.TARGET_URI_LIST)

        self.drag_dest_set(Gtk.DestDefaults.HIGHLIGHT | Gtk.DestDefaults.DROP,
                           [], Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self.drag_dest_set_target_list(tl)

        self.profile_settings = self.get_profile_settings()
        self.profile_settings.connect("changed", self.on_profile_settings_changed)
        self.system_settings = Gio.Settings.new("org.gnome.desktop.interface")
        self.system_settings.connect("changed::monospace-font-name", self.font_changed)

        self.reconfigure_vte()

        result, pid = self.spawn_sync(Vte.PtyFlags.DEFAULT, None, [Vte.get_user_shell()], None, GLib.SpawnFlags.SEARCH_PATH, None, None, None)
        self.child_pid = pid
        self.match_add_regex(self.HIGHLIGHT_VREGEX, 0)
        self.connect("button-press-event", self.on_button_press)
        self.connect('text-scrolled', self.on_text_scroll)
        

    def do_drag_data_received(self, drag_context, x, y, data, info, time):
        if info == self.TARGET_URI_LIST:
            self.feed_child(' '.join(["'" + Gio.file_new_for_uri(item).get_path() + "'" for item in Gedit.utils_drop_get_uris(data)]).encode('utf-8'))
            Gtk.drag_finish(drag_context, True, False, time);
        else:
            Vte.Terminal.do_drag_data_received(self, drag_context, x, y, data, info, time)

    def settings_try_new(self, schema):
        schemas = Gio.Settings.list_schemas()
        if not schemas:
            return None

        for s in schemas:
            if s == schema:
                return Gio.Settings.new(schema)

        return None

    def get_profile_settings(self):
        profiles = self.settings_try_new("org.gnome.Terminal.ProfilesList")

        if profiles:
            default_path = "/org/gnome/terminal/legacy/profiles:/:" + profiles.get_string("default") + "/"
            settings = Gio.Settings.new_with_path("org.gnome.Terminal.Legacy.Profile",
                                                  default_path)
        else:
            settings = Gio.Settings.new("org.gnome.gedit.plugins.terminal")

        return settings

    def get_font(self):
        if self.profile_settings.get_boolean("use-system-font"):
            font = self.system_settings.get_string("monospace-font-name")
        else:
            font = self.profile_settings.get_string("font")

        return font

    def font_changed(self, settings=None, key=None):
        font = self.get_font()
        font_desc = Pango.font_description_from_string(font)

        self.set_font(font_desc)

    def reconfigure_vte(self):
        # Fonts
        self.font_changed()

        # colors
        context = self.get_style_context()
        fg = context.get_color(Gtk.StateFlags.NORMAL)
        bg = context.get_background_color(Gtk.StateFlags.NORMAL)
        palette = []

        if not self.profile_settings.get_boolean("use-theme-colors"):
            fg_color = self.profile_settings.get_string("foreground-color")
            if fg_color != "":
                fg = Gdk.RGBA()
                parsed = fg.parse(fg_color)
            bg_color = self.profile_settings.get_string("background-color")
            if bg_color != "":
                bg = Gdk.RGBA()
                parsed = bg.parse(bg_color)
        str_colors = self.profile_settings.get_strv("palette")
        if str_colors:
            for str_color in str_colors:
                try:
                    rgba = Gdk.RGBA()
                    rgba.parse(str_color)
                    palette.append(rgba)
                except:
                    palette = []
                    break

        self.set_colors(fg, bg, palette)
        self.set_cursor_blink_mode(self.profile_settings.get_enum("cursor-blink-mode"))
        self.set_cursor_shape(self.profile_settings.get_enum("cursor-shape"))
        self.set_audible_bell(self.profile_settings.get_boolean("audible-bell"))
        self.set_allow_bold(self.profile_settings.get_boolean("allow-bold"))
        self.set_scroll_on_keystroke(self.profile_settings.get_boolean("scroll-on-keystroke"))
        self.set_scroll_on_output(self.profile_settings.get_boolean("scroll-on-output"))
        self.set_audible_bell(self.defaults['audible_bell'])

        if self.profile_settings.get_boolean("scrollback-unlimited"):
            lines = -1
        else:
            lines = self.profile_settings.get_int("scrollback-lines")
        self.set_scrollback_lines(lines)

    def on_profile_settings_changed(self, settings, key):
        self.reconfigure_vte()
        
    def get_cwd(self):
        return os.readlink('/proc/%s/cwd' % self.child_pid)
        
    def on_button_press(self, term, event):
        if event.button == 1 and (event.state & Gdk.ModifierType.CONTROL_MASK):
            has_match, matches = self.event_check_regex_simple(event, [self.CLICK_VREGEX], 0)
          
            if has_match:
                match = self.CLICK_PATTERN.match(matches[0])
                
                filename = os.path.join(self.get_cwd(), match.group(1))
                line = int(match.group(2) or 0)
                
                self.emit("file-clicked", filename, line)
                return True
            
        return False
        
    def on_text_scroll(self, term, delta):
      if delta in (-1, 1):
         vadj = self.get_vadjustment()
         vadj.set_value(vadj.get_value() + delta*self.XTRA_SCROLL_LINES*vadj.get_step_increment())
        

class GeditTerminalPanel(Gtk.Box):
    """VTE terminal which follows gnome-terminal default profile options"""

    __gsignals__ = {
        "file-clicked": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (GObject.TYPE_STRING,GObject.TYPE_INT,)
        )
    }

    def __init__(self, plugin):
        Gtk.Box.__init__(self)
        
        self.plugin = plugin

        self._accel_base = '<gedit>/plugins/terminal'
        self._accels = {
            'change-directory': [Gdk.KEY_D, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK],
            'copy-clipboard': [Gdk.KEY_C, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK],
            'paste-clipboard': [Gdk.KEY_V, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK],
            'paste-current-file': [Gdk.KEY_F, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK]
        }
        self._accel_group = Gtk.AccelGroup.new()
            
        for name in self._accels:
            path = self._accel_base + '/' + name
            accel = Gtk.AccelMap.lookup_entry(path)

            if not accel[0]:
                 Gtk.AccelMap.add_entry(path, self._accels[name][0], self._accels[name][1])           
            
        self.create_popup_menu()
        self.add_terminal()

    def add_terminal(self):
        self._vte = GeditTerminal()
        self._vte.show()
        self.pack_start(self._vte, True, True, 0)

        self._vte.connect("child-exited", self.on_vte_child_exited)
        self._vte.connect("key-press-event", self.on_vte_key_press)
        self._vte.connect("button-press-event", self.on_vte_button_press)
        self._vte.connect("popup-menu", self.on_vte_popup_menu)
        self._vte.connect("file-clicked", self.on_vte_file_clicked)
        
        scrollbar = Gtk.Scrollbar.new(Gtk.Orientation.VERTICAL, self._vte.get_vadjustment())
        scrollbar.show()
        self.pack_start(scrollbar, False, False, 0)

    def on_vte_child_exited(self, term, status):
        for child in self.get_children():
            child.destroy()

        self.add_terminal()
        self._vte.grab_focus()

    def do_grab_focus(self):
        self._vte.grab_focus()

    def on_vte_key_press(self, term, event):
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        if event.keyval in (Gdk.KEY_Tab, Gdk.KEY_KP_Tab, Gdk.KEY_ISO_Left_Tab):
            if modifiers == Gdk.ModifierType.CONTROL_MASK:
                self.get_toplevel().child_focus(Gtk.DirectionType.TAB_FORWARD)
                return True
            elif modifiers == Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK:
                self.get_toplevel().child_focus(Gtk.DirectionType.TAB_BACKWARD)
                return True

        accel_quark = GLib.quark_from_string(Gtk.accelerator_name(event.keyval, modifiers))
        if self._accel_group.activate(accel_quark, self, event.keyval, modifiers):
            return True
         
        if modifiers & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            keyval_name = Gdk.keyval_name(Gdk.keyval_to_upper(event.keyval))

            # Special case some Vte.Terminal shortcuts
            # so the global shortcuts do not override them
            if modifiers == Gdk.ModifierType.CONTROL_MASK and keyval_name in 'ACDEHKLRTUWZ':
                return False

            if modifiers == Gdk.ModifierType.MOD1_MASK and keyval_name in 'BF':
                return False

        return Gtk.accel_groups_activate(self.get_toplevel(),
                                         event.keyval, modifiers)

    def on_vte_button_press(self, term, event):
        if event.button == 3:
            self._vte.grab_focus()
            self.show_popup(event)
            return True

        return False

    def create_popup_menu(self):
        self.menu = Gtk.Menu()
        self.menu_items = {}
        
        self.menu.set_accel_group(self._accel_group)
        
        item = Gtk.MenuItem.new_with_mnemonic(_("C_hange Directory"))
        item.connect("activate", self.change_to_current_directory)
        item.set_accel_path(self._accel_base + '/change-directory')
        self.menu_items['change-directory'] = item
        self.menu.append(item)

        self.menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_COPY, None)
        item.connect("activate", self.copy_clipboard)
        item.set_accel_path(self._accel_base + '/copy-clipboard')      
        self.menu_items['copy-clipboard'] = item
        self.menu.append(item)

        item = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_PASTE, None)
        item.connect("activate", self.paste_clipboard)
        item.set_accel_path(self._accel_base + '/paste-clipboard')
        self.menu.append(item)        

        self.menu.append(Gtk.SeparatorMenuItem())
        
        item = Gtk.MenuItem.new_with_mnemonic(_("Paste current f_ile"))
        item.connect("activate", self.paste_current_file)
        item.set_accel_path(self._accel_base + '/paste-current-file')
        self.menu_items['paste-current-file'] = item
        self.menu.append(item)
        
        self.menu.show_all()
        self.menu.attach_to_widget(self, None)
        
    def update_popup_menu(self):
        directory = self.plugin.get_active_document_directory()
        path = self.plugin.get_active_document_path()
        
        self.menu_items['change-directory'].set_sensitive(directory is not None)
        self.menu_items['copy-clipboard'].set_sensitive(self._vte.get_has_selection())
        self.menu_items['paste-current-file'].set_sensitive(path is not None)

    def on_vte_popup_menu(self, term):
        self.show_popup()

    def show_popup(self, event = None):
        self.update_popup_menu()
        
        if event is not None:
            self.menu.popup(None, None, None, None, event.button, event.time)
        else:
            self.menu.popup(None, None,
                       lambda m: Gedit.utils_menu_position_under_widget(m, self),
                       None,
                       0, Gtk.get_current_event_time())
            self.menu.select_first(False)

    def feed_path(self, path):
        self._vte.feed_child(("'" + path + "'").encode('utf-8'))
        self._vte.grab_focus()

    def change_directory(self, path):
        path = path.replace('\\', '\\\\').replace('"', '\\"')
        self._vte.feed_child(('cd "%s"\n' % path).encode('utf-8'))
        self._vte.grab_focus()
        
    def on_vte_file_clicked(self, term, filename, line):
        self.emit('file-clicked', filename, line)
        
    # methods below are called by accelerators, they need to handle *args and return True
        
    def copy_clipboard(self, *args):
        self._vte.copy_clipboard()
        self._vte.grab_focus()
        return True

    def paste_clipboard(self, *args):
        self._vte.paste_clipboard()
        self._vte.grab_focus()
        return True
        
    def change_to_current_directory(self, *args):
        directory = self.plugin.get_active_document_directory()
        if directory:
            self.change_directory(directory)
        return True
            
    def paste_current_file(self, *args):
        path = self.plugin.get_active_document_path()
        if path:
            self.feed_path(path)
        return True
    
  
class TerminalAppActivatable(GObject.Object, Gedit.AppActivatable):
    app = GObject.Property(type=Gedit.App)

    def __init__(self):
        super().__init__()

    def do_activate(self):
        # deprecated?
        self.app.add_accelerator("<Primary><Alt>T", "win.focus-on-terminal", None)

    def deactivate(self):
        # deprecated?
        self.app.remove_accelerator("win.focus-on-terminal", None)


class TerminalPlugin(GObject.Object, Gedit.WindowActivatable):
    __gtype_name__ = "TerminalPlugin"

    window = GObject.Property(type=Gedit.Window)

    def __init__(self):
        GObject.Object.__init__(self)
   
    def do_activate(self):
        self._panel = GeditTerminalPanel(self)
        self._panel.connect("file-clicked", self.on_vte_file_clicked)
        self._panel.show()

        bottom = self.window.get_bottom_panel()
        bottom.add_titled(self._panel, "GeditTerminalPanel", _("Terminal"))
        
        action = Gio.SimpleAction(name="focus-on-terminal")
        action.connect('activate', self.on_focus)
        self.window.add_action(action)

    def do_deactivate(self):
        bottom = self.window.get_bottom_panel()
        bottom.remove(self._panel)
        self.window.remove_action("focus-on-terminal")

    def do_update_state(self):
        pass

    def get_active_document_path(self):
        doc = self.window.get_active_document()
        if doc:
            location = doc.get_file().get_location()
            if location and location.has_uri_scheme("file"):
                return location.get_path()
        return None
        
    def get_active_document_directory(self):
        doc = self.get_active_document_path()
        if doc:
            return os.path.dirname(doc)
        return None
        
    def on_focus(self, action, parameter, user_data=None):
        self.window.get_bottom_panel().set_visible_child_name("GeditTerminalPanel")
        self._panel.grab_focus()

    def on_vte_file_clicked(self, term, filename, line):
        if os.path.exists(filename):
            gio_file = Gio.File.new_for_path(filename)
            Gedit.commands_load_location(self.window, gio_file, None, line, -1)

# Let's conform to PEP8
# ex:ts=4:et:
