> **Note:** This project is moved to Codeberg: https://codeberg.org/gaurav712/ytmusic-cli

# ytmusic-cli

A terminal-based frontend for YouTube Music using urwid for UI, ytmusicapi for API access, and mpv for playback.

## Features

- Search and play YouTube Music songs
- Vim-like navigation (j/k keys)
- Play/pause and seeking controls
- Progress bar with time display
- Loads recommended songs on startup

## Requirements

- Python 3.7+
- mpv (system package)
- YouTube Music auth headers file

## Installation

1. Install mpv:
   ```bash
   # Debian/Ubuntu
   sudo apt install mpv
   
   # Arch Linux
   sudo pacman -S mpv
   
   # macOS
   brew install mpv
   ```

2. Install the package:
   ```bash
   pip install -e .
   ```

3. Set up YouTube Music authentication:
   - Follow the [ytmusicapi setup guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)
   - Save the headers file to `~/.config/ytmusic-cli/headersauth.json`

## Usage

```bash
ytmusic-cli
```

Or with options:
```bash
ytmusic-cli --auth-headers /path/to/headers.json
ytmusic-cli --verbose
```

### Controls

| Key | Action |
|-----|--------|
| `/` | Search |
| `Escape` | Cancel Search |
| `j` | Move down |
| `k` | Move up |
| `Enter` | Select / Submit |
| `Space` | Play/Pause |
| `h` | Seek -10s |
| `l` | Seek +10s |
| `q` | Quit |

## Project Structure

```
ytmusic-cli/
├── pyproject.toml        # Package configuration
├── ytmusic_cli/
│   ├── main.py           # Entry point
│   ├── interface.py      # UI
│   ├── player.py         # Playback
│   ├── config.py         # Constants
│   └── custom_list_box.py
└── README.md
```

## License

MIT
