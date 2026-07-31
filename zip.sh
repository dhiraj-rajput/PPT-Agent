#!/bin/bash
# ============================================================
# make_backend_zip.sh — Clean backend zip for cPanel upload
# ============================================================
# Zips PPT-Agent/backend/ while excluding everything that
# shouldn't go to the server: caches, venvs, secrets, logs,
# and runtime-generated files.
#
# Usage:
#   ./make_backend_zip.sh                     # run from repo root, uses ./backend
#   ./make_backend_zip.sh /path/to/backend     # explicit backend path
#   ./make_backend_zip.sh /path/to/backend /path/to/output.zip
#
# By default, ALL .env* files are excluded — this is intentional.
# You don't want a fresh zip silently overwriting the carefully
# configured .env already sitting on the server. Edit .env on the
# server directly, or upload it separately if you really need to.
# Pass --include-env to keep .env.example / .env.production in the
# zip (the live .env itself is still always excluded).
# ============================================================

set -euo pipefail

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

SRC_DIR="${1:-./backend}"
OUT_ZIP="${2:-./backend-deploy-$(date +%Y%m%d-%H%M%S).zip}"

if [ ! -d "$SRC_DIR" ]; then
    echo "Error: backend directory not found at '$SRC_DIR'" >&2
    echo "Run this from your repo root, or pass the path explicitly:" >&2
    echo "  ./make_backend_zip.sh /path/to/PPT-Agent/backend" >&2
    exit 1
fi

command -v zip >/dev/null 2>&1 || { echo "Error: 'zip' is not installed." >&2; exit 1; }

SRC_DIR="$(cd "$SRC_DIR" && pwd)"
PARENT_DIR="$(dirname "$SRC_DIR")"
BASE_NAME="$(basename "$SRC_DIR")"
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
    "$BASE_NAME/*.pyc"
    "$BASE_NAME/*.pyo"
    "$BASE_NAME/*/.pytest_cache/*"
    "$BASE_NAME/*/.mypy_cache/*"
    "$BASE_NAME/*.egg-info/*"

    # Virtual environments (never ship these — recreated on server via
    # cPanel Setup Python App + pip install)
    "$BASE_NAME/.venv/*"
    "$BASE_NAME/venv/*"
    "$BASE_NAME/env/*"
    "$BASE_NAME/ENV/*"

    # Version control / editor / OS junk
    "$BASE_NAME/.git/*"
    "$BASE_NAME/.idea/*"
    "$BASE_NAME/.vscode/*"
    "$BASE_NAME/*.DS_Store"
    "$BASE_NAME/*Thumbs.db"

    # Runtime-generated data — recreated automatically on the server,
    # don't ship stale copies over the live ones
    "$BASE_NAME/logs/*"
    "$BASE_NAME/output/*"
    "$BASE_NAME/private/*"
    "$BASE_NAME/downloads/*"
    "$BASE_NAME/*.log"

    # Secrets — see --include-env flag above
    "$BASE_NAME/.env"
)

if [ "$INCLUDE_ENV" = false ]; then
    EXCLUDES+=("$BASE_NAME/.env.production" "$BASE_NAME/.env.localhost" "$BASE_NAME/.env.example")
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
BAD=$(unzip -l "$OUT_ZIP" | grep -E "__pycache__|\.pyc$|/\.env$|/logs/|/output/|/private/|/downloads/|\.git/" || true)
if [ -n "$BAD" ]; then
    echo "WARNING: found unexpected files in the zip:"
    echo "$BAD"
else
    echo "Clean — no caches, envs, logs, or venvs included."
fi

echo ""
echo "Upload $OUT_ZIP via cPanel File Manager into"
echo "  /home/<user>/winbid.avanyaedge.com/"
echo "then use File Manager's 'Extract' on it (faster than uploading"
echo "thousands of individual files), and it will unpack to"
echo "  /home/<user>/winbid.avanyaedge.com/backend/"
echo "overwriting code files but leaving out .env, logs, and venv."