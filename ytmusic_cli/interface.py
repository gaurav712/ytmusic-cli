"""Main UI interface using urwid."""

import urwid
import signal
import sys
import logging
from threading import Thread, Event
from typing import Dict, Any, List, Optional

from ytmusic_cli.player import Player
from ytmusic_cli.custom_list_box import CustomListBox

logger = logging.getLogger(__name__)


class Interface:
    """Main interface class for the YouTube Music CLI."""

    def __init__(self, auth_headers_path: str = None) -> None:
        """Initialize the UI and player.

        Args:
            auth_headers_path: Optional path to auth headers file
        """
        self.status_text = ''
        self.searching = False
        self.player: Optional[Player] = None
        self.mainloop: Optional[urwid.MainLoop] = None
        self.update_event = Event()
        self.update_thread: Optional[Thread] = None
        # Store latest progress values for UI updates
        self._latest_time_pos: Optional[float] = None
        self._latest_duration: Optional[float] = None
        self._latest_is_paused: Optional[bool] = None
        self._latest_progress: float = 0
        self.current_song_name: str = 'Not Playing'

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            # Initialize the UI
            self.header = urwid.Text('YouTube Music CLI')
            self.now_playing = urwid.Text('Not Playing')
            self.status = urwid.Text('')
            self.progress_row = urwid.Text('')
            self.footer = urwid.Pile([
                (1, urwid.SolidFill()),  # Blank row above bottom two rows
                self.now_playing,
                self.progress_row,
                self.status
            ])
            self.listbox = CustomListBox(
                self.handle_keypress,
                self.is_searching,
                urwid.SimpleFocusListWalker([])
            )
            # Add blank row above listbox
            body_with_blank = urwid.Pile([
                (1, urwid.SolidFill()),  # Blank row above song list
                self.listbox
            ])
            self.frame = urwid.Frame(
                header=self.header,
                body=body_with_blank,
                footer=self.footer
            )
            top = urwid.Padding(self.frame, left=2, right=2)

            # Initialize the player
            self.player = Player(auth_headers_path)

            # Start progress update thread
            self.update_event.clear()
            self.update_thread = Thread(target=self._update_progress_loop, daemon=True)
            self.update_thread.start()

            self.mainloop = urwid.MainLoop(top, unhandled_input=self.handle_keypress)
            # Set up recurring alarm to update UI
            self._schedule_progress_update()
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
        """Format seconds as MM:SS.

        Args:
            seconds: Time in seconds, or None

        Returns:
            Formatted time string
        """
        if seconds is None:
            return "0:00"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def _create_text_progress_bar(self, progress: float, width: int) -> str:
        """Create a text-based progress bar.

        Args:
            progress: Progress percentage (0-100)
            width: Width of the progress bar (excluding brackets)

        Returns:
            Progress bar string like [#####            ]
        """
        filled = int((progress / 100) * width)
        empty = width - filled
        return '[' + '#' * filled + ' ' * empty + ']'

    def _update_progress_loop(self) -> None:
        """Periodically fetch progress data from mpv."""
        import time
        while not self.update_event.wait(0.5):  # Update every 0.5 seconds
            try:
                if self.player and self.player.playback:
                    time_pos = self.player.get_time_pos()
                    duration = self.player.get_duration()
                    is_paused = self.player.is_paused()

                    # Update progress bar
                    if duration and duration > 0 and time_pos is not None:
                        progress = min(max((time_pos / duration) * 100, 0), 100)
                    else:
                        progress = 0
                    
                    # Store latest values (thread-safe since we're just writing)
                    self._latest_time_pos = time_pos
                    self._latest_duration = duration
                    self._latest_is_paused = is_paused
                    self._latest_progress = progress
                else:
                    # No playback active
                    self._latest_time_pos = None
                    self._latest_duration = None
                    self._latest_is_paused = None
                    self._latest_progress = 0
            except Exception as e:
                logger.debug(f"Error updating progress: {e}")

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
            # Get terminal width (default to 80 if not available)
            try:
                if self.mainloop:
                    screen = self.mainloop.screen
                    cols, _ = screen.get_cols_rows()
                else:
                    cols = 80
            except:
                cols = 80

            # Calculate available width (accounting for padding)
            available_width = max(cols - 4, 40)  # Subtract padding (2 on each side)
            
            # Build the timer text
            if time_pos is not None and duration is not None:
                status_icon = "⏸" if is_paused else "▶"
                time_str = f"{self._format_time(time_pos)} / {self._format_time(duration)}"
                timer_text = f"{status_icon} {time_str}"
            elif time_pos is not None:
                status_icon = "⏸" if is_paused else "▶"
                time_str = f"{self._format_time(time_pos)} / --:--"
                timer_text = f"{status_icon} {time_str}"
            else:
                timer_text = ""

            # Update the top row: timer on left, song name centered
            song_name = self.current_song_name
            timer_width = len(timer_text) if timer_text else 0
            
            # Build the top row: timer on left, song name centered
            if timer_text and song_name:
                # Calculate space for song name (remaining width after timer)
                remaining_width = available_width - timer_width
                if remaining_width > 0:
                    # Center song name in remaining space
                    song_display = song_name[:remaining_width]
                    padding = (remaining_width - len(song_display)) // 2
                    top_row = timer_text + ' ' * padding + song_display
                else:
                    top_row = timer_text
            elif timer_text:
                top_row = timer_text
            elif song_name:
                # Just center the song name
                song_display = song_name[:available_width]
                padding = (available_width - len(song_display)) // 2
                top_row = ' ' * padding + song_display
            else:
                top_row = ""
            
            # Truncate to fit
            top_row = top_row[:available_width]
            self.now_playing.set_text(top_row)
            
            # Update the bottom row: just the progress bar
            progress_bar_width = available_width - 2  # -2 for brackets
            progress_bar_text = self._create_text_progress_bar(progress, progress_bar_width)
            self.progress_row.set_text(progress_bar_text)
        except Exception as e:
            logger.debug(f"Error updating progress display: {e}")

    def item_chosen(self, button: urwid.Button, choice: Dict[str, Any]) -> None:
        """Handle item selection from the list.

        Args:
            button: The button widget (unused)
            choice: Dictionary containing song information
        """
        try:
            title = choice.get('title', 'Unknown')
            artist = choice.get('artists', [{}])[0].get('name', 'Unknown')
            display_text = f"{title} - {artist}"
            self.now_playing.set_text(display_text)
            self.current_song_name = display_text
            
            if self.player:
                self.player.stop()
                # Reset progress display
                self._latest_time_pos = None
                self._latest_duration = None
                self._latest_progress = 0
                self._update_progress_display(None, None, None, 0)

                video_id = choice.get('videoId')
                if video_id:
                    self.player.start(f'https://music.youtube.com/watch?v={video_id}')
        except Exception as e:
            logger.error(f"Error in item_chosen: {e}")
            self.status.set_text(f'Error: {str(e)}')

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
        elif key == 'h':
            # Seek backward 10 seconds
            if self.player:
                self.player.seek(-10, relative=True)
        elif key == 'l':
            # Seek forward 10 seconds
            if self.player:
                self.player.seek(10, relative=True)

    def is_searching(self) -> bool:
        """Check if UI is in search mode.

        Returns:
            True if in search mode, False otherwise
        """
        return self.searching

    def play_pause_toggle(self) -> None:
        """Toggle play/pause state."""
        if self.player and self.player.playback:
            if self.player.playing:
                self.player.pause()
            else:
                self.player.play()
            # Force immediate update of status
            if self.mainloop:
                time_pos = self.player.get_time_pos()
                duration = self.player.get_duration()
                is_paused = self.player.is_paused()
                progress = 0
                if duration and duration > 0 and time_pos is not None:
                    progress = min(max((time_pos / duration) * 100, 0), 100)
                self._update_progress_display(time_pos, duration, is_paused, progress)

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
        try:
            if not search_results:
                self.status.set_text('No results found')
                self.searching = False
                return

            # Create buttons for each result
            buttons = []
            for result in search_results:
                try:
                    title = result.get('title', 'Unknown')
                    artist = result.get('artists', [{}])[0].get('name', 'Unknown')
                    button_text = f"{title} - {artist}"
                    button = urwid.Button(
                        button_text,
                        on_press=self.item_chosen,
                        user_data=result
                    )
                    buttons.append(button)
                except Exception as e:
                    logger.warning(f"Error creating button for result: {e}")
                    continue

            if buttons and self.mainloop:
                # Replace the body using the public API
                self.listbox.body = urwid.SimpleFocusListWalker(buttons)
                self.mainloop.draw_screen()
            
            self.searching = False
            self.status_text = ''
            self.status.set_text('')
        except Exception as e:
            logger.error(f"Error in search_thread_callback: {e}")
            self.status.set_text(f'Error displaying results: {str(e)}')
            self.searching = False

