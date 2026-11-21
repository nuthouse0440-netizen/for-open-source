#!/data/data/com.termux/files/usr/bin/bash
# Live monitor: watch the agent's thoughts, actions, and system responses.
# Best run in a Termux:Float window so it floats on top, always visible.
LOG="$(cd "$(dirname "$0")" && pwd)/agent.log"
touch "$LOG"
clear
echo "============================================================"
echo "  ON-DEVICE AGENT — LIVE MONITOR"
echo "  thoughts [THINK]  actions [ACT]  results [RESULT]"
echo "  (Ctrl-C to close; it keeps running for hours.)"
echo "============================================================"
# Colorize tags if the terminal supports it; otherwise plain tail.
tail -n 300 -f "$LOG" | sed \
  -e 's/\(\[YOU\]\)/\x1b[1;36m\1\x1b[0m/' \
  -e 's/\(\[THINK\]\)/\x1b[1;35m\1\x1b[0m/' \
  -e 's/\(\[ACT\]\)/\x1b[1;33m\1\x1b[0m/' \
  -e 's/\(\[RESULT\]\)/\x1b[1;32m\1\x1b[0m/' \
  -e 's/\(\[ERROR\]\)/\x1b[1;31m\1\x1b[0m/' \
  -e 's/\(Blocked:\)/\x1b[1;31m\1\x1b[0m/'
