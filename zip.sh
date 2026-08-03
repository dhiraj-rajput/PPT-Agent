#!/bin/bash
# ============================================================
# zip.sh — Clean deployment zip generator for cPanel upload
# ============================================================
# Zips the target directory. With NO arguments, zips the ENTIRE
# project root (backend + Frontend + docs + everything else next
# to this script) while excluding all server/dev trash: caches,
# venvs, secrets, logs, node_modules, frontend build trash
# (dist, .vite, etc.), and previously generated zips.
#
# The output zip is named after the folder being zipped, e.g.:
#   ./zip.sh            -> PPT-Agent-20260803-120000.zip
#   ./zip.sh ./backend  -> backend-20260803-120000.zip
#
# Usage:
#   ./zip.sh                          # zip the WHOLE project (backend + Frontend + docs)
#   ./zip.sh ./backend                # zip only backend -> backend-<timestamp>.zip
#   ./zip.sh /path/to/project         # explicit project path
#   ./zip.sh /path/to/project output.zip   # explicit output name/path
#
# Pass --include-env to include example/production env templates
# (live .env itself is always excluded).
# ============================================================

set -euo pipefail

# Directory this script lives in — used as the default (whole-project) target
# so a blank run always zips backend + Frontend + docs together, regardless
# of the directory it's invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INCLUDE_ENV=false
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --include-env)
            INCLUDE_ENV=true
            ;;
        *)
            POSITIONAL+=("$arg")
            ;;
    esac
done
set -- "${POSITIONAL[@]:-}"

SRC_DIR="${1:-$SCRIPT_DIR}"

if [ ! -d "$SRC_DIR" ]; then
    echo "Error: Directory not found at '$SRC_DIR'" >&2
    echo "Run this from your repo root, or pass the path explicitly:" >&2
    echo "  ./zip.sh ./" >&2
    exit 1
fi

command -v zip >/dev/null 2>&1 || { echo "Error: 'zip' is not installed." >&2; exit 1; }

SRC_DIR="$(cd "$SRC_DIR" && pwd)"
PARENT_DIR="$(dirname "$SRC_DIR")"
BASE_NAME="$(basename "$SRC_DIR")"

# Output zip is named after the folder being zipped (e.g. "backend" -> backend-<timestamp>.zip,
# whole project "PPT-Agent" -> PPT-Agent-<timestamp>.zip), dropped next to this script.
OUT_ZIP="${2:-$SCRIPT_DIR/${BASE_NAME}-$(date +%Y%m%d-%H%M%S).zip}"
OUT_ZIP="$(cd "$(dirname "$OUT_ZIP")" && pwd)/$(basename "$OUT_ZIP")"

echo "Source:  $SRC_DIR"
echo "Output:  $OUT_ZIP"
echo ""

# ------------------------------------------------------------
# Exclusion patterns
# ------------------------------------------------------------

EXCLUDES=(
    # Python bytecode / caches
    "$BASE_NAME/*/__pycache__/*"
    "$BASE_NAME/__pycache__/*"
    "*/__pycache__/*"
    "__pycache__/*"
    "*.pyc"
    "*.pyo"
    "*/.pytest_cache/*"
    "*/.mypy_cache/*"
    "*.egg-info/*"

    # Virtual environments
    "$BASE_NAME/.venv/*"
    "$BASE_NAME/venv/*"
    "$BASE_NAME/env/*"
    "$BASE_NAME/ENV/*"
    "*/.venv/*"
    "*/venv/*"
    "*/env/*"

    # Frontend / Node trash & build artifacts
    "$BASE_NAME/node_modules/*"
    "$BASE_NAME/*/node_modules/*"
    "*/node_modules/*"
    "node_modules/*"

    "$BASE_NAME/dist/*"
    "$BASE_NAME/*/dist/*"
    "*/dist/*"
    "dist/*"

    "$BASE_NAME/build/*"
    "$BASE_NAME/*/build/*"
    "*/build/*"

    "$BASE_NAME/.vite/*"
    "$BASE_NAME/*/.vite/*"
    "*/.vite/*"

    "$BASE_NAME/.cache/*"
    "$BASE_NAME/*/.cache/*"
    "*/.cache/*"

    "$BASE_NAME/coverage/*"
    "$BASE_NAME/*/coverage/*"

    "$BASE_NAME/npm-debug.log*"
    "$BASE_NAME/yarn-debug.log*"
    "$BASE_NAME/yarn-error.log*"
    "$BASE_NAME/.eslintcache"
    "*.log"
    "*/*.log"

    # Version control / editor / OS junk
    "$BASE_NAME/.git/*"
    "*/.git/*"
    ".git/*"
    "$BASE_NAME/.idea/*"
    "*/.idea/*"
    "$BASE_NAME/.vscode/*"
    "*/.vscode/*"
    "*.DS_Store"
    "*DS_Store"
    "*Thumbs.db"

    # Runtime-generated data / secrets
    "$BASE_NAME/logs/*"
    "*/logs/*"
    "$BASE_NAME/output/*"
    "*/output/*"
    "$BASE_NAME/private/*"
    "*/private/*"
    "$BASE_NAME/downloads/*"
    "*/downloads/*"

    # Secrets
    "$BASE_NAME/.env"
    "*/.env"
    ".env"

    # Previously generated zips (never zip the zips)
    "*.zip"
)

if [ "$INCLUDE_ENV" = false ]; then
    EXCLUDES+=(
        "$BASE_NAME/.env.production"
        "$BASE_NAME/.env.localhost"
        "$BASE_NAME/.env.example"
        "*/.env.production"
        "*/.env.localhost"
        "*/.env.example"
    )
fi

rm -f "$OUT_ZIP"

cd "$PARENT_DIR"
zip -r -q "$OUT_ZIP" "$BASE_NAME" -x "${EXCLUDES[@]}"

echo "Done."
echo ""
echo "Zip contents summary:"
unzip -l "$OUT_ZIP" | tail -1
echo ""
echo "Size:"
du -h "$OUT_ZIP"
echo ""
echo "Sanity check — confirming nothing unwanted got in:"
BAD=$(unzip -l "$OUT_ZIP" | grep -E "__pycache__|\.pyc$|/\.env$|/logs/|/output/|/private/|/downloads/|\.git/|node_modules/|/dist/|/\.vite/" || true)
if [ -n "$BAD" ]; then
    echo "WARNING: found unexpected files in the zip:"
    echo "$BAD"
else
    echo "Clean — no caches, envs, logs, node_modules, dist, or venvs included."
fi