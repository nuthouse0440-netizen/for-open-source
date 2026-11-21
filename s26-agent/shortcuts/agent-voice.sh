#!/data/data/com.termux/files/usr/bin/bash
# Home-screen widget: listen via mic, send speech to the on-device agent.
cd "$HOME/s26-agent" || exit 1
msg=$(termux-speech-to-text 2>/dev/null)
[ -z "$msg" ] && exit 0
python3 agent.py --notify-reply "$msg"
