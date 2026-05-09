#!/bin/bash
# Hourly cron script — processes pending resume_queue items
# Called by: crontab -e → 0 * * * * /Users/rashmicagopinath/workspace/Resume_Generator/run_queue.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/run_${TIMESTAMP}.log"

echo "=== Resume Queue Run: $(date) ===" >> "$LOG_FILE"

cd "$SCRIPT_DIR"
/opt/homebrew/bin/python3 main.py --queue --limit 20 >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "=== Exit code: $EXIT_CODE ===" >> "$LOG_FILE"

# Keep only last 7 days of logs
find "$LOG_DIR" -name "run_*.log" -mtime +7 -delete 2>/dev/null || true

exit $EXIT_CODE
