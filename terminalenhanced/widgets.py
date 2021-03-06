import os
import re

from gi.repository import GObject, GLib, Gio, Pango, Gdk, Gtk, Gedit, Vte
from .settings import Settings

from .workarounds import vte_terminal_event_check_regex_simple

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
            settings = Settings.get("profile")

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
            # event_check_regex_simple can't currently be called via pygobject, so we use a workaround
            has_match, matches = vte_terminal_event_check_regex_simple(self, event, [self.CLICK_VREGEX], 0)

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
        self.plugin.open_file(filename, line)

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


