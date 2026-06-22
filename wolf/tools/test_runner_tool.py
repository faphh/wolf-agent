"""Test runner tool — Auto-detect and run tests for the project.

Supports: pytest, unittest, jest, vitest, go test, cargo test.
"""

import os
import subprocess
import logging
from typing import Any, Dict, List, Optional
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def _detect_test_framework(cwd: str) -> tuple:
    """Detect test framework and command."""
    # Python
    if os.path.exists(os.path.join(cwd, "pyproject.toml")):
        with open(os.path.join(cwd, "pyproject.toml")) as f:
            content = f.read()
            if "pytest" in content:
                return "pytest", ["python", "-m", "pytest", "-x", "-v", "--tb=short"]
    if os.path.exists(os.path.join(cwd, "setup.py")):
        return "pytest", ["python", "-m", "pytest", "-x", "-v", "--tb=short"]

    # JavaScript/TypeScript
    if os.path.exists(os.path.join(cwd, "package.json")):
        import json
        with open(os.path.join(cwd, "package.json")) as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        if "test" in scripts:
            if "vitest" in scripts.get("test", ""):
                return "vitest", ["npx", "vitest", "run"]
            if "jest" in scripts.get("test", ""):
                return "jest", ["npx", "jest", "--no-coverage"]
            return "npm test", ["npm", "test", "--silent"]

    # Go
    if os.path.exists(os.path.join(cwd, "go.mod")):
        return "go test", ["go", "test", "-v", "./..."]

    # Rust
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return "cargo test", ["cargo", "test"]

    # Java (Maven/Gradle)
    if os.path.exists(os.path.join(cwd, "pom.xml")):
        return "maven", ["mvn", "test", "-q"]
    if os.path.exists(os.path.join(cwd, "build.gradle")):
        return "gradle", ["./gradlew", "test"]

    return "unknown", []


def test_runner_handler(args: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Run tests for the project."""
    cwd = args.get("cwd", ".")
    framework = args.get("framework", "auto")
    pattern = args.get("pattern", "")  # Specific test file/pattern
    timeout = args.get("timeout", 120)

    if framework == "auto":
        framework, cmd = _detect_test_framework(cwd)
        if not cmd:
            return {"error": "Could not detect test framework. Specify with framework parameter."}
    else:
        cmd_map = {
            "pytest": ["python", "-m", "pytest", "-x", "-v", "--tb=short"],
            "jest": ["npx", "jest", "--no-coverage"],
            "vitest": ["npx", "vitest", "run"],
            "go test": ["go", "test", "-v", "./..."],
            "cargo test": ["cargo", "test"],
        }
        cmd = cmd_map.get(framework, [])
        if not cmd:
            return {"error": f"Unknown framework: {framework}"}

    if pattern:
        cmd.append(pattern)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
            env={**os.environ, "FORCE_COLOR": "0", "NO_COLOR": "1"},
        )

        output = result.stdout + result.stderr
        if len(output) > 15000:
            output = output[:10000] + f"\n... [truncated, {len(output)} chars]"

        # Parse results
        passed = result.returncode == 0
        failed_count = 0
        passed_count = 0

        # Try to extract counts from pytest output
        for line in output.split("\n"):
            if "passed" in line and "failed" in line:
                import re
                m = re.search(r"(\d+) passed", line)
                if m:
                    passed_count = int(m.group(1))
                m = re.search(r"(\d+) failed", line)
                if m:
                    failed_count = int(m.group(1))

        return {
            "framework": framework,
            "passed": passed,
            "output": output,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Tests timed out after {timeout}s", "framework": framework}
    except FileNotFoundError:
        return {"error": f"Test runner not found. Is {framework} installed?"}
    except Exception as e:
        return {"error": str(e)}


registry.register(
    name="run_tests", toolset="coding",
    schema={
        "description": "Auto-detect and run project tests. Supports pytest, jest, vitest, go test, cargo test, maven, gradle.",
        "parameters": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Project directory (default: cwd)"},
                "framework": {"type": "string", "description": "Force framework (auto/pytest/jest/vitest/go test/cargo test)"},
                "pattern": {"type": "string", "description": "Specific test file or pattern"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 120)"},
            },
        },
    },
    handler=test_runner_handler, emoji="🧪",
)

