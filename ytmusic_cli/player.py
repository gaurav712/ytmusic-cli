"""Player module for handling YouTube Music playback via mpv."""

import socket
import subprocess
import shlex
import logging
import os
import atexit
import signal
import json
import shutil
from time import sleep
from typing import Optional, Callable, List, Dict, Any, Set
from threading import Thread, Lock

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

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
                if PSUTIL_AVAILABLE:
                    try:
                        process = psutil.Process(pid)
                        if process.is_running():
                            cmdline = ' '.join(process.cmdline()).lower()
                            if 'mpv' in cmdline:
                                logger.debug(f"Terminating mpv process {pid}")
                                process.terminate()
                                try:
                                    process.wait(timeout=2)
                                except psutil.TimeoutExpired:
                                    logger.warning(f"Force killing mpv process {pid}")
                                    process.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                else:
                    # Fallback without psutil
                    try:
                        os.kill(pid, signal.SIGTERM)
                        sleep(0.5)
                        # Check if still alive and force kill
                        try:
                            os.kill(pid, 0)  # Check if process exists
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass  # Already dead
                    except ProcessLookupError:
                        pass  # Process doesn't exist
            except Exception as e:
                logger.warning(f"Error cleaning up process {pid}: {e}")
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
            # Clean up any existing socket
            _cleanup_orphaned_mpv()

            # Send notification (only if notify-send is available)
            notify_send_path = shutil.which('notify-send')
            if notify_send_path:
                try:
                    subprocess.run(
                        [notify_send_path, 'YouTube Music', 'Playing: ' + self.url],
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
                            except:
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
            except (socket.error, OSError):
                pass
            try:
                self.sock.close()
            except Exception as e:
                logger.debug(f"Error closing socket: {e}")
            finally:
                self.sock = None

        # Terminate process
        if self.process:
            pid = self.process.pid
            try:
                # Remove from tracking
                with _process_lock:
                    _mpv_processes.discard(pid)

                # Try graceful termination
                if self.process.poll() is None:  # Process still running
                    try:
                        # Try to terminate the process group (kills child processes too)
                        try:
                            pgid = os.getpgid(pid)
                            os.killpg(pgid, signal.SIGTERM)
                        except (ProcessLookupError, OSError, AttributeError):
                            # Fall back to process.terminate() if process group fails
                            self.process.terminate()
                    except ProcessLookupError:
                        pass  # Already dead

                    # Wait for termination
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        try:
                            try:
                                pgid = os.getpgid(pid)
                                os.killpg(pgid, signal.SIGKILL)
                            except (ProcessLookupError, OSError, AttributeError):
                                self.process.kill()
                        except ProcessLookupError:
                            pass  # Already dead
            except ProcessLookupError:
                # Process already terminated
                pass
            except Exception as e:
                logger.warning(f"Error terminating process {pid}: {e}")
                # Last resort: try to kill by PID
                try:
                    if pid:
                        os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
            finally:
                self.process = None

        # Clean up socket file if it exists
        try:
            if os.path.exists(IPC_SERVER_PATH):
                os.unlink(IPC_SERVER_PATH)
        except OSError:
            pass

    def send_command(self, ipc_command_json: str) -> Optional[bytes]:
        """Send an IPC command to mpv and receive response.

        Args:
            ipc_command_json: JSON command string

        Returns:
            Response bytes from mpv, or None on error
        """
        if not self.sock:
            logger.debug("Socket not connected, cannot send command")
            return None

        # Check if process is still alive
        if self.process and self.process.poll() is not None:
            logger.debug("mpv process has terminated")
            return None

        try:
            # Send the JSON IPC command to the socket
            self.sock.sendall(ipc_command_json.encode())

            # Receive a response from the socket
            return self.sock.recv(1024)
        except (socket.error, BrokenPipeError, ConnectionResetError) as e:
            logger.debug(f"Socket error sending command: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error sending command: {e}")
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
        """Get recommended songs from YouTube Music home page.

        Args:
            callback: Function to call with recommended songs
        """
        try:
            # Get home content without limit to avoid parsing issues
            home = self.ytmusic.get_home()
            songs = []
            
            # Extract songs from home page sections
            for section in home:
                try:
                    # Get section title to identify recommended sections
                    section_title = section.get('title', '').lower()
                    
                    # Look for recommended sections or any section with songs
                    # Skip sections that are not music content (like action cards)
                    if 'action' in section_title or 'card' in section_title:
                        continue
                    
                    # Get contents from section
                    contents = section.get('contents', [])
                    
                    for item in contents:
                        try:
                            # Check if it's a song directly (has videoId and title)
                            if 'videoId' in item and 'title' in item:
                                # Make sure it has artists (to filter out non-song items)
                                if 'artists' in item and len(item.get('artists', [])) > 0:
                                    songs.append(item)
                            # Check if it's a musicShelf or similar with nested items
                            elif 'items' in item:
                                for nested_item in item.get('items', []):
                                    if 'videoId' in nested_item and 'title' in nested_item:
                                        if 'artists' in nested_item and len(nested_item.get('artists', [])) > 0:
                                            songs.append(nested_item)
                        except (KeyError, TypeError, AttributeError) as e:
                            logger.debug(f"Error processing item in section: {e}")
                            continue
                except (KeyError, TypeError, AttributeError) as e:
                    logger.debug(f"Error processing section: {e}")
                    continue
            
            # Remove duplicates based on videoId
            seen_ids = set()
            unique_songs = []
            for song in songs:
                video_id = song.get('videoId')
                if video_id and video_id not in seen_ids:
                    seen_ids.add(video_id)
                    unique_songs.append(song)
            
            # Limit to first 50 songs
            callback(unique_songs[:50])
        except Exception as e:
            logger.error(f"Error getting recommended songs: {e}")
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
                # Update state based on actual mpv state
                is_paused = self.playback.is_paused()
                self.playing = not is_paused if is_paused is not None else True
            except Exception as e:
                logger.error(f"Error resuming playback: {e}")

    def pause(self) -> None:
        """Pause playback."""
        if self.playback:
            try:
                self.playback.pause()
                # Update state based on actual mpv state
                is_paused = self.playback.is_paused()
                self.playing = not is_paused if is_paused is not None else False
            except Exception as e:
                logger.error(f"Error pausing playback: {e}")

    def is_paused(self) -> Optional[bool]:
        """Check if playback is paused.

        Returns:
            True if paused, False if playing, None if not playing or error
        """
        if self.playback:
            return self.playback.is_paused()
        return None

    def get_time_pos(self) -> Optional[float]:
        """Get current playback position in seconds.

        Returns:
            Current time position in seconds, or None on error
        """
        if self.playback:
            return self.playback.get_time_pos()
        return None

    def get_duration(self) -> Optional[float]:
        """Get total duration of the current track in seconds.

        Returns:
            Duration in seconds, or None on error
        """
        if self.playback:
            return self.playback.get_duration()
        return None

    def seek(self, seconds: float, relative: bool = False) -> None:
        """Seek to a specific position.

        Args:
            seconds: Time in seconds to seek to (absolute) or offset (relative)
            relative: If True, seek relative to current position; if False, seek to absolute position
        """
        if self.playback:
            try:
                self.playback.seek(seconds, relative)
            except Exception as e:
                logger.error(f"Error seeking: {e}")

    def cleanup(self) -> None:
        """Clean up resources. Call this before destroying the player."""
        try:
            self.stop()
        except Exception as e:
            logger.warning(f"Error during player cleanup: {e}")

