#!/data/data/com.termux/files/usr/bin/bash
# Home-screen widget: pop a text box, send it to the on-device agent.
cd "$HOME/s26-agent" || exit 1
msg=$(termux-dialog text -t "Ask the agent" 2>/dev/null \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("text",""))' 2>/dev/null)
[ -z "$msg" ] && exit 0
python3 agent.py --notify-reply "$msg"
