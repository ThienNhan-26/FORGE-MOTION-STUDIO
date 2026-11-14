#!/usr/bin/env python3
"""FORGE Phase 1 Reviewer Integration — Test Runner Helper.

Usage (Windows PowerShell):
    python run_tests.py --batch 1       # Parser + Trailing Garbage
    python run_tests.py --batch 2       # Guards + Boundaries
    python run_tests.py --batch 3       # Repair Loop
    python run_tests.py --batch model   # Model Evaluation (needs Ollama)
    python run_tests.py --all           # All deterministic batches (1+2+3)
    python run_tests.py --all --model   # Everything including model eval

Environment requirements:
    - FORGE project root must be resolvable (auto-detected or via --project-root)
    - Dependencies installed: pip install -r requirements-dev.txt
    - Batch model requires Ollama running at OLLAMA_BASE_URL

This script does NOT modify .env, config, or security settings.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import json
import urllib.request
from pathlib import Path


def resolve_project_root(explicit: str | None) -> Path:
    """Resolve FORGE project root directory."""
    if explicit:
        root = Path(explicit).resolve()
        if not (root / "config.py").exists():
            print(f"ERROR: {root} does not contain config.py", file=sys.stderr)
            sys.exit(1)
        return root

    # Auto-detect: walk up from this script's location
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "config.py").exists() and (current / "agents").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    print(
        "ERROR: Could not auto-detect FORGE project root.\n"
        "Use --project-root to specify explicitly.",
        file=sys.stderr,
    )
    sys.exit(1)


def check_dependencies() -> list[str]:
    """Check required packages are importable."""
    missing = []
    for pkg in ["pytest", "pydantic"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def check_security_policy(project_root: Path) -> bool:
    """Check FORGE_ALLOW_UNSANDBOXED_PYTHON in process environment and .env.

    Returns True if safe to proceed, False if blocked.
    Policy: Fail-closed. Only allow if explicitly set to 'false' in both sources.
    """
    ALLOWED_VALUES = {"false", "0", "no", "off"}
    BLOCKED_VALUES = {"true", "1", "yes", "on"}

    # 1. Check Process Environment
    proc_val = os.environ.get("FORGE_ALLOW_UNSANDBOXED_PYTHON")

    # 2. Check .env file (Read-only)
    env_file = project_root / ".env"
    file_val = None
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("FORGE_ALLOW_UNSANDBOXED_PYTHON="):
                file_val = line.split("=", 1)[1].strip().strip("'\"")
                break

    # Validation Logic
    def is_blocked(val: str | None) -> bool:
        if val is None:
            return True # Not set -> BLOCK
        if val.lower() in BLOCKED_VALUES:
            return True # Explicitly true -> BLOCK
        if val.lower() not in ALLOWED_VALUES:
            return True # Invalid value -> BLOCK
        return False # Explicitly false -> ALLOW

    proc_blocked = is_blocked(proc_val)
    file_blocked = is_blocked(file_val) if file_val is not None else False

    if proc_blocked:
        print(
            f"\n❌ BLOCKED: Process environment FORGE_ALLOW_UNSANDBOXED_PYTHON is '{proc_val}'.",
            file=sys.stderr,
        )
        print("Security policy requires this to be explicitly set to 'false'.", file=sys.stderr)
        return False

    if file_val is not None and file_blocked:
        print(
            f"\n❌ BLOCKED: .env file FORGE_ALLOW_UNSANDBOXED_PYTHON is '{file_val}'.",
            file=sys.stderr,
        )
        print("Security policy requires consistency. Please fix your .env file.", file=sys.stderr)
        return False

    # If .env exists but doesn't have the key, we warn but don't block if proc is OK
    # If .env is missing entirely, we rely on proc env.

    return True


def check_ollama_connection(base_url: str) -> bool:
    """Quick check if Ollama is reachable."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return "models" in payload
    except Exception:
        return False


BATCH_MAP = {
    "1": "tests/phase1_reviewer/test_parser.py",
    "2": "tests/phase1_reviewer/test_guards.py",
    "3": "tests/phase1_reviewer/test_repair_loop.py",
    "model": "tests/phase1_reviewer/test_model_evaluation.py",
}


def run_batch(batch_id: str, project_root: Path, extra_args: list[str]) -> tuple[int, str]:
    """Run a single test batch. Returns (exit_code, status_label)."""
    test_path = BATCH_MAP.get(batch_id)
    if not test_path:
        return 1, "INVALID"

    full_path = project_root / test_path
    if not full_path.exists():
        return 1, "MISSING_FILE"

    cmd = [
        sys.executable, "-m", "pytest",
        str(full_path),
        "-v", "--tb=short",
    ]

    if batch_id == "model":
        cmd.extend(["-m", "model_eval"])
    else:
        cmd.extend(["-m", "not model_eval"])

    cmd.extend(extra_args)

    print(f"\n{'='*60}")
    print(f"BATCH {batch_id}: {test_path}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd, cwd=str(project_root))
    return result.returncode, "PASS" if result.returncode == 0 else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FORGE Phase 1 Reviewer Integration Test Runner"
    )
    parser.add_argument(
        "--batch",
        choices=list(BATCH_MAP.keys()),
        help="Run a specific batch (1, 2, 3, model)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all deterministic batches (1+2+3)",
    )
    parser.add_argument(
        "--model",
        action="store_true",
        help="Include model evaluation batch (requires Ollama)",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Explicit path to FORGE project root",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check environment and dependencies, do not run tests",
    )
    args, extra = parser.parse_known_args()

    # Resolve project root
    project_root = resolve_project_root(args.project_root)
    print(f"Project root: {project_root}")

    # Add project root to sys.path for imports
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Check dependencies
    missing = check_dependencies()
    if missing:
        print(f"ERROR: Missing dependencies: {missing}", file=sys.stderr)
        print(f"Install with: pip install -r {project_root / 'requirements-dev.txt'}", file=sys.stderr)
        return 1
    print("Dependencies: OK")

    # Security Policy Check (Fail-closed)
    if not check_security_policy(project_root):
        return 2 # Exit code 2 = BLOCKED

    if args.check_only:
        print("\nCheck-only mode. No tests executed.")
        return 0

    # Determine which batches to run
    batches_to_run: list[str] = []
    if args.batch:
        batches_to_run.append(args.batch)
    elif args.all:
        batches_to_run.extend(["1", "2", "3"])
        if args.model:
            batches_to_run.append("model")
    else:
        parser.print_help()
        print("\nSpecify --batch, --all, or --check-only.")
        return 1

    # Run batches sequentially
    results: dict[str, tuple[int, str]] = {}
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    has_skipped = False

    for batch_id in batches_to_run:
        if batch_id == "model":
            if not check_ollama_connection(ollama_url):
                print(f"\n⚠️ SKIPPED: Batch {batch_id} (Ollama not reachable at {ollama_url})")
                results[batch_id] = (-1, "SKIPPED")
                has_skipped = True
                continue

        exit_code, status = run_batch(batch_id, project_root, extra)
        results[batch_id] = (exit_code, status)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    all_passed = True
    for batch_id, (code, status) in results.items():
        if status == "SKIPPED":
            print(f"  Batch {batch_id}: {status}")
        elif code == 0:
            print(f"  Batch {batch_id}: {status}")
        else:
            all_passed = False
            print(f"  Batch {batch_id}: {status} (exit code {code})")

    if has_skipped:
        return 3 # Exit code 3 = INCOMPLETE/SKIPPED
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())