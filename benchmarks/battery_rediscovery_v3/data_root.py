"""Platform-specific location of approved local Forge research data.

Windows runs use the documented D:/forge-data location. WSL runs use the
corresponding mounted drive path so pinned input digests are checked against
the same external files without copying them into the repository.
"""

from __future__ import annotations

import os
import pathlib
import platform

if os.name == "nt":
    FORGE_DATA_ROOT = pathlib.Path("D:/forge-data")
elif "microsoft" in platform.release().lower():
    FORGE_DATA_ROOT = pathlib.Path("/mnt/d/forge-data")
else:
    FORGE_DATA_ROOT = pathlib.Path("D:/forge-data")
