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
import subprocess

import time

import gi
gi.require_version('Gedit', '3.0')
gi.require_version('Peas', '1.0')
gi.require_version('PeasGtk', '1.0')
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import GObject, GLib, Gio, Pango, Gdk, Gtk, Gedit, Vte, Peas, PeasGtk

try:
    import gettext
    gettext.bindtextdomain('gedit-plugins')
    gettext.textdomain('gedit-plugins')
    _ = gettext.gettext
except:
    _ = lambda s: s

SCHEMAS_PATH = os.path.join(os.path.dirname(__file__), 'schemas')

schema_source = None

def get_gio_settings(schema_id):
    global schema_source

    if schema_source is None:
        schema_source = Gio.SettingsSchemaSource.new_from_directory(SCHEMAS_PATH, Gio.SettingsSchemaSource.get_default(), False)

        if not schema_source:
            raise Exception('no schema source')

    schema = schema_source.lookup(schema_id, False)
    return Gio.Settings.new_full(schema, None, None)


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
            settings = get_gio_settings("pl.zb3.gedit.terminal-enhanced.profile")

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


class GeditTerminalEnhancedPanel(Gtk.Box):
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

        self.add_terminal()
        self.create_action_group()
        self.create_popup_menu()


    def add_terminal(self):
        self._vte = GeditTerminal()
        self._vte.show()
        self.pack_start(self._vte, True, True, 0)

        self._vte.connect("child-exited", self.on_vte_child_exited)
        self._vte.connect("key-press-event", self.on_vte_key_press)
        self._vte.connect("button-press-event", self.on_vte_button_press)
        self._vte.connect("popup-menu", self.on_vte_popup_menu)
        self._vte.connect("file-clicked", self.on_vte_file_clicked)
        self._vte.connect("focus-in-event", self.on_vte_focus)

        scrollbar = Gtk.Scrollbar.new(Gtk.Orientation.VERTICAL, self._vte.get_vadjustment())
        scrollbar.show()
        self.pack_start(scrollbar, False, False, 0)

    def create_action_group(self):
        self.action_group = Gio.SimpleActionGroup()
        self.actions = {}

        actions = (
            ('change-directory', self.change_to_current_directory),
            ('copy-clipboard', self.copy_clipboard),
            ('paste-clipboard', self.paste_clipboard),
            ('paste-current-file', self.paste_current_file),
        )

        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)

            self.actions[name] = action
            self.action_group.add_action(action)


    def create_popup_menu(self):
        model = Gio.Menu()
        section = Gio.Menu()
        section.append(_("C_hange Directory"), "term.change-directory")
        model.append_section(None, section)

        section = Gio.Menu()
        section.append(_("_Copy"), "term.copy-clipboard")
        section.append(_("_Paste"), "term.paste-clipboard")
        model.append_section(None, section)

        section = Gio.Menu()
        section.append(_("Paste current f_ile"), "term.paste-current-file")
        model.append_section(None, section)

        self.menu = Gtk.Menu.new_from_model(model)
        self.menu.attach_to_widget(self, None)
        self.menu.insert_action_group('term', self.action_group)


    def update_action_state(self, enable_all=False):
        # we only update the state when we need it. so before showing a popup, we want to enable
        # only usable actions, but then all keys should work without us listening for state changes

        if enable_all:
            for action in self.actions:
                self.actions[action].set_enabled(True)
        else:
            directory = self.plugin.get_active_document_directory()
            path = self.plugin.get_active_document_path()

            self.actions['change-directory'].set_enabled(directory is not None)
            self.actions['copy-clipboard'].set_enabled(self._vte.get_has_selection())
            self.actions['paste-current-file'].set_enabled(path is not None)

    def show_popup(self, event = None):
        self.update_action_state()

        if event is not None:
            self.menu.popup(None, None, None, None, event.button, event.time)
        else:
            self.menu.popup(None, None,
                       lambda m: Gedit.utils_menu_position_under_widget(m, self),
                       None,
                       0, Gtk.get_current_event_time())
            self.menu.select_first(False)

    def feed_string(self, string):
        self._vte.feed_child(string.encode('utf-8'))
        self._vte.grab_focus()

    def feed_path(self, path):
        self.feed_string("'" + path + "'")

    def change_directory(self, path):
        path = path.replace('\\', '\\\\').replace('"', '\\"')
        self.feed_string('cd "%s"\n' % path)

    def do_grab_focus(self):
        self._vte.grab_focus()

    def on_vte_key_press(self, term, event):
        # gedit overrides the default GtkWindow event handling mechanism, so we get events
        # before accelerators which 'd normally not be the case

        # the goal of this function is to handle our accelerators and partially reverse this process
        # so that VTE doesn't consume everything.

        # special case TAB / backspace keys
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        if event.keyval in (Gdk.KEY_Tab, Gdk.KEY_KP_Tab, Gdk.KEY_ISO_Left_Tab):
            if modifiers == Gdk.ModifierType.CONTROL_MASK:
                self.get_toplevel().child_focus(Gtk.DirectionType.TAB_FORWARD)
                return True
            elif modifiers == Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK:
                self.get_toplevel().child_focus(Gtk.DirectionType.TAB_BACKWARD)
                return True
        elif event.keyval == Gdk.KEY_BackSpace and modifiers == Gdk.ModifierType.CONTROL_MASK:
            # feed ^W which corresponds to 0x17
            self.feed_string(chr(0x17))
            return True

        # Special case some Vte.Terminal shortcuts
        # so the global shortcuts do not override them
        if event.keyval == Gdk.KEY_Delete:
            return False

        if modifiers & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            keyval_name = Gdk.keyval_name(Gdk.keyval_to_upper(event.keyval))

            if modifiers == Gdk.ModifierType.CONTROL_MASK and keyval_name in 'ACDEHKLRTUWZ':
                return False

            if modifiers == Gdk.ModifierType.MOD1_MASK and keyval_name in 'BF':
                return False

            # very ugly hack: handle our accelerators manually
            # it must be done, because it's not that actions in our namespace are checked
            # first, so other plugins' accelerators override our terminal-local ones

            accel = Gtk.accelerator_name(event.keyval, modifiers)
            actions = self.get_toplevel().get_application().get_actions_for_accel(accel)

            for action in actions:
                if action.startswith('term.'):
                    self.actions[action[len('term.'):]].activate()
                    return True

        # now we'll give other accelerators a chance, to reverse gedit's behaviour
        return self.get_toplevel().activate_key(event)

    def on_vte_child_exited(self, term, status):
        for child in self.get_children():
            child.destroy()

        self.add_terminal()
        self._vte.grab_focus()

    def on_vte_focus(self, term, arg):
        # re-enable all keys, we could also do this on keypress
        self.update_action_state(True)

    def on_vte_popup_menu(self, term):
        self.show_popup()

    def on_vte_file_clicked(self, term, filename, line):
        self.emit('file-clicked', filename, line)

    def on_vte_button_press(self, term, event):
        if event.button == 3:
            self._vte.grab_focus()
            self.show_popup(event)
            return True

        return False

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



