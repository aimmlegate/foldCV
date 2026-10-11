"""Signal owned, unreaped process groups and recognize macOS vanished groups."""

import os
import subprocess


def signal_group(group_id: int, sig: int) -> bool:
    try:
        os.killpg(group_id, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # macOS reports EPERM when an unreaped leader's last live group member exits.
        try:
            inventory = subprocess.run(["/bin/ps", "-axo", "pgid=,stat="], capture_output=True, timeout=1,
                                       env={"PATH": os.defpath, "LC_ALL": "C"}, check=True)
            rows = [row.split() for row in inventory.stdout.splitlines()]
            if (len(inventory.stdout) > 512_000 or not rows or
                    any(len(row) != 2 or not row[0].isdigit() for row in rows)):
                raise ValueError("invalid process inventory")
        except (OSError, ValueError, subprocess.SubprocessError):
            raise OSError("Process group inspection failed") from None
        if group_id in {int(group) for group, state in rows if not state.startswith(b"Z")}:
            raise
        return False
