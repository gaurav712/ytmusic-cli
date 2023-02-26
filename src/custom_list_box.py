import urwid
from globals import HANDLED_KEYS


# Override urwid.ListBox to enable vim-like navigation
class CustomListBox(urwid.ListBox):

    def __init__(self, unhandled_input_callback, is_searching, body):
        self.unhandled_input_callback = unhandled_input_callback
        self.is_searching = is_searching
        super().__init__(body)

    def keypress(self, size, key):
        if not self.is_searching() and key in HANDLED_KEYS:
            if key == 'enter':
                super().keypress(size, key)
            elif key == 'j':
                super()._keypress_down(size)
            elif key == 'k':
                super()._keypress_up(size)
            return

        self.unhandled_input_callback(key)

