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
import shlex

from gi.repository import GObject, Gio, Gedit, Peas, PeasGtk

from .widgets import *
from .settings import Settings

try:
    import gettext
    gettext.bindtextdomain('gedit-plugins')
    gettext.textdomain('gedit-plugins')
    _ = gettext.gettext
except:
    _ = lambda s: s


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

    def do_create_configure_widget(self):
        return Settings.create_configure_widget()


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
        self._panel.show()

        bottom = self.window.get_bottom_panel()
        bottom.add_titled(self._panel, "GeditTerminalEnhancedPanel", _("Terminal"))
        bottom.set_visible_child(self._panel)

        self.bus = self.window.get_message_bus()

        self.register_messages()
        self.install_filebrowser_extension()

    def do_deactivate(self):
        self.window.remove_action("focus-on-terminal")

        bottom = self.window.get_bottom_panel()
        bottom.remove(self._panel)

        self.unregiser_messages()
        self.uninstall_filebrowser_extension()

    def do_update_state(self):
        pass

    def register_messages(self):
        self.bus.register(self.FeedString, '/plugins/terminalenhanced', 'feed-string')

        self.signal_ids = []
        self.signal_ids.append(self.bus.connect('/plugins/terminalenhanced', 'feed-string', self.on_feed_string_message, None))

    def unregister_messages(self):
        for sid in self.signal_ids:
            self.bus.disconnect(sid)

        self.bus.unregister_all('/plugins/terminalenhanced')

    def on_feed_string_message(self, bus, message, user_data):
        self.focus_terminal()
        self._panel.feed_string(message.props.str)

    def install_filebrowser_extension(self):
        self.fb_menu_extension = None

        if self.bus.is_registered('/plugins/filebrowser', 'extend_context_menu'):
            msg = self.bus.send_sync('/plugins/filebrowser', 'extend_context_menu')
            self.fb_menu_extension = msg.props.extension

            action = Gio.SimpleAction(name='fb-paste-to-terminal')
            action.connect("activate", self.on_fb_paste_to_terminal)
            self.window.add_action(action)

            item = Gio.MenuItem.new(_("Paste name into the terminal"), 'win.fb-paste-to-terminal')
            self.fb_menu_extension.append_menu_item(item)

            action = Gio.SimpleAction(name='fb-change-terminal-dir')
            action.connect("activate", self.on_fb_change_terminal_dir)
            self.window.add_action(action)

            item = Gio.MenuItem.new(_("Change terminal directory to this"), 'win.fb-change-terminal-dir')
            self.fb_menu_extension.append_menu_item(item)

    def uninstall_filebrowser_extension(self):
        if self.fb_menu_extension:
            self.window.remove_action('win.fb-paste-to-terminal')
            self.window.remove_action('win.fb-change-terminal-dir')

            self.fb_menu_extension = None

    def get_fb_selected_paths(self):
        try:
            view = self.bus.send_sync('/plugins/filebrowser', 'get_view').props.view
        except TypeError:
            return []

        model, rows = view.get_selection().get_selected_rows()
        paths = []

        for row in rows:
            gfile = model.get_value(model.get_iter(row), 3)
            paths.append(gfile.get_path())

        if not paths:
            msg = self.bus.send_sync('/plugins/filebrowser', 'get_root')
            paths.append(msg.props.location.get_path())

        return paths

    def on_fb_paste_to_terminal(self, action, param):
        paths = self.get_fb_selected_paths()

        self._panel.feed_string(' '.join([shlex.quote(p) for p in paths]))

    def on_fb_change_terminal_dir(self, action, param):
        paths = self.get_fb_selected_paths()
        if paths:
            path = paths[0]
            if not os.path.isdir(path):
                path = os.path.dirname(path)

            self._panel.feed_string('cd '+shlex.quote(path)+'\n')

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

    def open_file(self, filename, line):
        if os.path.exists(filename):
            gio_file = Gio.File.new_for_path(filename)
            Gedit.commands_load_location(self.window, gio_file, None, line, -1)


# Let's conform to PEP8
# ex:ts=4:et:
