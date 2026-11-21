#!/data/data/com.termux/files/usr/bin/bash
# =====================================================================
# On-device agent setup for Galaxy S26 (Termux, no root required)
# Builds llama.cpp, downloads a small model, installs Termux:API,
# and sets up the local model server to auto-start at boot.
#
# RUN THIS INSIDE TERMUX (installed from F-Droid, NOT the Play Store).
# Also install the "Termux:API" and "Termux:Boot" add-on apps from F-Droid.
# =====================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR="$HOME/models"
MODEL_FILE="gemma-3-1b-it-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf?download=true"
LLAMA_DIR="$HOME/llama.cpp"
PORT=8080

echo "==> [1/6] Updating packages..."
pkg update -y && pkg upgrade -y

echo "==> [2/6] Installing build tools + Termux:API CLI + python + adb..."
pkg install -y git cmake clang make openssl libcurl wget python termux-api android-tools

echo "==> Granting access to shared storage (needed for file organization)..."
echo "    (Android will show a permission dialog — tap Allow.)"
termux-setup-storage || true

echo "==> [3/6] Cloning + building llama.cpp (this takes a few minutes)..."
if [ ! -d "$LLAMA_DIR" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
fi
cd "$LLAMA_DIR"
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j"$(nproc)"

echo "==> [4/6] Downloading model ($MODEL_FILE)..."
mkdir -p "$MODEL_DIR"
if [ ! -f "$MODEL_DIR/$MODEL_FILE" ]; then
  wget -O "$MODEL_DIR/$MODEL_FILE" "$MODEL_URL"
fi

echo "==> [5/6] Installing boot auto-start script..."
mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/start-llama.sh" << BOOT
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
cd "$LLAMA_DIR"
./build/bin/llama-server -m "$MODEL_DIR/$MODEL_FILE" \
  --host 127.0.0.1 --port $PORT > "\$HOME/llama-server.log" 2>&1 &
# live-monitor web dashboard (http://127.0.0.1:8899)
python3 "$SCRIPT_DIR/monitor_web.py" > "\$HOME/monitor.log" 2>&1 &
# persistent quick-response notification bar (ongoing; does not auto-dismiss)
(sleep 3; bash "\$HOME/.shortcuts/agent-bar.sh") > /dev/null 2>&1 &
BOOT
chmod +x "$HOME/.termux/boot/start-llama.sh"

echo "==> Installing home-screen widget shortcuts (Termux:Widget)..."
mkdir -p "$HOME/.shortcuts"
if [ -d "$SCRIPT_DIR/shortcuts" ]; then
  cp "$SCRIPT_DIR"/shortcuts/*.sh "$HOME/.shortcuts/" 2>/dev/null || true
  chmod +x "$HOME/.shortcuts/"*.sh 2>/dev/null || true
fi

echo "==> [6/6] Starting the server now (for this session)..."
termux-wake-lock || true
cd "$LLAMA_DIR"
nohup ./build/bin/llama-server -m "$MODEL_DIR/$MODEL_FILE" \
  --host 127.0.0.1 --port $PORT > "$HOME/llama-server.log" 2>&1 &
nohup python3 "$SCRIPT_DIR/monitor_web.py" > "$HOME/monitor.log" 2>&1 &
bash "$HOME/.shortcuts/agent-bar.sh" 2>/dev/null || true

echo ""
echo "===================================================================="
echo " DONE. Local model server is starting on http://127.0.0.1:$PORT"
echo ""
echo " IMPORTANT manual steps (Android will kill it otherwise):"
echo "   1. Open the 'Termux:Boot' app ONCE to grant boot permission."
echo "   2. Settings > Apps > Termux > Battery > set to 'Unrestricted'."
echo "      Do the same for 'Termux:API' and 'Termux:Boot'."
echo ""
echo " HOME-SCREEN WIDGET (tap to type / use mic):"
echo "   1. Install the 'Termux:Widget' app from F-Droid."
echo "   2. Long-press your home screen > Widgets > Termux:Widget."
echo "   3. Add it and pick a shortcut:"
echo "        agent-ask     = choose Type or Speak"
echo "        agent-text    = type a message"
echo "        agent-voice   = speak a message"
echo "        agent-quick   = menu of common one-tap commands"
echo "        agent-monitor = open the full-screen live monitor"
echo "        agent-bar     = (re)show the persistent notification bar"
echo "   Replies appear as a notification and are spoken aloud."
echo ""
echo " NOTIFICATION BAR (quick responses from the shade):"
echo "   A persistent (ongoing) notification with Ask / Speak / Quick buttons"
echo "   is posted now and at every boot. It does NOT auto-dismiss."
echo "   Tapping a button runs the agent; tapping the body opens the chooser."
echo ""
echo " LIVE MONITOR (watch its thoughts + responses, full screen):"
echo "   - Web dashboard (auto-starts at boot): open http://127.0.0.1:8899"
echo "     in your browser (tap 'agent-monitor' widget, or Chrome > that URL)."
echo "     Add it to your home screen / make it a PWA for a whole-screen view."
echo "   - Always-on-top floating window: install 'Termux:Float' (F-Droid),"
echo "     open it, and run:  ~/s26-agent/monitor.sh"
echo ""
echo " Then talk to your agent with:   python ~/s26-agent/agent.py"
echo ""
echo " OPTIONAL — deep settings control (change ANY setting, no root):"
echo "   One-time pairing (Android 11+):"
echo "     a. Settings > Developer options > Wireless debugging > ON"
echo "     b. Tap 'Pair device with pairing code' -> note the IP:PORT + 6-digit code"
echo "     c. In Termux:  adb pair 127.0.0.1:<pair_port>   (enter the code)"
echo "     d. On the main Wireless-debugging screen, note the connect PORT, then:"
echo "          adb connect 127.0.0.1:<connect_port>"
echo "   --allow-adb enables BOTH settings changes AND developer adb shell"
echo "   commands on the device, e.g.:"
echo "     python ~/s26-agent/agent.py --allow-adb"
echo "   (ports change each time Wireless debugging is toggled -> re-run adb connect.)"
echo ""
echo " TASK APPROVAL (--auto):"
echo "   python ~/s26-agent/agent.py --allow-adb --auto"
echo "   Your request approves every step of that task -- no per-step y/N prompts."
echo "   Destructive commands (rm -rf /, mkfs, fastboot, wipe...) are STILL refused."
echo "   Without --auto, each change/command asks you to confirm."
echo "===================================================================="
