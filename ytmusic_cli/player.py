"""Player module for handling YouTube Music playback via mpv."""

import socket
import subprocess
import shlex
import logging
from time import sleep
from typing import Optional, Callable, List, Dict, Any
from threading import Thread

from ytmusicapi import YTMusic

from ytmusic_cli.config import AUTH_HEADERS, IPC_SERVER_PATH, PAUSE_CMD, PLAY_CMD

logger = logging.getLogger(__name__)


class PlayerThread(Thread):
    """Thread for managing mpv playback process and IPC communication."""

    def __init__(self, url: str) -> None:
        """Initialize the player thread with a URL.

        Args:
            url: YouTube Music URL to play
        """
        super().__init__(daemon=True)
        self.url = url
        self.process: Optional[subprocess.Popen] = None
        self.sock: Optional[socket.socket] = None

    def run(self) -> None:
        """Start mpv player and establish IPC connection."""
        try:
            # Send notification
            subprocess.run(
                ['notify-send', 'YouTube Music', 'Playing: ' + self.url],
                check=False,
                capture_output=True
            )

            # Start the player with proper argument escaping
            cmd = [
                'mpv',
                self.url,
                '--no-video',
                '--cache=no',
                f'--input-ipc-server={IPC_SERVER_PATH}'
            ]
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Create a socket object
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

            # Connect to the socket with retry logic
            max_retries = 5
            for attempt in range(max_retries):
                sleep(0.5)
                try:
                    self.sock.connect(IPC_SERVER_PATH)
                    break
                except (socket.error, FileNotFoundError) as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to connect to IPC socket after {max_retries} attempts: {e}")
                        raise
        except Exception as e:
            logger.error(f"Error in PlayerThread.run: {e}")
            raise

    def terminate(self) -> None:
        """Terminate the player process and close socket."""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.warning(f"Error closing socket: {e}")
            finally:
                self.sock = None

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.warning(f"Error terminating process: {e}")
            finally:
                self.process = None

    def send_command(self, ipc_command_json: str) -> Optional[bytes]:
        """Send an IPC command to mpv and receive response.

        Args:
            ipc_command_json: JSON command string

        Returns:
            Response bytes from mpv, or None on error
        """
        if not self.sock:
            logger.warning("Socket not connected, cannot send command")
            return None

        try:
            # Send the JSON IPC command to the socket
            self.sock.sendall(ipc_command_json.encode())

            # Receive a response from the socket
            return self.sock.recv(1024)
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return None

    def play(self) -> None:
        """Resume playback."""
        self.send_command(PLAY_CMD)

    def pause(self) -> None:
        """Pause playback."""
        self.send_command(PAUSE_CMD)


class Player:
    """Main player class for YouTube Music."""

    def __init__(self, auth_headers_path: Optional[str] = None) -> None:
        """Initialize the player with YouTube Music API.

        Args:
            auth_headers_path: Optional path to auth headers file.
                              If None, uses default from config.
        """
        self.playing = False
        self.playback: Optional[PlayerThread] = None

        # Initialize connection
        headers_path = auth_headers_path or AUTH_HEADERS
        try:
            self.ytmusic = YTMusic(headers_path)
        except Exception as e:
            logger.error(f"Failed to initialize YTMusic API: {e}")
            raise

    def search(self, query: str, callback: Callable[[List[Dict[str, Any]]], None]) -> None:
        """Search for songs on YouTube Music.

        Args:
            query: Search query string
            callback: Function to call with search results
        """
        if not query or not query.strip():
            callback([])
            return

        try:
            results = self.ytmusic.search(query=query.strip(), filter='songs')
            callback(results)
        except Exception as e:
            logger.error(f"Search error: {e}")
            callback([])

    def start(self, url: str) -> None:
        """Start playing a URL.

        Args:
            url: YouTube Music URL to play
        """
        self.stop()  # Stop any existing playback
        self.playback = PlayerThread(url)
        self.playback.start()
        self.playing = True

    def stop(self) -> None:
        """Stop current playback."""
        if self.playback:
            try:
                self.playback.terminate()
            except Exception as e:
                logger.warning(f"Error stopping playback: {e}")
            finally:
                self.playback = None
                self.playing = False

    def play(self) -> None:
        """Resume playback."""
        if self.playback:
            try:
                self.playback.play()
                self.playing = True
            except Exception as e:
                logger.error(f"Error resuming playback: {e}")

    def pause(self) -> None:
        """Pause playback."""
        if self.playback:
            try:
                self.playback.pause()
                self.playing = False
            except Exception as e:
                logger.error(f"Error pausing playback: {e}")

    def cleanup(self) -> None:
        """Clean up resources. Call this before destroying the player."""
        self.stop()

