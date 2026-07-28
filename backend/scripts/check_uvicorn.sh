#!/bin/bash
# ============================================================
# check_uvicorn.sh — cPanel Uvicorn watchdog
# ============================================================
# Place at: ~/scripts/check_uvicorn.sh
# Add to cPanel Cron Jobs (crontab -e):
#   * * * * * /bin/bash ~/scripts/check_uvicorn.sh >/dev/null 2>&1
#   @reboot    /bin/bash ~/scripts/check_uvicorn.sh >/dev/null 2>&1
#
# How to find your Python path:
#   In cPanel → Setup Python App → view your app → copy the "Python path"
#   It looks like: /home/USERNAME/virtualenv/APPDIR/3.11/bin/python3.11
# ============================================================

# ── EDIT THESE ──────────────────────────────────────────────
APP_DIR="/home/gmfdmmzn/winbid.avanyaedge.com/backend"
VENV_PYTHON="/home/gmfdmmzn/virtualenv/winbid.avanyaedge.com/backend/3.13/bin/python"
PORT=5050
LOG_FILE="$APP_DIR/logs/uvicorn.log"
# ─────────────────────────────────────────────────────────────

# Ensure log directory exists
mkdir -p "$APP_DIR/logs"

# Check if Uvicorn is already running on the configured port
if pgrep -f "uvicorn server:app.*--port $PORT" > /dev/null 2>&1; then
    # Already running — nothing to do
    exit 0
fi

# Start Uvicorn
cd "$APP_DIR" || exit 1

# Load .env production variables
if [ -f "$APP_DIR/.env" ]; then
    export $(grep -v '^#' "$APP_DIR/.env" | xargs -d '\n') 2>/dev/null || true
fi

nohup "$VENV_PYTHON" -m uvicorn server:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --workers 1 \
    --timeout-keep-alive 600 \
    >> "$LOG_FILE" 2>&1 &

echo "[$(date)] Uvicorn started (PID $!)" >> "$LOG_FILE"
