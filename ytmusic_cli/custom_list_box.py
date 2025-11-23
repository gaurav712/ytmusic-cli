"""Custom ListBox widget with vim-like navigation."""

from typing import Callable, Optional
import urwid

from ytmusic_cli.config import HANDLED_KEYS


class CustomListBox(urwid.ListBox):
    """ListBox with vim-like navigation (j/k keys)."""

    def __init__(
        self,
        unhandled_input_callback: Callable[[str], None],
        is_searching: Callable[[], bool],
        body: urwid.ListWalker
    ) -> None:
        """Initialize the custom list box.

        Args:
            unhandled_input_callback: Function to call for unhandled keys
            is_searching: Function that returns True if in search mode
            body: ListWalker for the list items
        """
        self.unhandled_input_callback = unhandled_input_callback
        self.is_searching = is_searching
        super().__init__(body)

    def keypress(self, size: tuple, key: str) -> Optional[str]:
        """Handle keypress events with vim-like navigation.

        Args:
            size: Size tuple (width, height)
            key: Key pressed

        Returns:
            Unhandled key or None
        """
        if not self.is_searching() and key in HANDLED_KEYS:
            if key == 'enter':
                return super().keypress(size, key)
            elif key == 'j':
                super()._keypress_down(size)
                return None
            elif key == 'k':
                super()._keypress_up(size)
                return None

        return self.unhandled_input_callback(key)