class TerminalAppActivatable(GObject.Object, Gedit.AppActivatable, PeasGtk.Configurable):
    app = GObject.Property(type=Gedit.App)

    __instance = None

    def __init__(self):
        super().__init__()

        self.accelerators = (
            ('<Primary><Shift>D', 'term.change-directory'),
            ('<Primary><Shift>C', 'term.copy-clipboard'),
            ('<Primary><Shift>V', 'term.paste-clipboard'),
            ('<Primary><Shift>F', 'term.paste-current-file'),
            ('<Primary><Alt>T', 'win.focus-on-terminal')
        )

    def do_activate(self):
        for accel, action in self.accelerators:
            self.app.set_accels_for_action(action, (accel,))


    def deactivate(self):
        for accel, action in self.accelerators:
            self.app.set_accels_for_action(action, [])

    def invoke_dconf_editor(self):
        env = os.environ.copy()
        env['GSETTINGS_SCHEMA_DIR'] = SCHEMAS_PATH
        subprocess.Popen(['dconf-editor', '/pl/zb3/gedit/terminal-enhanced/profile'], env=env)

    def do_create_configure_widget(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(20)

        button = Gtk.Button.new_with_label("Edit profile settings using dconf-editor")
        button.connect('clicked', lambda x: self.invoke_dconf_editor())
        box.pack_start(button, True, False, 0)

        return box


class TerminalEnhancedPlugin(GObject.Object, Gedit.WindowActivatable):
    __gtype_name__ = "TerminalEnhancedPlugin"

    window = GObject.Property(type=Gedit.Window)

    class FeedString(Gedit.Message):
        str = GObject.Property(type=str)

    def __init__(self):
        GObject.Object.__init__(self)

    def do_activate(self):
        action = Gio.SimpleAction(name="focus-on-terminal")
        action.connect('activate', lambda a, p: self.focus_terminal())
        self.window.add_action(action)

        self._panel = GeditTerminalEnhancedPanel(self)
        self._panel.connect("file-clicked", self.on_vte_file_clicked)
        self._panel.show()

        bottom = self.window.get_bottom_panel()
        bottom.add_titled(self._panel, "GeditTerminalEnhancedPanel", _("Terminal"))
        bottom.set_visible_child(self._panel)

        bus = self.window.get_message_bus()
        bus.register(self.FeedString, '/plugins/terminalenhanced', 'feed-string')

        self.signal_ids = []
        self.signal_ids.append(bus.connect('/plugins/terminalenhanced', 'feed-string', self.on_feed_string_message, None))

    def do_deactivate(self):
        self.window.remove_action("focus-on-terminal")

        bottom = self.window.get_bottom_panel()
        bottom.remove(self._panel)

        bus = self.window.get_message_bus()
        for sid in self.signal_ids:
            bus.disconnect(sid)

        bus.unregister_all('/plugins/terminalenhanced')

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

    def focus_terminal(self):
        self.window.get_bottom_panel().set_visible_child_name("GeditTerminalEnhancedPanel")
        self._panel.grab_focus()

    def on_feed_string_message(self, bus, message, user_data):
        self.focus_terminal()
        self._panel.feed_string(message.props.str)

    def on_vte_file_clicked(self, term, filename, line):
        if os.path.exists(filename):
            gio_file = Gio.File.new_for_path(filename)
            Gedit.commands_load_location(self.window, gio_file, None, line, -1)

# Let's conform to PEP8
# ex:ts=4:et:
