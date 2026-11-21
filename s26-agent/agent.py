#!/data/data/com.termux/files/usr/bin/env python3
"""
On-device agent for Galaxy S26 (Termux, no root).

Brain : a local llama.cpp server (OpenAI-compatible) on 127.0.0.1:8080
Hands : Termux:API tools + file operations in shared storage.

The model replies with a single JSON object:
    {"action": "<name>", "args": {...}, "say": "<spoken reply>"}
The agent runs the action, then speaks `say`.

Actions:
  say                                      - just speak the reply
  notify      {title, content}             - post a notification
  battery                                  - (context already provided)
  datetime                                 - (context already provided)
  clipboard_get | clipboard_set {text}
  list_dir    {path}                       - list files in a folder
  organize    {path}                       - sort a folder into subfolders by type (confirms)
  move        {src, dst}                   - move/rename a file (confirms)
  volume      {stream, level}              - set volume (music/call/ring/...)
  torch       {on}                         - flashlight on/off
  open_settings {target}                   - open a Settings screen (wifi/bluetooth/display/...)
  send_sms    {number, text}               - off unless --allow-sms, always confirms

Usage:
    python agent.py "sort my downloads"
    python agent.py                 # interactive
    python agent.py --voice         # speech input
    python agent.py --allow-sms ... # enable SMS tool
    python agent.py --yes ...       # skip confirmations for file ops (use with care)

Standard library only. Degrades to print/input when Termux:API is absent.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

SERVER = "http://127.0.0.1:8080/v1/chat/completions"
HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "agent.log")
# Actions/responses are pulled from GitHub and cached here (core stays local).
COMMANDS_FILE = os.path.join(HERE, "commands.json")
GITHUB_COMMANDS_URL = ("https://raw.githubusercontent.com/nuthouse0440-netizen/"
                       "for-open-source/claude/repo-persistence-automation-9jmhzm/"
                       "s26-agent/commands.json")

ALLOW_SMS = "--allow-sms" in sys.argv
# Developer adb (over Wireless Debugging): enables BOTH settings changes and
# adb shell commands on the device. No Termux shell execution.
ALLOW_ADB = "--allow-adb" in sys.argv
# Task-level approval: your directive approves every step it needs, until the
# task is done -- no per-step prompts. The destructive denylist still applies.
AUTO = "--auto" in sys.argv
VOICE = "--voice" in sys.argv
# Post the agent's reply as an Android notification (used by the home-screen
# widget, where there's no terminal to read).
NOTIFY_REPLY = "--notify-reply" in sys.argv
ASSUME_YES = ("--yes" in sys.argv) or AUTO
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]

# Where "organize"/"list" default to. ~/storage/* exists after termux-setup-storage.
STORAGE = os.path.expanduser("~/storage/shared")
DOWNLOADS = os.path.join(STORAGE, "Download")

CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp"},
    "Video": {".mp4", ".mkv", ".mov", ".avi", ".webm"},
    "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a"},
    "Docs": {".pdf", ".doc", ".docx", ".txt", ".md", ".xls", ".xlsx", ".ppt", ".pptx"},
    "Archives": {".zip", ".tar", ".gz", ".7z", ".rar"},
    "Apps": {".apk"},
}

# Common Android Settings screens (am start -a android.settings.X)
SETTINGS_SCREENS = {
    "wifi": "android.settings.WIFI_SETTINGS",
    "bluetooth": "android.settings.BLUETOOTH_SETTINGS",
    "display": "android.settings.DISPLAY_SETTINGS",
    "sound": "android.settings.SOUND_SETTINGS",
    "battery": "android.settings.BATTERY_SAVER_SETTINGS",
    "location": "android.settings.LOCATION_SOURCE_SETTINGS",
    "apps": "android.settings.APPLICATION_SETTINGS",
    "data": "android.settings.DATA_USAGE_SETTINGS",
    "airplane": "android.settings.AIRPLANE_MODE_SETTINGS",
    "nfc": "android.settings.NFC_SETTINGS",
    "storage": "android.settings.INTERNAL_STORAGE_SETTINGS",
}

SYSTEM_PROMPT = """You are an on-device assistant on an Android phone.
Reply with ONLY one JSON object, no other text:
{"action":"<name>","args":{...},"say":"<short spoken reply>"}

Actions and args:
- say {}                         normal answer
- notify {title, content}
- clipboard_get {} | clipboard_set {text}
- battery {} | datetime {}       (values are already in the context message)
- list_dir {path}
- organize {path}                sort a folder into subfolders by file type
- move {src, dst}
- volume {stream, level}         stream one of music/call/ring/notification/system/alarm; level 0-15
- torch {on}                     on=true/false
- open_settings {target}         target one of: wifi, bluetooth, display, sound, battery,
                                 location, apps, data, airplane, nfc, storage
- get_setting {namespace, key}   read a setting; namespace is system/secure/global
- put_setting {namespace, key, value}  change ANY system setting (asks confirmation)
- toggle {target, on}            target wifi/data/bluetooth, on true/false
- adb_shell {command}            run a developer adb shell command on the device
- send_sms {number, text}

VERY IMPORTANT: If the user asks a question, chats, or wants information, use
action "say" and put the answer in "say". The current time (datetime) and
battery are already in the Live device context — read them from there and just
say them. Only use a NON-"say" action when the user explicitly asks you to DO
that thing (organize files, change a setting, toggle something, etc.).

Examples:
user: what time is it -> {"action":"say","args":{},"say":"It's 3:42 PM."}
user: how is my battery -> {"action":"say","args":{},"say":"74% and charging."}
user: tell me a joke -> {"action":"say","args":{},"say":"Why did the phone..."}
user: organize my downloads -> {"action":"organize","args":{"path":"downloads"},"say":"Organizing downloads."}
user: turn on the flashlight -> {"action":"torch","args":{"on":true},"say":"Flashlight on."}
user: open wifi settings -> {"action":"open_settings","args":{"target":"wifi"},"say":"Opening Wi-Fi settings."}
user: what's in my downloads -> {"action":"list_dir","args":{"path":"downloads"},"say":"Here's your downloads."}

If a task needs several steps, reply with a JSON ARRAY of these objects, in order.

Prefer put_setting/toggle for actually changing a setting; use open_settings only
when the exact key is unknown. Common keys: system/screen_brightness (0-255),
system/screen_off_timeout (ms), global/airplane_mode_on (0/1),
secure/location_mode (0 off, 3 high accuracy).

Rules: pick the single best action. Always include a friendly
"say". Return JSON only."""


def have(cmd):
    return shutil.which(cmd) is not None


def log(tag, text):
    """Append a timestamped line to the agent log (watched by the monitor)."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{datetime.datetime.now().strftime('%H:%M:%S')} "
                    f"[{tag}] {str(text).strip()}\n")
    except Exception:
        pass


def wa(reason, *tips):
    """Format a 'blocked -> here are workarounds' message (non-shell fixes first)."""
    body = " ".join(f"({i + 1}) {t}" for i, t in enumerate(tips))
    return f"Blocked: {reason} Workarounds: {body}" if tips else f"Blocked: {reason}"


# map a radio/toggle to the Settings screen you can flip by hand (non-shell fix)
_TOGGLE_SCREEN = {"wifi": "wifi", "bluetooth": "bluetooth", "data": "data"}


def _gui_yesno(msg):
    """Tap yes/no via Termux:API dialog. Returns True/False, or None if the
    dialog tool isn't available (caller falls back to terminal input)."""
    if not have("termux-dialog"):
        return None
    try:
        out = subprocess.run(["termux-dialog", "confirm", "-i", msg[:200]],
                            capture_output=True, text=True, timeout=120).stdout
        return json.loads(out).get("text", "").lower() == "yes"
    except Exception:
        return None


def confirm(msg):
    if ASSUME_YES:
        return True
    g = _gui_yesno(msg)
    if g is not None:
        return g
    try:
        return input(msg + " [y/N] ").strip().lower().startswith("y")
    except EOFError:
        return False


def confirm_always(msg):
    """Per-command confirmation. --auto (task approval) auto-approves but still
    PRINTS the command for transparency; the destructive denylist is separate
    and always blocks regardless of this."""
    if AUTO:
        print(msg + "  [auto-approved for this task]")
        return True
    g = _gui_yesno(msg)
    if g is not None:
        return g
    try:
        return input(msg + " [y/N] ").strip().lower().startswith("y")
    except EOFError:
        return False


# Backstop denylist: clearly catastrophic commands are refused outright.
_DANGER = [
    r"\brm\s+-rf?\s+/(?:\s|$|\*)", r"\bmkfs\b", r"\bdd\b[^|]*\bof=/dev/",
    r":\s*\(\s*\)\s*\{", r"\bfastboot\b", r"\bwipe\b", r"\bformat\b",
    r"--wipe", r"\breboot\b[^|]*bootloader", r"\bsvc\s+power\b",
    r"\bpm\s+(uninstall|clear)\b[^|]*\bcom\.android\.", r"device_provisioned",
    r">\s*/dev/(block|sd|mmc)", r"\bsetprop\s+ro\.",
]


def danger_reason(cmd):
    for p in _DANGER:
        if re.search(p, cmd):
            return p
    return None


def _run_captured(argv):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except Exception as e:
        return f"error: {e}"
    res = (out.stdout + out.stderr).strip()
    return f"(exit {out.returncode}) " + (res[:1500] if res else "(no output)")


def speak(text):
    print("AGENT:", text)
    if NOTIFY_REPLY and have("termux-notification"):
        try:
            subprocess.run(["termux-notification", "--title", "Agent",
                            "--content", text[:400]], timeout=15)
        except Exception:
            pass
    if have("termux-tts-speak"):
        try:
            subprocess.run(["termux-tts-speak", text], timeout=30)
        except Exception:
            pass


def device_context():
    ctx = {"datetime": datetime.datetime.now().isoformat(timespec="seconds")}
    if have("termux-battery-status"):
        try:
            ctx["battery"] = json.loads(subprocess.run(
                ["termux-battery-status"], capture_output=True, text=True,
                timeout=10).stdout)
        except Exception:
            pass
    return ctx


# ---------------- file operations ----------------
def _resolve(path):
    if not path or path in (".", "downloads", "Download", "~/storage/shared/Download"):
        return DOWNLOADS
    return os.path.expanduser(path)


def do_list_dir(path):
    p = _resolve(path)
    if not os.path.isdir(p):
        return wa(f"no such folder: {p}.",
                  "run setup again to grant storage access (termux-setup-storage)",
                  "try 'list downloads' or give a full path")
    items = sorted(os.listdir(p))
    return f"{len(items)} items in {p}: " + ", ".join(items[:40]) + \
           (" ..." if len(items) > 40 else "")


def category_for(fname):
    ext = os.path.splitext(fname)[1].lower()
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "Other"


def do_organize(path):
    p = _resolve(path)
    if not os.path.isdir(p):
        return wa(f"no such folder: {p}.",
                  "run setup again to grant storage access (termux-setup-storage)",
                  "say 'list downloads' first to confirm the path")
    moves = []
    for name in os.listdir(p):
        src = os.path.join(p, name)
        if os.path.isfile(src):
            moves.append((name, category_for(name)))
    if not moves:
        return f"Nothing to organize in {p}."
    preview = {}
    for name, cat in moves:
        preview.setdefault(cat, 0)
        preview[cat] += 1
    summary = ", ".join(f"{n}->{c}" for c, n in preview.items())
    if not confirm(f"Organize {len(moves)} files in {p} ({summary})?"):
        return "Cancelled."
    for name, cat in moves:
        dst_dir = os.path.join(p, cat)
        os.makedirs(dst_dir, exist_ok=True)
        try:
            shutil.move(os.path.join(p, name), os.path.join(dst_dir, name))
        except Exception as e:
            print("  skip", name, e)
    return f"Organized {len(moves)} files into {len(preview)} folders in {p}."


def do_move(src, dst):
    s, d = os.path.expanduser(src), os.path.expanduser(dst)
    if not os.path.exists(s):
        return f"No such file: {s}"
    if not confirm(f"Move {s} -> {d}?"):
        return "Cancelled."
    os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
    shutil.move(s, d)
    return f"Moved to {d}."


# ---------------- settings / toggles ----------------
def do_volume(stream, level):
    if have("termux-volume"):
        subprocess.run(["termux-volume", str(stream), str(level)], timeout=15)
        return f"Set {stream} volume to {level}."
    return "termux-volume not available."


def do_torch(on):
    if have("termux-torch"):
        subprocess.run(["termux-torch", "on" if on else "off"], timeout=15)
        return "Flashlight " + ("on." if on else "off.")
    return "termux-torch not available."


def do_open_settings(target):
    action = SETTINGS_SCREENS.get(str(target).lower())
    if not action:
        return f"Don't know the settings screen '{target}'."
    if have("am"):
        subprocess.run(["am", "start", "-a", action], timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened {target} settings."
    return "Cannot open settings (am not available)."


# ------- deep settings via Wireless-Debugging adb (no root, all confirmed) -------
VALID_NS = {"system", "secure", "global"}


def _settings_get_cmd(ns, key):
    return ["adb", "shell", "settings", "get", ns, key]


def _settings_put_cmd(ns, key, val):
    return ["adb", "shell", "settings", "put", ns, key, str(val)]


def _svc_cmd(target, on):
    return ["adb", "shell", "svc", target, "enable" if on else "disable"]


def adb_ready():
    if not have("adb"):
        return False, "adb not installed (pkg install android-tools)."
    try:
        out = subprocess.run(["adb", "devices"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception as e:
        return False, f"adb error: {e}"
    if "\tdevice" in out:
        return True, "ok"
    return False, ("No adb device connected. Turn on Wireless debugging, pair, "
                   "then `adb connect 127.0.0.1:<port>` (see README).")


def do_get_setting(ns, key):
    if ns not in VALID_NS:
        return f"namespace must be one of {sorted(VALID_NS)}."
    ok, msg = adb_ready()
    if not ok:
        return msg
    out = subprocess.run(_settings_get_cmd(ns, key), capture_output=True,
                        text=True, timeout=15).stdout.strip()
    return f"{ns}/{key} = {out or '(null)'}"


def do_put_setting(ns, key, val):
    if ns not in VALID_NS:
        return f"namespace must be one of {sorted(VALID_NS)}."
    ok, msg = adb_ready()
    if not ok:
        return wa(f"can't change {ns}/{key} via adb ({msg})",
                  "open the related Settings screen and change it by hand "
                  "(e.g. say 'open display settings')",
                  "pair Wireless debugging, then run with --allow-adb")
    cmd = _settings_put_cmd(ns, key, val)
    if not confirm("Run: " + " ".join(cmd) + " ?"):
        return "Cancelled."
    subprocess.run(cmd, timeout=15)
    return f"Set {ns}/{key} = {val}."


def do_toggle(target, on):
    if target not in {"wifi", "data", "bluetooth"}:
        return "toggle target must be wifi, data, or bluetooth."
    ok, msg = adb_ready()
    if not ok:
        return wa(f"can't toggle {target} directly ({msg})",
                  f"say 'open {_TOGGLE_SCREEN.get(target, target)} settings' and flip it by hand",
                  "pair Wireless debugging, then run with --allow-adb")
    cmd = _svc_cmd(target, on)
    if not confirm("Run: " + " ".join(cmd) + " ?"):
        return "Cancelled."
    subprocess.run(cmd, timeout=15)
    return f"{target} {'enabled' if on else 'disabled'}."


# ------- on-device developer commands via adb (dev mode) — off by default -----
def do_adb_shell(cmd):
    if not ALLOW_ADB:
        return wa("developer adb is off.",
                  "turn it on with --allow-adb (needs Wireless debugging paired)",
                  "for a setting, I can open its Settings screen instead — no shell needed")
    r = danger_reason(cmd)
    if r:
        return wa(f"that command is blocked as destructive ({r}).",
                  "if you truly need it, run it yourself in a terminal after reviewing it",
                  "tell me the goal and I'll suggest a safer, non-destructive way")
    ok, msg = adb_ready()
    if not ok:
        return wa(f"adb not connected ({msg})",
                  "pair Wireless debugging (Settings > Developer options)",
                  "or ask me to open the relevant Settings screen instead")
    if not confirm_always("RUN (adb shell on device): " + cmd + "\nProceed?"):
        return "Cancelled."
    return _run_captured(["adb", "shell", cmd])


# ---------------- model call + dispatch ----------------
def ask_model(user_text):
    # Fold everything into ONE user message. Some chat templates (e.g. Gemma)
    # reject a separate 'system' role and require roles to alternate
    # user/assistant, so a single user turn is the most portable.
    prompt = (SYSTEM_PROMPT
              + "\n\nLive device context: " + json.dumps(device_context())
              + "\n\nUser request: " + user_text)
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 256,
    }
    req = urllib.request.Request(SERVER, data=json.dumps(payload).encode(),
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()


def parse_action(text):
    start, depth = text.find("{"), 0
    if start == -1:
        return {"action": "say", "args": {}, "say": text}
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    break
    return {"action": "say", "args": {}, "say": text}


def battery_say():
    if have("termux-battery-status"):
        try:
            d = json.loads(subprocess.run(["termux-battery-status"],
                           capture_output=True, text=True, timeout=10).stdout)
            pct, st = d.get("percentage", "?"), str(d.get("status", "")).lower()
            return f"Battery is {pct}%" + (" and charging." if st == "charging" else ".")
        except Exception:
            pass
    return "I can't read the battery right now."


# ---- actions/responses: CORE defaults here, overridable from GitHub ----------
# The engine (this file) is the local core. commands.json holds the actual
# command->action rules + canned responses, pulled from GitHub and cached in
# COMMANDS_FILE. Edit the repo, run `sync`, and behavior updates with no code
# change. If no cached file exists, these built-in defaults are used.
DEFAULT_COMMANDS = [
    {"pattern": r"\b(what.?s the time|what time|the time|current time|clock)\b",
     "action": "say", "say": "It's {time}."},
    {"pattern": r"\bbattery\b", "action": "say", "say": "{battery}"},
    {"pattern": r"\bopen\s+([a-z]+)\s+settings?\b", "action": "open_settings",
     "group_into": {"target": 1}, "say": "Opening {g1} settings."},
    {"pattern": r"\bwi-?fi\b", "requires": r"\b(on|off|enable|disable|turn)\b",
     "action": "toggle", "args": {"target": "wifi"}, "on_from_text": True,
     "say": "Turning wifi {onoff}."},
    {"pattern": r"\bbluetooth\b", "requires": r"\b(on|off|enable|disable|turn)\b",
     "action": "toggle", "args": {"target": "bluetooth"}, "on_from_text": True,
     "say": "Turning bluetooth {onoff}."},
    {"pattern": r"\b(mobile data|cellular|data)\b",
     "requires": r"\b(on|off|enable|disable|turn)\b",
     "action": "toggle", "args": {"target": "data"}, "on_from_text": True,
     "say": "Turning data {onoff}."},
    {"pattern": r"\b(flashlight|torch|light)\b", "action": "torch",
     "on_from_text": True, "say": "Flashlight {onoff}."},
    {"pattern": r"\borganize\b", "action": "organize", "args": {"path": "downloads"},
     "say": "Organizing your downloads."},
    {"pattern": r"\b(list|show|what)\b.*\b(download|downloads|folder)\b",
     "action": "list_dir", "args": {"path": "downloads"}, "say": "Here's your downloads."},
    {"pattern": r"\b(clipboard|what did i copy)\b", "action": "clipboard_get",
     "say": "Reading clipboard."},
    {"pattern": r"\bvolume\b", "action": "volume", "args": {"stream": "music"},
     "value_into": "level", "say": "Setting volume to {value}."},
    {"pattern": r"\b(hi|hello|hey)\b", "action": "say", "say": "Hey — what do you need?"},
    {"pattern": r"\b(who are you|what are you|what can you do)\b", "action": "say",
     "say": "I'm your on-device agent. I can change settings, toggle radios, "
            "organize files, read battery and clipboard, and run developer adb "
            "commands — just tell me."},
    {"pattern": r"\b(sync|update actions|pull actions)\b", "action": "__sync__",
     "say": ""},
]


def load_commands():
    """Load the GitHub-synced command set if cached, else the built-in defaults."""
    try:
        with open(COMMANDS_FILE) as f:
            data = json.load(f)
        cmds = data.get("commands")
        if isinstance(cmds, list) and cmds:
            return cmds
    except Exception:
        pass
    return DEFAULT_COMMANDS


def sync_commands():
    """Pull the latest actions/responses from GitHub and cache them locally."""
    try:
        req = urllib.request.Request(GITHUB_COMMANDS_URL,
                                     headers={"User-Agent": "s26-agent"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        obj = json.loads(raw)                 # validate before writing
        n = len(obj.get("commands", []))
        with open(COMMANDS_FILE, "wb") as f:
            f.write(raw)
        return f"Synced {n} actions/responses from GitHub."
    except Exception as e:
        return f"Sync failed ({e}). Keeping current actions."


def _apply_command(c, text, mobj):
    args = dict(c.get("args", {}))
    say = c.get("say", "")
    low = text.lower()
    if c.get("on_from_text"):
        on = not re.search(r"\b(off|disable|out|stop|kill)\b", low)
        args["on"] = on
        say = say.replace("{onoff}", "on" if on else "off")
    if "value_into" in c:
        mn = re.search(r"(\d{1,3})", text)
        if mn:
            args[c["value_into"]] = int(mn.group(1))
            say = say.replace("{value}", mn.group(1))
    for arg, gi in c.get("group_into", {}).items():
        try:
            val = mobj.group(int(gi)) or ""
            args[arg] = val
            say = say.replace("{g%s}" % gi, val)
        except Exception:
            pass
    say = say.replace("{time}", datetime.datetime.now().strftime("%I:%M %p").lstrip("0"))
    say = say.replace("{battery}", battery_say())
    return {"action": c["action"], "args": args, "say": say}


def rule_match(text):
    """Match the user's words to an action using the (GitHub-synced) command set.
    First match wins; returns an action dict, or None to fall back to the model."""
    low = text.lower()
    for c in load_commands():
        try:
            mobj = re.search(c["pattern"], low)
        except (re.error, KeyError):
            continue
        if not mobj:
            continue
        if "requires" in c and not re.search(c["requires"], low):
            continue
        return _apply_command(c, text, mobj)
    return None


def parse_actions(text):
    """Return a list of action objects. The model may reply with a single
    object or a JSON array of them (a multi-step task)."""
    t = text.strip()
    try:
        v = json.loads(t)
        if isinstance(v, list):
            objs = [x for x in v if isinstance(x, dict) and "action" in x]
            return objs or [{"action": "say", "args": {}, "say": text}]
        if isinstance(v, dict):
            return [v]
    except Exception:
        pass
    return [parse_action(text)]


def run_action(obj):
    action = obj.get("action", "say")
    a = obj.get("args", {}) or {}
    say = obj.get("say", "")

    if action == "notify" and have("termux-notification"):
        subprocess.run(["termux-notification", "--title", a.get("title", "Agent"),
                        "--content", a.get("content", say)], timeout=15)
    elif action == "clipboard_set" and have("termux-clipboard-set"):
        subprocess.run(["termux-clipboard-set", a.get("text", "")], timeout=15)
    elif action == "clipboard_get" and have("termux-clipboard-get"):
        clip = subprocess.run(["termux-clipboard-get"], capture_output=True,
                             text=True, timeout=15).stdout
        say = (say + " Clipboard: " + clip).strip()
    elif action == "list_dir":
        say = do_list_dir(a.get("path", ""))
    elif action == "organize":
        say = do_organize(a.get("path", ""))
    elif action == "move":
        say = do_move(a.get("src", ""), a.get("dst", ""))
    elif action == "volume":
        say = do_volume(a.get("stream", "music"), a.get("level", 7))
    elif action == "torch":
        say = do_torch(bool(a.get("on", True)))
    elif action == "open_settings":
        say = do_open_settings(a.get("target", ""))
    elif action in ("get_setting", "put_setting", "toggle"):
        if not ALLOW_ADB:
            say = ("Deep settings control is off. Re-run with --allow-adb "
                   "(needs Wireless debugging paired).")
        elif action == "get_setting":
            say = do_get_setting(a.get("namespace", "global"), a.get("key", ""))
        elif action == "put_setting":
            say = do_put_setting(a.get("namespace", "global"),
                                 a.get("key", ""), a.get("value", ""))
        else:
            say = do_toggle(a.get("target", ""), bool(a.get("on", True)))
    elif action == "adb_shell":
        say = do_adb_shell(a.get("command", ""))
    elif action == "send_sms":
        if not ALLOW_SMS:
            say = wa("SMS is off.",
                     "re-run with --allow-sms",
                     "or open the Messages app and send it yourself")
        elif have("termux-sms-send"):
            num, txt = a.get("number", ""), a.get("text", "")
            if confirm(f"Send SMS to {num!r}: {txt!r}?"):
                subprocess.run(["termux-sms-send", "-n", num, txt], timeout=20)
                say = "Message sent."
            else:
                say = "Cancelled."
    speak(say or "Done.")
    return say or "Done."


def get_input():
    if VOICE and have("termux-speech-to-text"):
        print("(listening...)")
        return subprocess.run(["termux-speech-to-text"], capture_output=True,
                             text=True, timeout=60).stdout.strip()
    return input("you> ").strip()


def handle(text):
    if not text:
        return
    log("YOU", text)

    # 1) Deterministic command layer — reliable, no model guessing.
    ruled = rule_match(text)
    if ruled is not None:
        if ruled.get("action") == "__sync__":     # pull latest actions from GitHub
            log("RULE", "__sync__")
            speak(sync_commands())
            return
        log("RULE", json.dumps(ruled.get("action")) + " " + json.dumps(ruled.get("args", {})))
        log("RESULT", run_action(ruled))
        return

    # 2) Fall back to the model only for freeform requests.
    try:
        reply = ask_model(text)
    except Exception as e:
        msg = (f"Could not reach the local model server on 127.0.0.1:8080. "
               f"Is llama-server running? ({e})")
        log("ERROR", msg)
        speak(msg)
        return
    log("THINK", reply)                       # the model's raw output = its "thoughts"
    actions = parse_actions(reply)
    if len(actions) > 1:
        tag = "approved by your request" if AUTO else "will confirm each step"
        print(f"[task] {len(actions)} steps ({tag})")
        log("TASK", f"{len(actions)} steps ({tag})")
    for obj in actions:
        log("ACT", json.dumps(obj.get("action")) + " " + json.dumps(obj.get("args", {})))
        result = run_action(obj)
        log("RESULT", result)


def main():
    if "--sync" in sys.argv:                  # pull latest actions/responses
        print(sync_commands())
        if not ARGS:
            return
    if ARGS:
        handle(" ".join(ARGS))
        return
    print("On-device agent. Ctrl-C to quit.")
    while True:
        try:
            handle(get_input())
        except (KeyboardInterrupt, EOFError):
            print("\nbye")
            break


if __name__ == "__main__":
    main()
