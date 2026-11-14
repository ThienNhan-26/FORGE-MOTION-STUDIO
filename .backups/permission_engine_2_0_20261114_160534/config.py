
"""Central configuration for FORGE. All paths are anchored to this project."""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()

        if value.startswith(("'", '"')) and value.endswith(("'", '"')):
            value = value[1:-1]

        os.environ.setdefault(key, value)


_load_dotenv(ROOT_DIR / ".env")


# ============================================================
# FORGE DIRECTORIES
# ============================================================

WORKSPACE_DIR = Path(
    os.getenv("FORGE_WORKSPACE_DIR", str(ROOT_DIR / "workspace"))
).expanduser().resolve()

STORAGE_DIR = Path(
    os.getenv("FORGE_STORAGE_DIR", str(ROOT_DIR / "storage"))
).expanduser().resolve()

DB_PATH = Path(
    os.getenv("FORGE_DB_PATH", str(STORAGE_DIR / "forge.db"))
).expanduser().resolve()

SKILLS_DIR = Path(
    os.getenv("FORGE_SKILLS_DIR", str(ROOT_DIR / "skills"))
).expanduser().resolve()

REMOTION_TEMPLATE_DIR = Path(
    os.getenv(
        "FORGE_REMOTION_DIR",
        str(ROOT_DIR / "adapters" / "remotion_template")
    )
).expanduser().resolve()

BLENDER_EXECUTABLE = os.getenv("FORGE_BLENDER_EXECUTABLE", "")


# ============================================================
# OLLAMA CONNECTION
# ============================================================

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
).rstrip("/")

OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))


# ============================================================
# FOUR-MODEL TEAM
# ============================================================

# 1. Director / Planner
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma4-e4b-local:latest"
)

# 2. Main Engineer / Coder
OLLAMA_CODER_MODEL = os.getenv(
    "OLLAMA_CODER_MODEL",
    "Qwen3-Coder-30B-A3B:latest"
)

# 3. Independent Reviewer
OLLAMA_REVIEWER_MODEL = os.getenv(
    "OLLAMA_REVIEWER_MODEL",
    "gpt-oss-20b-mxfp4:latest"
)

# 4. 3D Specialist
OLLAMA_3D_MODEL = os.getenv(
    "OLLAMA_3D_MODEL",
    "qwen3d-coder:latest"
)


# ============================================================
# FORGE EXECUTION SETTINGS
# ============================================================

FORGE_MAX_WORKERS = max(
    1,
    int(os.getenv("FORGE_MAX_WORKERS", "2"))
)

FORGE_MAX_ACTIVE_MISSIONS = max(
    1,
    int(os.getenv("FORGE_MAX_ACTIVE_MISSIONS", "1"))
)

FORGE_MAX_REPAIR_ROUNDS = max(
    0,
    int(os.getenv("FORGE_MAX_REPAIR_ROUNDS", "2"))
)

# Maximum number of Coder correction rounds triggered by independent review.
# The first review always runs; this setting controls additional correction attempts.
FORGE_MAX_REVIEW_ROUNDS = max(
    0,
    int(os.getenv("FORGE_MAX_REVIEW_ROUNDS", "1"))
)

FORGE_ENABLE_PYTHON_EXECUTION = (
    os.getenv("FORGE_ENABLE_PYTHON_EXECUTION", "false").lower()
    in {"1", "true", "yes", "on"}
)
