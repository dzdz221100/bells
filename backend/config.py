"""Central configuration for the Bells backend.

Responsibilities:
  * locate and load .env files (repo root AND one folder above the repo root)
  * expose the model name the course key is allowed to use
  * build the PydanticAI model object
  * fail loudly and readably when no API key is present

Nothing in this module ever prints or logs the key itself.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

# backend/config.py -> backend/ -> repo root (bells/)
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
PARENT_OF_REPO = REPO_ROOT.parent

DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "bells.db"
SCHEMA_PATH = DATA_DIR / "schema.sql"

# The two places we look for a .env, in load order.
# Graders clone this repo into a folder where their .env sits one level above it,
# so BOTH must work. The repo-root one is loaded last so it wins on conflict.
ENV_SEARCH_PATHS: tuple[Path, ...] = (
    PARENT_OF_REPO / ".env",  # one folder ABOVE the repo root
    REPO_ROOT / ".env",       # the repo root itself (wins on conflict)
)

# Only gpt-6-luna is available on the course key; override locally if needed.
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-6-luna")

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

_loaded = False


def load_env(*, force: bool = False) -> list[Path]:
    """Load .env from the repo root and from one folder above the repo root.

    Both files are loaded if both exist. The repo-root file is loaded last with
    ``override=True`` so its values win on conflict.

    Returns the list of .env paths that were actually found and loaded.
    """
    global _loaded, MODEL_NAME

    if _loaded and not force:
        return [p for p in ENV_SEARCH_PATHS if p.is_file()]

    found: list[Path] = []
    for path in ENV_SEARCH_PATHS:
        if path.is_file():
            load_dotenv(path, override=True)
            found.append(path)

    # Re-read the model name now that the env files are in os.environ.
    MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    _loaded = True
    return found


def get_api_key() -> str | None:
    """Return the Portkey/OpenAI key, or None if neither is set."""
    load_env()
    key = os.getenv("PORTKEY_API_KEY") or os.getenv("OPENAI_API_KEY")
    return key.strip() if key and key.strip() else None


def require_api_key() -> str:
    """Return the API key, or raise a clear error naming both search locations."""
    key = get_api_key()
    if key:
        return key

    looked = "\n".join(f"    {i}. {p}" for i, p in enumerate(ENV_SEARCH_PATHS, 1))
    raise RuntimeError(
        "No API key found.\n\n"
        "Bells needs PORTKEY_API_KEY (preferred) or OPENAI_API_KEY.\n"
        "It looked for a .env file in these two places:\n"
        f"{looked}\n\n"
        "Fix: copy .env.example to .env in either location and fill in the key,\n"
        "or export PORTKEY_API_KEY in your shell before starting the server.\n"
        "(The key value is never printed or logged.)"
    )


def build_model() -> OpenAIResponsesModel:
    """Build the PydanticAI model, routed through Portkey."""
    api_key = require_api_key()
    provider = OpenAIProvider(base_url=PORTKEY_BASE_URL, api_key=api_key)
    return OpenAIResponsesModel(MODEL_NAME, provider=provider)


def env_status() -> dict[str, object]:
    """Non-secret diagnostic summary, safe to log or return from a health route."""
    load_env()
    return {
        "model": MODEL_NAME,
        "base_url": PORTKEY_BASE_URL,
        "env_files_found": [str(p) for p in ENV_SEARCH_PATHS if p.is_file()],
        "env_files_searched": [str(p) for p in ENV_SEARCH_PATHS],
        "api_key_present": get_api_key() is not None,
    }
