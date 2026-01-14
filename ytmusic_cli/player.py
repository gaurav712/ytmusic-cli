"""Player module for handling YouTube Music playback via mpv."""

import socket
import subprocess
import logging
import os
import atexit
import signal
import json
import shutil
from time import sleep
from typing import Optional, Callable, List, Dict, Any, Set
from threading import Thread, Lock

import psutil
from ytmusicapi import YTMusic

from ytmusic_cli.config import AUTH_HEADERS, IPC_SERVER_PATH, PAUSE_CMD, PLAY_CMD

logger = logging.getLogger(__name__)

# Global registry to track all mpv processes started by this application
_mpv_processes: Set[int] = set()
_process_lock = Lock()


def _cleanup_mpv_processes() -> None:
    """Clean up all tracked mpv processes."""
    with _process_lock:
        for pid in list(_mpv_processes):
            try:
                process = psutil.Process(pid)
                if process.is_running() and 'mpv' in ' '.join(process.cmdline()).lower():
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except psutil.TimeoutExpired:
                        process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        _mpv_processes.clear()


def _cleanup_orphaned_mpv() -> None:
    """Clean up any orphaned mpv processes using our IPC socket."""
    try:
        # Check if socket exists and try to connect
        if os.path.exists(IPC_SERVER_PATH):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                sock.connect(IPC_SERVER_PATH)
                sock.close()
            except (socket.error, ConnectionRefusedError):
                # Socket exists but no process listening - clean it up
                try:
                    os.unlink(IPC_SERVER_PATH)
                except OSError:
                    pass
    except Exception as e:
        logger.debug(f"Error checking for orphaned mpv: {e}")


# Register cleanup functions
atexit.register(_cleanup_mpv_processes)
atexit.register(_cleanup_orphaned_mpv)


