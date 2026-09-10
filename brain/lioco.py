#!/usr/bin/env python3
"""Entry point for the lioco brain. Always prints one JSON object to stdout."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lioco_brain.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
