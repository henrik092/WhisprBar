#!/usr/bin/env python3
"""
WhisprBar - Voice-to-text transcription tray application

This is the legacy entry point that provides backwards compatibility
with V5 installations. The actual application logic is in the whisprbar
package.
"""

import sys
from whisprbar.main import main, parse_args
from whisprbar.ui import _run_diagnostics_cli
from whisprbar.config import load_config, cfg

if __name__ == "__main__":
    cli_args = parse_args(sys.argv[1:])
    if cli_args.diagnose:
        load_config()
        sys.exit(_run_diagnostics_cli(cfg))
    main()
