"""Setup configuration for ytmusic-cli.

This file is kept for backward compatibility. Modern installations should use:
    pip install -e .

Or for building:
    pip install build
    python -m build
"""

try:
    from setuptools import setup, find_packages
except ImportError:
    print("Error: setuptools is required. Install it with:")
    print("  pip install setuptools")
    print("\nOr use modern pip installation:")
    print("  pip install -e .")
    raise

from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="ytmusic-cli",
    version="0.1.0",
    description="A terminal-based frontend for YouTube Music",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/ytmusic-cli",
    packages=find_packages(),
    install_requires=[
        "ytmusicapi>=1.0.0",
        "urwid>=2.1.0",
        "psutil>=5.8.0",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "ytmusic-cli=ytmusic_cli.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio :: Players",
    ],
)

