"""Main UI interface using urwid."""

import urwid
from threading import Thread
from typing import Dict, Any, List

from ytmusic_cli.player import Player
from ytmusic_cli.custom_list_box import CustomListBox


class Interface:
    """Main interface class for the YouTube Music CLI."""

    def __init__(self, auth_headers_path: str = None) -> None:
        """Initialize the UI and player.

        Args:
            auth_headers_path: Optional path to auth headers file
        """
        self.status_text = ''
        self.searching = False

        # Initialize the UI
        self.header = urwid.Text('YouTube Music CLI')
        self.now_playing = urwid.Text('Not Playing')
        self.status = urwid.Text('')
        self.footer = urwid.Pile([self.now_playing, self.status])
        self.listbox = CustomListBox(
            self.handle_keypress,
            self.is_searching,
            urwid.SimpleFocusListWalker([])
        )
        self.frame = urwid.Frame(
            header=self.header,
            body=self.listbox,
            footer=self.footer
        )
        top = urwid.Padding(self.frame, left=2, right=2)

        # Initialize the player
        self.player = Player(auth_headers_path)

        self.mainloop = urwid.MainLoop(top, unhandled_input=self.handle_keypress)
        try:
            self.mainloop.run()
        finally:
            # Cleanup on exit
            self.player.cleanup()

    def item_chosen(self, button: urwid.Button, choice: Dict[str, Any]) -> None:
        """Handle item selection from the list.

        Args:
            button: The button widget (unused)
            choice: Dictionary containing song information
        """
        title = choice.get('title', 'Unknown')
        artist = choice.get('artists', [{}])[0].get('name', 'Unknown')
        display_text = f"{title} - {artist}"
        self.now_playing.set_text(display_text)
        self.player.stop()

        video_id = choice.get('videoId')
        if video_id:
            self.player.start(f'https://music.youtube.com/watch?v={video_id}')

    def handle_keypress(self, key: str) -> None:
        """Handle keyboard input.

        Args:
            key: Key pressed
        """
        # Handle backspace
        if key == 'backspace':
            if self.status_text:
                self.status_text = self.status_text[:-1]
                self.status.set_text(self.status_text)
        elif self.searching:
            if key == 'enter':
                self.handle_search()
                return
            # Add character to search query
            if key and len(key) == 1:
                self.status_text += key
                self.status.set_text(self.status_text)
        elif key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key == '/':
            self.searching = True
            self.status_text = '/'
            self.status.set_text(self.status_text)
        elif key == ' ':
            self.play_pause_toggle()

    def is_searching(self) -> bool:
        """Check if UI is in search mode.

        Returns:
            True if in search mode, False otherwise
        """
        return self.searching

    def play_pause_toggle(self) -> None:
        """Toggle play/pause state."""
        if self.player.playing:
            self.player.pause()
        else:
            self.player.play()

    def handle_search(self) -> None:
        """Handle search query submission."""
        query = self.status_text[1:] if self.status_text.startswith('/') else self.status_text
        self.status.set_text(f'Searching for: {query}')

        # Search async
        search_thread = Thread(
            target=self.player.search,
            args=(query, self.search_thread_callback),
            daemon=True
        )
        search_thread.start()

    def search_thread_callback(self, search_results: List[Dict[str, Any]]) -> None:
        """Callback for search results.

        Args:
            search_results: List of search result dictionaries
        """
        if not search_results:
            self.status.set_text('No results found')
            self.searching = False
            return

        # Create buttons for each result
        buttons = []
        for result in search_results:
            title = result.get('title', 'Unknown')
            artist = result.get('artists', [{}])[0].get('name', 'Unknown')
            button_text = f"{title} - {artist}"
            button = urwid.Button(
                button_text,
                on_press=self.item_chosen,
                user_data=result
            )
            buttons.append(button)

        # Replace the body using the public API
        self.listbox.body = urwid.SimpleFocusListWalker(buttons)
        self.mainloop.draw_screen()
        self.searching = False
        self.status_text = ''
        self.status.set_text('')

