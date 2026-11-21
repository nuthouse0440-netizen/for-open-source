#!/data/data/com.termux/files/usr/bin/bash
# Home-screen widget: open the full-screen live monitor (thoughts + responses).
cd "$HOME/s26-agent" || exit 1
# start the web dashboard if it isn't already running
pgrep -f monitor_web.py >/dev/null 2>&1 || (nohup python3 monitor_web.py >/dev/null 2>&1 &)
sleep 1
# open it full-screen in the browser
termux-open-url http://127.0.0.1:8899 2>/dev/null || \
  echo "Open http://127.0.0.1:8899 in your browser."
