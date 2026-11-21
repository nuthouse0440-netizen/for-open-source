#!/data/data/com.termux/files/usr/bin/bash
# Pull the latest actions/responses (commands.json) from GitHub.
# Routes through the "sync" command so the result is spoken + notified.
cd "$HOME/s26-agent" || exit 1
python3 agent.py --notify-reply "sync"
