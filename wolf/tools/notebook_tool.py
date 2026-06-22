"""Notebook tools — Read and edit Jupyter .ipynb files."""

import json
import os
import logging
from typing import Any, Dict, List, Optional
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def _load_notebook(path: str) -> Dict[str, Any]:
    """Load a Jupyter notebook."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_notebook(path: str, nb: Dict[str, Any]):
    """Save a Jupyter notebook."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)


def notebook_read_handler(args: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Read cells from a Jupyter notebook."""
    path = args.get("path", "")
    cell_range = args.get("cells", "")  # "1,5" or "3" or "" for all

    if not path or not os.path.exists(path):
        return {"error": f"Notebook not found: {path}"}

    try:
        nb = _load_notebook(path)
        cells = nb.get("cells", [])
        total = len(cells)

        if cell_range:
            parts = cell_range.split(",")
            start = max(0, int(parts[0]) - 1)
            end = min(total, int(parts[1])) if len(parts) > 1 else start + 1
        else:
            start, end = 0, total

        result = []
        for i in range(start, end):
            cell = cells[i]
            cell_type = cell.get("cell_type", "code")
            source = "".join(cell.get("source", []))
            outputs = []
            if cell_type == "code":
                for out in cell.get("outputs", []):
                    if out.get("output_type") == "stream":
                        outputs.append("".join(out.get("text", [])))
                    elif out.get("output_type") in ("execute_result", "display_data"):
                        for key in ("text/plain", "text/html"):
                            if key in out.get("data", {}):
                                outputs.append("".join(out["data"][key]))
                    elif out.get("output_type") == "error":
                        outputs.append("\n".join(out.get("traceback", [])))

            result.append({
                "index": i + 1,
                "type": cell_type,
                "source": source,
                "outputs": outputs[:3],  # Limit outputs
            })

        return {"cells": result, "total_cells": total, "path": path}
    except Exception as e:
        return {"error": str(e)}


def notebook_edit_handler(args: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Edit a cell in a Jupyter notebook."""
    path = args.get("path", "")
    cell_index = args.get("cell", 0)  # 1-indexed
    new_source = args.get("source", "")
    cell_type = args.get("cell_type", "")  # If set, change cell type

    if not path or not os.path.exists(path):
        return {"error": f"Notebook not found: {path}"}

    try:
        nb = _load_notebook(path)
        cells = nb.get("cells", [])
        idx = cell_index - 1

        if idx < 0 or idx >= len(cells):
            return {"error": f"Cell {cell_index} out of range (1-{len(cells)})"}

        if new_source:
            cells[idx]["source"] = new_source.split("\n")
            # Add newlines to all but last line
            cells[idx]["source"] = [line + "\n" for line in cells[idx]["source"][:-1]] + [cells[idx]["source"][-1]]

        if cell_type:
            cells[idx]["cell_type"] = cell_type

        # Clear outputs on edit
        if new_source and cells[idx].get("cell_type") == "code":
            cells[idx]["outputs"] = []

        _save_notebook(path, nb)
        return {"success": True, "cell": cell_index, "path": path}
    except Exception as e:
        return {"error": str(e)}


def notebook_create_handler(args: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Create a new Jupyter notebook."""
    path = args.get("path", "")
    kernel = args.get("kernel", "python3")

    if not path:
        return {"error": "path required"}

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": kernel},
            "language_info": {"name": "python", "version": "3.12.0"},
        },
        "cells": [{
            "cell_type": "code",
            "metadata": {},
            "source": ["# New notebook\n"],
            "outputs": [],
            "execution_count": None,
        }],
    }

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _save_notebook(path, nb)
    return {"success": True, "path": path, "cells": 1}


# Register
registry.register(
    name="notebook_read", toolset="file",
    schema={
        "description": "Read cells from a Jupyter notebook (.ipynb). Returns cell source and outputs.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Notebook path"},
                "cells": {"type": "string", "description": "Cell range (e.g., '1,5' or '3'). Empty for all."},
            },
            "required": ["path"],
        },
    },
    handler=notebook_read_handler, emoji="📓",
)

registry.register(
    name="notebook_edit", toolset="file",
    schema={
        "description": "Edit a cell in a Jupyter notebook. Clears outputs on edit.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Notebook path"},
                "cell": {"type": "integer", "description": "Cell index (1-indexed)"},
                "source": {"type": "string", "description": "New cell source code"},
                "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "Change cell type"},
            },
            "required": ["path", "cell"],
        },
    },
    handler=notebook_edit_handler, emoji="📓",
)

registry.register(
    name="notebook_create", toolset="file",
    schema={
        "description": "Create a new Jupyter notebook.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Notebook path"},
                "kernel": {"type": "string", "description": "Kernel name (default: python3)", "default": "python3"},
            },
            "required": ["path"],
        },
    },
    handler=notebook_create_handler, emoji="📓",
)

