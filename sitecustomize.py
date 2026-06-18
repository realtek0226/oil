"""Local startup compatibility patches for the oil research app."""
from __future__ import annotations

import platform
import sys


if sys.platform.startswith("win") and hasattr(platform, "_wmi_query"):
    def _safe_wmi_query(*_args: object, **_kwargs: object) -> list[str]:
        return ["10.0.0", "1", "Multiprocessor Free", "0", "0"]

    platform._wmi_query = _safe_wmi_query
