import ctypes
import ctypes.util

vte = ctypes.cdll.LoadLibrary(ctypes.util.find_library("vte-2.91"))
glib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("glib-2.0"))
glib.g_free.restype = None


def gobject_addr(obj):
    return int(str(obj).split(" at ")[-1].split(')')[0], 16)


def vte_terminal_event_check_regex_simple(terminal, event, regexes, flags):
    n_regexes = len(regexes)

    c_regexes = (ctypes.c_void_p * n_regexes)()
    for idx, regex in enumerate(regexes):
        c_regexes[idx] = gobject_addr(regex)

    c_matches = (ctypes.c_void_p * 1)()

    has_matches = vte.vte_terminal_event_check_regex_simple(
        ctypes.c_void_p(gobject_addr(terminal)),
        ctypes.c_void_p(gobject_addr(event)),
        c_regexes,
        ctypes.c_size_t(n_regexes),
        ctypes.c_uint32(flags),
        c_matches,
    )

    matches = [None] * n_regexes

    for idx, match_ptr in enumerate(c_matches):
        if match_ptr:
            match = ctypes.cast(match_ptr, ctypes.c_char_p).value

            matches[idx] = match.decode()

            glib.g_free(ctypes.c_void_p(match_ptr))

    return has_matches, matches
