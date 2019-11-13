import os
import subprocess

from gi.repository import Gio, Gtk

SCHEMAS_PATH = os.path.join(os.path.dirname(__file__), 'schemas')
PLUGIN_SCHEMA_ID = 'pl.zb3.gedit.terminal-enhanced'

class Settings:
    schema_source = None

    @classmethod
    def get(cls, local_id=''):
        schema_id = PLUGIN_SCHEMA_ID + ('.' + local_id if local_id else '')

        if cls.schema_source is None:
            cls.schema_source = Gio.SettingsSchemaSource.new_from_directory(SCHEMAS_PATH,
                                        Gio.SettingsSchemaSource.get_default(), False)
            if not cls.schema_source:
                raise Exception('no schema source')

        schema = cls.schema_source.lookup(schema_id, False)
        return Gio.Settings.new_full(schema, None, None)

    @staticmethod
    def invoke_dconf_editor(local_path=''):
        env = os.environ.copy()
        env['GSETTINGS_SCHEMA_DIR'] = SCHEMAS_PATH
        subprocess.Popen(['dconf-editor', '/pl/zb3/gedit/terminal-enhanced/'+local_path], env=env)

    @classmethod
    def create_configure_widget(cls):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(20)

        button = Gtk.Button.new_with_label("Edit profile settings using dconf-editor")
        button.connect('clicked', lambda x: cls.invoke_dconf_editor('profile'))
        box.pack_start(button, True, False, 0)

        return box


