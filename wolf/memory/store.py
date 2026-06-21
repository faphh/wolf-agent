"""Memory Store — Persistent memory management."""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_DIR = Path.home() / ".wolf" / "memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
USER_FILE = MEMORY_DIR / "USER.md"


def read_memory(target: str = "memory") -> str:
    fpath = USER_FILE if target == "user" else MEMORY_FILE
    if fpath.exists():
        return fpath.read_text(encoding="utf-8")
    return ""


def append_memory(content: str, target: str = "memory") -> bool:
    fpath = USER_FILE if target == "user" else MEMORY_FILE
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    existing = fpath.read_text(encoding="utf-8") if fpath.exists() else ""
    fpath.write_text(existing.rstrip() + "\n- " + content.strip() + "\n", encoding="utf-8")
    return True


def replace_memory(old_text: str, new_text: str, target: str = "memory") -> bool:
    fpath = USER_FILE if target == "user" else MEMORY_FILE
    if not fpath.exists():
        return False
    content = fpath.read_text(encoding="utf-8")
    if old_text not in content:
        return False
    fpath.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return True
