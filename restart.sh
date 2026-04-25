#!/bin/bash

# --- ADS v1.0 Clean Restart Script ---
echo "--- ADS: Cleaning up old processes ---"

# 1. Kill all headless instances
# pkill -f will match any process with 'headless.py' in the command line
pkill -9 -f headless.py

# 2. Wait a bit for cleanup
sleep 2

# 3. Double check and kill any remaining python3 processes in this dir (optional)
# ps aux | grep headless.py | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null

# 4. Verify venv
if [ ! -d "./venv" ]; then
    echo "ERROR: venv not found. Please create it first."
    exit 1
fi

# 5. Start new process
echo "--- ADS: Starting fresh headless instance ---"
# We use nohup and redirect to /tmp/headless.log to avoid closing on disconnect
# Also using 2>&1 to capture errors
nohup ./venv/bin/python3 headless.py > /tmp/headless.log 2>&1 &

echo "--- ADS: Restart Complete ---"
echo "Monitor logs with: tail -f /tmp/headless.log"
echo "Check PID with: pgrep -f headless.py"
