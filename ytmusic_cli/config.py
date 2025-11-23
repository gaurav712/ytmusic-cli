"""Configuration constants for the application."""

import os
from pathlib import Path

# Path to auth headers file (relative to user's home or current directory)
AUTH_HEADERS = os.getenv(
    "YT_MUSIC_AUTH_HEADERS",
    str(Path.home() / ".config" / "ytmusic-cli" / "headersauth.json")
)

# Socket to control mpv
IPC_SERVER_PATH = "/tmp/mpvsocket"

# IPC Commands
PLAY_CMD = '{ "command": ["set_property", "pause", false] }\n'
PAUSE_CMD = '{ "command": ["set_property", "pause", true] }\n'

# Keys to be handled by the list view
HANDLED_KEYS = ['k', 'j', 'enter']

