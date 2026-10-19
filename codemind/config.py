"""Central limits and settings. Values match SECURITY_PLAN.md."""

from __future__ import annotations

from pathlib import Path

# --- ingestion limits -------------------------------------------------------
MAX_ZIP_BYTES = 20 * 1024 * 1024            # compressed archive size
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # total after extraction
MAX_FILE_BYTES = 2 * 1024 * 1024            # any single file
MAX_FILES = 2000                            # archive entries
MAX_COMPRESSION_RATIO = 100                 # per entry, zip-bomb heuristic

IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "node_modules",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    ".idea", ".vscode", ".eggs", "site-packages", "__MACOSX",
})
SENSITIVE_NAME_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_dsa*", "id_ed25519*",
    "*.p12", "*.pfx", "credentials*.json", "*.keystore", ".netrc", ".pypirc",
)

LANGUAGE_BY_EXT = {
    ".py": "Python", ".md": "Markdown", ".txt": "Text", ".toml": "TOML",
    ".cfg": "Config", ".ini": "Config", ".json": "JSON", ".yml": "YAML",
    ".yaml": "YAML", ".csv": "CSV", ".js": "JavaScript", ".ts": "TypeScript",
    ".html": "HTML", ".css": "CSS", ".java": "Java", ".c": "C", ".cpp": "C++",
    ".sql": "SQL", ".sh": "Shell", ".ipynb": "Jupyter Notebook",
}

# --- workflow ---------------------------------------------------------------
MAX_RETRIES = 2            # failed validations that may be retried with a new strategy
TEST_TIMEOUT_S = 60        # wall clock for one sandboxed pytest run
SYNTAX_TIMEOUT_S = 20

# --- paths ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PROJECT_ROOT / "samples"
SAMPLE_REPO_DIR = SAMPLES_DIR / "student_grades_app"
DEFAULT_WORKSPACE = PROJECT_ROOT / "workspace"
DEFAULT_REPORTS = PROJECT_ROOT / "reports"

# --- optional LLM -----------------------------------------------------------
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"
OLLAMA_TIMEOUT_S = 30
