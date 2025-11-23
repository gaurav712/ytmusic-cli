# ytmusic-cli

A terminal-based frontend for YouTube Music using urwid for UI, ytmusicapi for API access, and mpv for playback.

## Features

- Search and play YouTube Music songs from the terminal
- Vim-like navigation (j/k keys)
- Play/pause control
- Clean, minimal interface

## Requirements

- Python 3.7+
- mpv (must be installed separately)
- YouTube Music auth headers file

## Installation

1. Install system dependencies:
   ```bash
   # Debian/Ubuntu
   sudo apt install mpv
   
   # Arch Linux
   sudo pacman -S mpv
   
   # macOS (with Homebrew)
   brew install mpv
   ```

2. Install Python dependencies:
   
   **Recommended (modern approach):**
   ```bash
   pip install -e .
   ```
   
   This will automatically install setuptools if needed and install the package in editable mode.
   
   **Alternative:**
   ```bash
   pip install -r requirements.txt
   ```
   
   Note: If you encounter setuptools errors, install it first:
   ```bash
   pip install setuptools wheel
   ```

3. Set up YouTube Music auth headers:
   - Follow the instructions at https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html
   - Place the `headersauth.json` file in `~/.config/ytmusic-cli/` or specify a custom path

## Usage

There are several ways to run the application:

**1. Using the installed command (recommended after installation):**
```bash
ytmusic-cli
```

**2. As a Python module:**
```bash
python3 -m ytmusic_cli
```

**3. Directly running the main module:**
```bash
python3 -m ytmusic_cli.main
```

**With custom auth headers path:**
```bash
ytmusic-cli --auth-headers /path/to/headersauth.json
# or
python3 -m ytmusic_cli --auth-headers /path/to/headersauth.json
```

**With verbose logging:**
```bash
ytmusic-cli --verbose
```

### Controls

- `/` - Start search
- `j` - Move down in list
- `k` - Move up in list
- `Enter` - Select item / Submit search
- `Space` - Play/Pause
- `q` - Quit

## Project Structure

```
ytmusic-cli/
├── ytmusic_cli/          # Main package
│   ├── __init__.py       # Package initialization
│   ├── config.py         # Configuration constants
│   ├── player.py         # Player and playback logic
│   ├── interface.py      # UI interface
│   ├── custom_list_box.py # Custom UI widget
│   └── main.py           # Entry point
├── requirements.txt      # Python dependencies
├── setup.py             # Package setup
└── README.md            # This file
```

## Development

To develop or modify the code:

1. Clone the repository
2. Install in development mode:
   ```bash
   pip install -e .
   ```
3. Make your changes
4. Test the application

## License

MIT License
