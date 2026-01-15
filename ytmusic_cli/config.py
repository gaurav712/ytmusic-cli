"""Configuration constants for the application."""

import os
from pathlib import Path

AUTH_HEADERS = os.getenv(
    "YT_MUSIC_AUTH_HEADERS",
    str(Path.home() / ".config" / "ytmusic-cli" / "headersauth.json")
)

COOKIES_FILE = os.getenv(
    "YT_MUSIC_COOKIES_FILE",
    str(Path.home() / ".config" / "ytmusic-cli" / "cookies.txt")
)

IPC_SERVER_PATH = "/tmp/mpvsocket"

PLAY_CMD = '{ "command": ["set_property", "pause", false] }\n'
PAUSE_CMD = '{ "command": ["set_property", "pause", true] }\n'