class PlayerThread(Thread):
    """Thread for managing mpv playback process and IPC communication."""

    def __init__(self, url: str, song_name: Optional[str] = None) -> None:
        """Initialize the player thread with a URL.

        Args:
            url: YouTube Music URL to play
            song_name: Optional song name for notifications
        """
        super().__init__(daemon=True)
        self.url = url
        self.song_name = song_name
        self.process: Optional[subprocess.Popen] = None
        self.sock: Optional[socket.socket] = None

    def run(self) -> None:
        """Start mpv player and establish IPC connection."""
        try:
            # Clean up any existing socket
            _cleanup_orphaned_mpv()

            # Send notification (only if notify-send is available)
            notify_send_path = shutil.which('notify-send')
            if notify_send_path:
                try:
                    notification_text = self.song_name if self.song_name else self.url
                    subprocess.run(
                        [notify_send_path, 'YouTube Music', 'Playing: ' + notification_text],
                        check=False,
                        capture_output=True,
                        timeout=2
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    # notify-send not available or timed out - not critical
                    pass

            # Find mpv dynamically
            mpv_path = shutil.which('mpv')
            if not mpv_path:
                logger.error("mpv not found. Please install mpv: sudo apt install mpv (or equivalent)")
                raise FileNotFoundError("mpv executable not found in PATH")

            # Start the player with proper argument escaping
            cmd = [
                mpv_path,
                self.url,
                '--no-video',
                '--cache=no',
                '--start=0',
                f'--input-ipc-server={IPC_SERVER_PATH}'
            ]
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True  # Create new process group
                )
            except FileNotFoundError:
                logger.error("mpv not found. Please install mpv: sudo apt install mpv (or equivalent)")
                raise
            except Exception as e:
                logger.error(f"Failed to start mpv: {e}")
                raise

            # Track the process
            if self.process and self.process.pid:
                with _process_lock:
                    _mpv_processes.add(self.process.pid)

            # Create a socket object
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)  # Set timeout for connection

            # Connect to the socket with retry logic
            max_retries = 5
            for attempt in range(max_retries):
                sleep(0.5)
                try:
                    self.sock.connect(IPC_SERVER_PATH)
                    self.sock.settimeout(None)  # Remove timeout after connection
                    break
                except (socket.error, FileNotFoundError, ConnectionRefusedError) as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to connect to IPC socket after {max_retries} attempts: {e}")
                        # Clean up the process if socket connection failed
                        if self.process:
                            try:
                                self.process.terminate()
                                self.process.wait(timeout=1)
                            except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
                                if self.process:
                                    self.process.kill()
                        raise
                except Exception as e:
                    logger.error(f"Unexpected error connecting to socket: {e}")
                    raise
        except Exception as e:
            logger.error(f"Error in PlayerThread.run: {e}")
            # Ensure cleanup on error
            self.terminate()
            raise

    def terminate(self) -> None:
        """Terminate the player process and close socket."""
        # Close socket first
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except (socket.error, OSError):
                pass
            self.sock = None

        # Terminate process
        if self.process:
            pid = self.process.pid
            with _process_lock:
                _mpv_processes.discard(pid)
            
            try:
                if self.process.poll() is None:
                    # Try process group termination first
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                    except (ProcessLookupError, OSError):
                        self.process.terminate()
                    
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
            except (ProcessLookupError, OSError):
                pass
            self.process = None

        # Clean up socket file
        try:
            os.unlink(IPC_SERVER_PATH)
        except OSError:
            pass

    def send_command(self, ipc_command_json: str) -> Optional[bytes]:
        """Send an IPC command to mpv and receive response."""
        if not self.sock or (self.process and self.process.poll() is not None):
            return None
        try:
            self.sock.sendall(ipc_command_json.encode())
            return self.sock.recv(1024)
        except (socket.error, BrokenPipeError, ConnectionResetError):
            return None

    def play(self) -> None:
        """Resume playback."""
        self.send_command(PLAY_CMD)

    def pause(self) -> None:
        """Pause playback."""
        self.send_command(PAUSE_CMD)

    def get_property(self, property_name: str) -> Optional[Any]:
        """Get a property value from mpv.

        Args:
            property_name: Name of the property to get

        Returns:
            Property value or None on error
        """
        cmd = json.dumps({"command": ["get_property", property_name]}) + "\n"
        response = self.send_command(cmd)
        if response:
            try:
                data = json.loads(response.decode())
                if "data" in data:
                    return data["data"]
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                pass
        return None

    def is_paused(self) -> Optional[bool]:
        """Check if playback is paused.

        Returns:
            True if paused, False if playing, None on error
        """
        return self.get_property("pause")

    def get_time_pos(self) -> Optional[float]:
        """Get current playback position in seconds.

        Returns:
            Current time position in seconds, or None on error
        """
        return self.get_property("time-pos")

    def get_duration(self) -> Optional[float]:
        """Get total duration of the current track in seconds.

        Returns:
            Duration in seconds, or None on error
        """
        return self.get_property("duration")

    def seek(self, seconds: float, relative: bool = False) -> None:
        """Seek to a specific position.

        Args:
            seconds: Time in seconds to seek to (absolute) or offset (relative)
            relative: If True, seek relative to current position; if False, seek to absolute position
        """
        seek_type = "relative" if relative else "absolute"
        cmd = json.dumps({"command": ["seek", seconds, seek_type]}) + "\n"
        self.send_command(cmd)


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

    def get_recommended(self, callback: Callable[[List[Dict[str, Any]]], None]) -> None:
        """Get recommended songs from YouTube Music home page."""
        def is_valid_song(item: Dict) -> bool:
            return 'videoId' in item and 'title' in item and item.get('artists')
        
        try:
            home = self.ytmusic.get_home()
            songs = []
            
            for section in home:
                section_title = section.get('title', '').lower()
                if 'action' in section_title or 'card' in section_title:
                    continue
                
                for item in section.get('contents', []):
                    if is_valid_song(item):
                        songs.append(item)
                    for nested in item.get('items', []):
                        if is_valid_song(nested):
                            songs.append(nested)
            
            # Deduplicate by videoId
            seen = set()
            unique = [s for s in songs if s.get('videoId') not in seen and not seen.add(s.get('videoId'))]
            callback(unique[:50])
        except Exception as e:
            logger.error(f"Error getting recommended songs: {e}")
            callback([])

    def start(self, url: str, song_name: Optional[str] = None) -> None:
        """Start playing a URL.

        Args:
            url: YouTube Music URL to play
            song_name: Optional song name for notifications
        """
        self.stop()  # Stop any existing playback
        self.playback = PlayerThread(url, song_name)
        self.playback.start()
        self.playing = True

    def stop(self) -> None:
        """Stop current playback."""
        if self.playback:
            self.playback.terminate()
            self.playback = None
            self.playing = False

    def play(self) -> None:
        """Resume playback."""
        if self.playback:
            self.playback.play()
            self.playing = True

    def pause(self) -> None:
        """Pause playback."""
        if self.playback:
            self.playback.pause()
            self.playing = False

    def is_paused(self) -> Optional[bool]:
        return self.playback.is_paused() if self.playback else None

    def get_time_pos(self) -> Optional[float]:
        return self.playback.get_time_pos() if self.playback else None

    def get_duration(self) -> Optional[float]:
        return self.playback.get_duration() if self.playback else None

    def seek(self, seconds: float, relative: bool = False) -> None:
        if self.playback:
            self.playback.seek(seconds, relative)

    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop()

