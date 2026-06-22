"""Session persistence — save and resume conversations.

Sessions are stored in ~/.wolf/sessions/ as JSON files.
"""

import json
import os
import time
import logging
from pathlib import Path
from dataclasses import asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path.home() / ".wolf" / "sessions"


def save_session(session_id: str, messages: list, metadata: Dict[str, Any] = None) -> str:
    """Save a conversation session to disk.

    Args:
        session_id: Unique session identifier
        messages: List of Message objects
        metadata: Optional metadata (agent, model, etc.)

    Returns:
        Path to the saved session file
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Convert Message objects to dicts
    msg_dicts = []
    for msg in messages:
        if hasattr(msg, '__dict__'):
            d = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                d["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                d["tool_call_id"] = msg.tool_call_id
            if msg.name:
                d["name"] = msg.name
            msg_dicts.append(d)
        elif isinstance(msg, dict):
            msg_dicts.append(msg)

    session_data = {
        "session_id": session_id,
        "timestamp": time.time(),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "message_count": len(msg_dicts),
        "metadata": metadata or {},
        "messages": msg_dicts,
    }

    filepath = SESSIONS_DIR / f"{session_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Session saved: {filepath}")
    return str(filepath)


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Load a session from disk.

    Returns:
        Session data dict or None if not found
    """
    filepath = SESSIONS_DIR / f"{session_id}.json"
    if not filepath.exists():
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load session {session_id}: {e}")
        return None


def list_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    """List recent sessions.

    Returns:
        List of session summaries (without full messages)
    """
    if not SESSIONS_DIR.exists():
        return []

    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            sessions.append({
                "session_id": data.get("session_id", f.stem),
                "created_at": data.get("created_at", ""),
                "message_count": data.get("message_count", 0),
                "metadata": data.get("metadata", {}),
                "file": str(f),
            })
        except Exception:
            continue

    return sessions[:limit]


def delete_session(session_id: str) -> bool:
    """Delete a session file."""
    filepath = SESSIONS_DIR / f"{session_id}.json"
    if filepath.exists():
        filepath.unlink()
        return True
    return False


def get_latest_session() -> Optional[Dict[str, Any]]:
    """Get the most recent session."""
    sessions = list_sessions(limit=1)
    if sessions:
        return load_session(sessions[0]["session_id"])
    return None
