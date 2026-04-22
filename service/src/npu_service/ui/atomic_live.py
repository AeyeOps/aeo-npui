"""Rich Live wrapper with synchronized terminal updates."""

from __future__ import annotations

from rich.live import Live

SYNC_UPDATE_BEGIN = "\x1b[?2026h"
SYNC_UPDATE_END = "\x1b[?2026l"


class AtomicLive(Live):
    """Emit synchronized update markers around every refresh when supported."""

    def refresh(self) -> None:
        output = self.console.file
        try:
            output.write(SYNC_UPDATE_BEGIN)
            output.flush()
        except Exception:
            pass
        try:
            super().refresh()
        finally:
            try:
                output.write(SYNC_UPDATE_END)
                output.flush()
            except Exception:
                pass
