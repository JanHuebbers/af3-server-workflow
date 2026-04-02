#!/usr/bin/env python3
"""
perm_helper.py — small utilities to check and fix output file permissions.

Usage in other scripts:
    from perm_helper import ensure_writable, set_owner_and_perms, sweep_fix_outputs
"""

import os, getpass, stat
from pathlib import Path
from contextlib import suppress

def _current_user_ids():
    """Return (username, uid, gid) for the current user (POSIX only)."""
    user = getpass.getuser()
    try:
        import pwd, grp
        uid = pwd.getpwnam(user).pw_uid
        gid = pwd.getpwnam(user).pw_gid
        return user, uid, gid
    except Exception:
        return user, None, None  # Windows / non-POSIX

def ensure_writable(path: str) -> None:
    """
    Check if a file exists but isn't writable by current user.
    Print a friendly message suggesting 'sudo chown' and 'chmod'.
    """
    p = Path(path)
    if p.exists() and not os.access(p, os.W_OK):
        owner = None
        with suppress(Exception):
            import pwd, grp
            st = p.stat()
            owner = f"{pwd.getpwuid(st.st_uid).pw_name}:{grp.getgrgid(st.st_gid).gr_name}"
        print(f"[warn] {p} exists but is not writable by '{getpass.getuser()}'"
              + (f" (owner: {owner})" if owner else "") + ".")
        print(f"       To fix: sudo chown {getpass.getuser()}:{getpass.getuser()} '{p}'; chmod u+rw '{p}'")

def set_owner_and_perms(path: str | Path, mode: int = 0o664) -> None:
    """
    Force file to be writable by current user.
    If run as root, also chown to current user.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return
    user, uid, gid = _current_user_ids()
    with suppress(Exception):
        os.chmod(p, mode)
    with suppress(Exception):
        if uid is not None:
            st = p.stat()
            if (st.st_uid != uid or st.st_gid != gid) and (os.geteuid() == 0 or os.getuid() == 0):
                os.chown(str(p), uid, gid)

def sweep_fix_outputs(base: str | Path, patterns: list[str] | None = None) -> None:
    """
    Recursively walk under base and fix ownership/permissions for files matching patterns.
    Default patterns cover common AF3 outputs.
    """
    base = Path(base)
    if patterns is None:
        patterns = [
            "per_residue_metrics.xlsx",
            "per_residue_metrics*.xlsx",
            "model_confidences.csv",
            "*.png", "*.pdf",
        ]
    for pat in patterns:
        for f in base.rglob(pat):
            set_owner_and_perms(f)
