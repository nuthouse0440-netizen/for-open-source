#!/data/data/com.termux/files/usr/bin/bash
# Quick-command menu: a wide list of one-tap responses + Type/Speak.
# Edit PRESETS to add your own. "Label=command text"
cd "$HOME/s26-agent" || exit 1

PRESETS=(
  "Battery=what's my battery level"
  "Organize downloads=organize my downloads"
  "List downloads=what's in my downloads"
  "Time & date=what time is it"
  "Read clipboard=read my clipboard"
  "Flashlight on=turn on the flashlight"
  "Flashlight off=turn off the flashlight"
  "Open Wi-Fi settings=open wifi settings"
  "Open Bluetooth settings=open bluetooth settings"
  "Open Display settings=open display settings"
)

labels=""
for p in "${PRESETS[@]}"; do labels="$labels,${p%%=*}"; done
labels="${labels#,},Type...,Speak..."

choice=$(termux-dialog sheet -t "Quick command" -v "$labels" 2>/dev/null \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("text",""))' 2>/dev/null)

[ -z "$choice" ] && exit 0

msg=""
case "$choice" in
  "Type...")
    msg=$(termux-dialog text -t "Ask the agent" 2>/dev/null \
      | python3 -c 'import sys,json;print(json.load(sys.stdin).get("text",""))' 2>/dev/null) ;;
  "Speak...")
    msg=$(termux-speech-to-text 2>/dev/null) ;;
  *)
    for p in "${PRESETS[@]}"; do
      if [ "${p%%=*}" = "$choice" ]; then msg="${p#*=}"; break; fi
    done ;;
esac

[ -z "$msg" ] && exit 0
python3 agent.py --notify-reply "$msg"
