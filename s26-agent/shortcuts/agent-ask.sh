#!/data/data/com.termux/files/usr/bin/bash
# Home-screen widget: choose Type or Speak, then ask the on-device agent.
# (Add --allow-adb / --auto to the python line below if you want those on.)
cd "$HOME/s26-agent" || exit 1

mode=$(termux-dialog sheet -t "Agent" -v "Type,Speak" 2>/dev/null \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("text",""))' 2>/dev/null)

case "$mode" in
  Type)
    msg=$(termux-dialog text -t "Ask the agent" 2>/dev/null \
      | python3 -c 'import sys,json;print(json.load(sys.stdin).get("text",""))' 2>/dev/null)
    ;;
  Speak)
    msg=$(termux-speech-to-text 2>/dev/null)
    ;;
  *)
    exit 0
    ;;
esac

[ -z "$msg" ] && exit 0
python3 agent.py --notify-reply "$msg"
