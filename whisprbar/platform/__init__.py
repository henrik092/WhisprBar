"""Platform-specific functionality package for WhisprBar.

Re-exports submodules for convenient access. The original modules
(whisprbar.paste, whisprbar.tray, whisprbar.hotkeys) remain in place
for backwards compatibility; this package provides an alternative
organizational structure.
"""

from . import detection
from . import paste
from . import tray
from . import hotkeys

__all__ = [
    "detection",
    "paste",
    "tray",
    "hotkeys",
]
