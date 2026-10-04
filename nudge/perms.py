"""Keep nudge's private files private.

config.toml holds the Telegram bot token and the Anthropic key; state.db holds
event titles and pending proposals. config.example.toml says `chmod 600`, but
nothing enforced it, and the usual way a file loses it is being copied onto a
new machine, which is exactly when nobody is looking.

token.json is covered separately: gcal._save chmods it on every write.

This tightens rather than refuses. A config readable by other accounts is worth
a log line and a fix; it is not worth missing a reminder over.
"""

from __future__ import annotations

import logging
import stat
from pathlib import Path

log = logging.getLogger("nudge")


def keep_private(path: Path | str) -> None:
    """chmod 600 `path` if group or others can read or write it. Never raises."""
    path = Path(path)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return  # missing, or ":memory:" -- nothing to protect
    if not mode & 0o077:
        return
    try:
        path.chmod(0o600)
    except OSError as e:
        log.warning("%s is readable by other users (%o) and could not be tightened: %s",
                    path, mode, e)
        return
    log.warning("%s was readable by other users (%o); tightened to 600", path, mode)
