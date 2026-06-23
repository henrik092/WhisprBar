#!/usr/bin/env python3
"""
WhisprBar - Voice-to-text transcription tray application

This is the legacy entry point that provides backwards compatibility
with V5 installations. The actual application logic is in the whisprbar
package.
"""

from whisprbar.main import cli_main

if __name__ == "__main__":
    cli_main()
