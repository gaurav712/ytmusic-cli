"""Main entry point for YouTube Music CLI."""

import sys
import logging
import argparse
from pathlib import Path

from ytmusic_cli.interface import Interface
from ytmusic_cli.config import AUTH_HEADERS, COOKIES_FILE
from ytmusic_cli.cookie_converter import ensure_cookies_file


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='YouTube Music CLI - A terminal-based frontend for YouTube Music'
    )
    parser.add_argument('--auth-headers', type=str, default=None,
                        help=f'Path to auth headers JSON file (default: {AUTH_HEADERS})')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')

    args = parser.parse_args()
    setup_logging(args.verbose)

    auth_path = args.auth_headers or AUTH_HEADERS
    if not Path(auth_path).exists():
        print(f"Error: Auth headers file not found: {auth_path}")
        print("Please create the auth headers file or specify a different path with --auth-headers")
        print("See https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html for instructions")
        sys.exit(1)

    # Ensure cookies file is up-to-date
    try:
        if not ensure_cookies_file(auth_path, COOKIES_FILE):
            logging.warning("Failed to create/update cookies file. MPV will continue without cookie support.")
    except Exception as e:
        logging.warning(f"Error preparing cookies file: {e}. MPV will continue without cookie support.")

    try:
        Interface(auth_path)
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

