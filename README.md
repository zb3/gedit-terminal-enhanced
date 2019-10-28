# gedit-terminal-enhanced

Slightly modified version of the original terminal plugin. Modifications include:
* <kbd>Ctrl</kbd> + <kbd>Click</kbd> to open grep results and other files (separated by space/colon, line numbers supported)
* <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>F</kbd> to paste currently edited file
* <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>D</kbd> to change current directory to the one containing currently edited file (via `cd`)
* Mouse wheel scrolls 3 lines at a time instead of only one.

### Notes
* <kbd>Ctrl</kbd> + <kbd>Click</kbd> functionality currently requires patched version of PyGObject (see https://gitlab.gnome.org/GNOME/pygobject/issues/366)
* File names are read as relative to current working directory of the terminal process, so when it changes, previous names won't work.
* It currently uses linux-specific `/proc/PID/cwd` to get the cwd of the terminal process.

## Installation
* Make sure the original terminal plugin is available (it's in the `gedit-plugins` package)
* Copy project folder to `~/.local/share/gedit/plugins`
* Enable this plugin (you didn't see it coming, did you?)
* ~~Uninstall~~ Enjoy :)
