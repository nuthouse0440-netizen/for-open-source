#!/data/data/com.termux/files/usr/bin/bash
# Post a PERSISTENT (ongoing) notification bar with quick-action buttons.
# --ongoing = it stays in the shade and does NOT auto-dismiss when tapped.
SH="$HOME/.shortcuts"
termux-notification \
  --id agent-bar \
  --ongoing \
  --alert-once \
  --title "On-device Agent" \
  --content "Ask · Speak · Quick" \
  --action "bash $SH/agent-ask.sh" \
  --button1 "Ask"   --button1-action "bash $SH/agent-text.sh" \
  --button2 "Speak" --button2-action "bash $SH/agent-voice.sh" \
  --button3 "Quick" --button3-action "bash $SH/agent-quick.sh"
