"""Main UI interface using urwid."""

import urwid
import signal
import sys
import logging
import time
from threading import Thread, Event
from typing import Dict, Any, List, Optional

from ytmusic_cli.player import Player
from ytmusic_cli.custom_list_box import CustomListBox

logger = logging.getLogger(__name__)


class NoMouseWidget(urwid.WidgetWrap):
    """Widget wrapper that disables all mouse events."""
    def mouse_event(self, size, event, button, col, row, focus):
        return False


class Interface:
    """Main interface class for the YouTube Music CLI."""

    def __init__(self, auth_headers_path: str = None) -> None:
        """Initialize the UI and player."""
        self.status_text = ''
        self.searching = False
        self.player: Optional[Player] = None
        self.mainloop: Optional[urwid.MainLoop] = None
        self.update_event = Event()
        self.update_thread: Optional[Thread] = None
        self._latest_time_pos: Optional[float] = None
        self._latest_duration: Optional[float] = None
        self._latest_is_paused: Optional[bool] = None
        self._latest_progress: float = 0
        self.current_song_name: str = 'Not Playing'

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            # Initialize the UI
            self.header = urwid.Text('YouTube Music CLI')
            self.now_playing = urwid.Text('Not Playing')
            self.status = urwid.Text('')
            self.progress_row = urwid.Text('')
            self.footer = urwid.Pile([
                ('pack', urwid.Divider()),
                ('pack', self.now_playing),
                ('pack', self.progress_row),
                ('pack', self.status)
            ])
            self.listbox = CustomListBox(
                self.handle_keypress,
                self.is_searching,
                urwid.SimpleFocusListWalker([])
            )
            body_with_blank = urwid.Pile([
                ('pack', urwid.Divider()),
                self.listbox
            ])
            self.frame = urwid.Frame(
                header=self.header,
                body=body_with_blank,
                footer=self.footer
            )
            top = NoMouseWidget(urwid.Padding(self.frame, left=2, right=2))

            # Initialize the player
            self.player = Player(auth_headers_path)

            # Start progress update thread
            self.update_event.clear()
            self.update_thread = Thread(target=self._update_progress_loop, daemon=True)
            self.update_thread.start()

            self.mainloop = urwid.MainLoop(top, unhandled_input=self.handle_keypress)
            # Disable mouse interactions
            self.mainloop.screen.set_mouse_tracking(False)
            # Set up recurring alarm to update UI
            self._schedule_progress_update()
            
            # Load recommended songs on boot
            self._load_recommended()
            
            self.mainloop.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error in interface: {e}", exc_info=True)
            raise
        finally:
            # Cleanup on exit
            self._cleanup()

    def _signal_handler(self, signum, frame) -> None:
        """Handle termination signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self._cleanup()
        sys.exit(0)

    def _cleanup(self) -> None:
        """Clean up all resources."""
        try:
            # Stop update thread
            if self.update_thread:
                self.update_event.set()
                if self.update_thread.is_alive():
                    self.update_thread.join(timeout=1)
            if self.player:
                self.player.cleanup()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    def _format_time(self, seconds: Optional[float]) -> str:
        """Format seconds as MM:SS."""
        if seconds is None:
            return "0:00"
        return f"{int(seconds // 60)}:{int(seconds % 60):02d}"

    def _format_song_display(self, song: Dict[str, Any]) -> str:
        """Format song dict as 'Title - Artist'."""
        title = song.get('title', 'Unknown')
        artist = song.get('artists', [{}])[0].get('name', 'Unknown')
        return f"{title} - {artist}"

    def _calc_progress(self, time_pos: Optional[float], duration: Optional[float]) -> float:
        """Calculate progress percentage."""
        if duration and duration > 0 and time_pos is not None:
            return min(max((time_pos / duration) * 100, 0), 100)
        return 0

    def _create_text_progress_bar(self, progress: float, width: int) -> str:
        """Create a text-based progress bar."""
        filled = int((progress / 100) * width)
        return '[' + '#' * filled + ' ' * (width - filled) + ']'

    def _update_progress_loop(self) -> None:
        """Periodically fetch progress data from mpv."""
        while not self.update_event.wait(0.5):
            if self.player and self.player.playback:
                self._latest_time_pos = self.player.get_time_pos()
                self._latest_duration = self.player.get_duration()
                self._latest_is_paused = self.player.is_paused()
                self._latest_progress = self._calc_progress(self._latest_time_pos, self._latest_duration)
            else:
                self._latest_time_pos = None
                self._latest_duration = None
                self._latest_is_paused = None
                self._latest_progress = 0

    def _schedule_progress_update(self) -> None:
        """Schedule the next progress update alarm."""
        if self.mainloop:
            self.mainloop.set_alarm_in(0.5, self._on_progress_update_alarm)

    def _on_progress_update_alarm(self, loop, user_data) -> None:
        """Alarm callback to update progress display."""
        try:
            self._update_progress_display(
                self._latest_time_pos,
                self._latest_duration,
                self._latest_is_paused,
                self._latest_progress
            )
            # Schedule next update
            self._schedule_progress_update()
        except Exception as e:
            logger.debug(f"Error in progress update alarm: {e}")
            # Still schedule next update even on error
            self._schedule_progress_update()

    def _update_progress_display(self, time_pos: Optional[float], duration: Optional[float],
                                  is_paused: Optional[bool], progress: float) -> None:
        """Update the progress display widgets.

        Args:
            time_pos: Current time position
            duration: Total duration
            is_paused: Whether playback is paused
            progress: Progress percentage (0-100)
        """
        try:
            cols = 80
            if self.mainloop:
                try:
                    cols, _ = self.mainloop.screen.get_cols_rows()
                except Exception:
                    pass
            
            width = max(cols - 4, 40)
            
            # Build timer text
            if time_pos is not None:
                icon = "⏸" if is_paused else "▶"
                dur_str = self._format_time(duration) if duration else "--:--"
                timer = f"{icon} {self._format_time(time_pos)} / {dur_str}"
            else:
                timer = ""

            # Build display row: timer + song name
            if timer and self.current_song_name:
                gap = 4
                remaining = width - len(timer) - gap
                if remaining > 0:
                    top_row = f"{timer}{' ' * gap}{self.current_song_name[:remaining]}"
                else:
                    top_row = timer
            else:
                top_row = timer or self.current_song_name[:width]
            
            self.now_playing.set_text(top_row[:width])
            self.progress_row.set_text(self._create_text_progress_bar(progress, width - 2))
        except Exception:
            pass

    def item_chosen(self, button: urwid.Button, choice: Dict[str, Any]) -> None:
        """Handle item selection from the list."""
        display_text = self._format_song_display(choice)
        self.now_playing.set_text(display_text)
        self.current_song_name = display_text
        
        if self.player:
            self.player.stop()
            self._latest_time_pos = None
            self._latest_duration = None
            self._latest_progress = 0
            self._update_progress_display(None, None, None, 0)

            video_id = choice.get('videoId')
            if video_id:
                self.player.start(f'https://music.youtube.com/watch?v={video_id}', display_text)

    def handle_keypress(self, key: str) -> None:
        """Handle keyboard input."""
        if key == 'backspace' and self.status_text:
            self.status_text = self.status_text[:-1]
            self.status.set_text(self.status_text)
        elif self.searching:
            if key == 'enter':
                self.handle_search()
            elif key == 'esc':
                self.searching = False
                self.status_text = ''
                self.status.set_text('')
            elif key and len(key) == 1:
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
        elif key == 'h' and self.player:
            self.player.seek(-10, relative=True)
        elif key == 'l' and self.player:
            self.player.seek(10, relative=True)

    def is_searching(self) -> bool:
        return self.searching

    def play_pause_toggle(self) -> None:
        """Toggle play/pause state."""
        if self.player and self.player.playback:
            if self.player.playing:
                self.player.pause()
            else:
                self.player.play()
            if self.mainloop:
                t, d = self.player.get_time_pos(), self.player.get_duration()
                self._update_progress_display(t, d, self.player.is_paused(), self._calc_progress(t, d))

    def _load_recommended(self) -> None:
        """Load recommended songs on boot."""
        if self.player:
            self.status.set_text('Loading recommended songs...')
            Thread(target=self.player.get_recommended, args=(self.search_thread_callback,), daemon=True).start()

    def handle_search(self) -> None:
        """Handle search query submission."""
        query = self.status_text[1:] if self.status_text.startswith('/') else self.status_text
        self.status.set_text(f'Searching for: {query}')
        Thread(target=self.player.search, args=(query, self.search_thread_callback), daemon=True).start()

    def search_thread_callback(self, search_results: List[Dict[str, Any]]) -> None:
        """Callback for search results."""
        if not search_results:
            self.status.set_text('No results found')
            self.searching = False
            return

        buttons = [
            urwid.Button(self._format_song_display(r), on_press=self.item_chosen, user_data=r)
            for r in search_results
        ]

        if buttons and self.mainloop:
            self.listbox.body = urwid.SimpleFocusListWalker(buttons)
            self.mainloop.draw_screen()
        
        self.searching = False
        self.status_text = ''
        self.status.set_text('')

