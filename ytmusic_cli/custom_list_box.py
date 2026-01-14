"""Custom ListBox widget with vim-like navigation."""

from typing import Callable, Optional
import urwid


class CustomListBox(urwid.ListBox):
    """ListBox with vim-like navigation (j/k keys)."""

    def __init__(self, unhandled_input_callback: Callable[[str], None],
                 is_searching: Callable[[], bool], body: urwid.ListWalker) -> None:
        self.unhandled_input_callback = unhandled_input_callback
        self.is_searching = is_searching
        super().__init__(body)

    def keypress(self, size: tuple, key: str) -> Optional[str]:
        """Handle keypress events with vim-like navigation."""
        if not self.is_searching() and key in ('j', 'k', 'enter'):
            if key == 'enter':
                return super().keypress(size, key)
            elif key == 'j':
                super()._keypress_down(size)
            elif key == 'k':
                super()._keypress_up(size)
            return None
        return self.unhandled_input_callback(key)

