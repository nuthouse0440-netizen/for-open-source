# On-Device Agent for Galaxy S26 (no root)

A private, offline assistant that runs entirely on your phone:
**local LLM (llama.cpp) + Termux:API device actions**. No root, no cloud.

## What it can actually do
- Answer questions, summarize, rewrite — **offline**, on-device.
- **Organize files** in your shared storage: sort a folder (e.g. Downloads)
  into Images/Video/Audio/Docs/Archives/Apps/Other, list folders, move/rename
  files. (Destructive ops ask for confirmation unless you pass `--yes`.)
- **Change settings on request** — three tiers, all no-root:
  - direct toggles: volume, flashlight;
  - **open any Settings screen** (Wi-Fi, Bluetooth, display…) so you tap once;
  - **deep control** (`--allow-adb`): change *any* system setting directly via
    `settings put` / `svc` over Wireless Debugging — **every change asks you to
    confirm the exact command first.** One-time pairing required (see below).
- Other **device actions** via Termux:API: speak replies (TTS), post
  notifications, read battery, read/set clipboard, tell the time, and
  (optional) send an SMS after you confirm.
- Take **voice input** (`--voice`) using Termux's speech-to-text.
- Auto-start the model server at boot and stay running.

### Example requests
```
"sort my downloads"            -> organizes ~/storage/shared/Download by type
"what's in my downloads"       -> lists the folder
"turn the flashlight on"       -> toggles torch
"set music volume to 10"       -> sets volume
"open wifi settings"           -> opens the Wi-Fi settings screen
"remind me — notify: take meds"-> posts a notification
```

## What it can NOT do (honest limits)
- It is a **small (1B) model** — far weaker than Claude/ChatGPT. Good for
  simple tasks; it will make mistakes on hard ones. Swap in `gemma-3-4b-it`
  for better quality if the phone handles it.
- It can only do what **Termux:API allows without root** — it can't silently
  control arbitrary apps, change system settings it has no permission for,
  or act as a full system takeover. That's an Android security boundary, not
  a bug.
- Android may still kill it under heavy memory pressure even with the
  battery/boot steps.

## Install (do these on the phone)
1. Install **Termux**, **Termux:API**, and **Termux:Boot** from **F-Droid**
   (NOT the Play Store versions).
2. Copy `setup.sh` and `agent.py` into Termux (e.g. into `~/s26-agent/`).
3. Run:
   ```bash
   bash ~/s26-agent/setup.sh
   ```
   This builds llama.cpp, downloads a small model, installs Termux:API,
   starts the local server, and sets it to auto-start at boot.
4. Do the two manual steps the script prints at the end:
   - Open the **Termux:Boot** app once (grants boot permission).
   - Settings → Apps → **Termux** → Battery → **Unrestricted** (same for
     Termux:API and Termux:Boot).

## Use it — home-screen widget (normal mode, no terminal)
This is the everyday way to use it: a tap widget on your home screen.
1. Install **Termux:Widget** from F-Droid.
2. `setup.sh` already copied the widget scripts to `~/.shortcuts/`.
3. Long-press home screen → **Widgets** → **Termux:Widget** → add it and pick:
   - **agent-ask** — taps up a menu: *Type* or *Speak*
   - **agent-text** — pops a text box to type into
   - **agent-voice** — listens on the mic
4. The reply is **spoken aloud and shown as a notification** (so you see it
   after the widget closes).

Tap the widget → type or talk → get your answer. No terminal, no flags — that's
"normal mode." (Confirmations for file moves etc. appear as tap **yes/no**
dialogs.) To give a widget more power, edit its script in `~/.shortcuts/` and
add flags to the `python agent.py` line (e.g. `--allow-adb --auto`).

## Quick responses from the notification shade
A **persistent (ongoing) notification** is posted at setup and every boot with
three buttons — **Ask** (type), **Speak** (mic), **Quick** (menu of common
one-tap commands) — and tapping the body opens the Type/Speak chooser. Because
it's `--ongoing` it **stays in the shade and does not auto-dismiss/cancel** when
you tap it. Edit the `PRESETS` list in `~/.shortcuts/agent-quick.sh` to add your
own one-tap commands. Re-show it anytime with the `agent-bar` widget.

## Use it — from the terminal
```bash
python ~/s26-agent/agent.py "what's my battery level"   # one-shot
python ~/s26-agent/agent.py                             # interactive
python ~/s26-agent/agent.py --voice                     # speak to it
python ~/s26-agent/agent.py --allow-sms "text Sam running late"  # SMS (confirms first)
```

## Live monitor — watch its thoughts & system responses (full screen)
The agent logs everything it does to `agent.log`: your input (`YOU`), the
model's raw output / reasoning (`THINK`), each action (`ACT`), and each system
response (`RESULT` / `ERROR`). Two always-on viewers:

**Web dashboard (recommended, whole-screen):** auto-starts at boot on
`http://127.0.0.1:8899`.
```bash
python ~/s26-agent/monitor_web.py     # if not already running
```
Open that URL in your browser and go full-screen (Chrome ⋮ → *Add to Home
screen* makes it a full-screen app icon). It auto-refreshes every 2s, colour-
codes THINK/ACT/RESULT, and scrolls to the latest. Leave it up as long as you
like — hours is fine.

**Always-on-top floating window:** install **Termux:Float** (F-Droid), open it,
and run `~/s26-agent/monitor.sh` — a live, colour-coded `tail -f` that floats
over other apps.

> Honest note on "a whole home-screen page": Android doesn't let a Termux
> script paint a live home-screen *widget page* without extra apps (that needs
> something like KWGT + Tasker, or a custom app). The closest no-extra-build
> options are the two above — a full-screen browser dashboard, or a Termux:Float
> window that's always on top. Both show the live thoughts/responses full-size.

## When something is blocked, it offers workarounds
Instead of just failing, blocked actions return `Blocked: <reason>
Workarounds: (1) … (2) …`, preferring **non-shell fixes** first. Examples:
- *toggle Wi-Fi but adb isn't connected* → "say 'open wifi settings' and flip
  it by hand" / "pair Wireless debugging and run with --allow-adb"
- *change a setting but adb off* → "open the related Settings screen" first
- *a destructive command* → "do it yourself after reviewing it" / "tell me the
  goal and I'll suggest a safer way"
- *no storage access* → "run setup again (termux-setup-storage)"

These appear in the spoken reply, the notification, and the live monitor.

## How it works
`agent.py` sends your text + a little live device context (battery, time)
to the local model, which replies with a JSON action
(`say` / `notify` / `clipboard_*` / `battery` / `datetime` / `send_sms`).
The agent runs that action and speaks the reply. SMS is **off by default**
and always asks for confirmation.

## Customizing
- **Bigger/smarter model:** edit `MODEL_FILE`/`MODEL_URL` in `setup.sh`
  (e.g. `gemma-3-4b-it-Q4_K_M.gguf`).
- **More tools:** add branches in `run_action()` for other `termux-*`
  commands (location, SMS inbox, camera, etc.) and list them in the
  system prompt. Keep risky actions behind a confirmation like SMS.
## Deep settings control (`--allow-adb`) — change ANY setting, no root
This is built in. It uses Android's **Wireless Debugging** so Termux can run
`adb` against the phone itself — no root, no PC.

**One-time pairing (Android 11+):**
1. Settings → Developer options → **Wireless debugging → ON**
2. Tap **"Pair device with pairing code"** → note the `IP:PORT` + 6-digit code
3. In Termux: `adb pair 127.0.0.1:<pair_port>` → enter the code
4. On the main Wireless-debugging screen, note the **connect PORT**, then:
   `adb connect 127.0.0.1:<connect_port>`

Then run the agent with `--allow-adb`:
```bash
python ~/s26-agent/agent.py --allow-adb
```
Now requests like *"set brightness to 120"*, *"turn wifi off"*, *"airplane mode
on"* work via `settings put` / `svc`. **Every change prints the exact command
and asks you to confirm** (unless you pass `--yes`).

Safety / caveats:
- A wrong `settings put` can misconfigure the phone — that's why each one is
  confirmed. Values are reversible (`settings put` the old value back).
- The Wireless-debugging **ports change every time you toggle it** — re-run
  `adb connect` if it disconnects.
- This is still **not root**: it can't do what `adb shell` itself can't.

## Developer adb (`--allow-adb`) — run adb shell commands on the device
`--allow-adb` enables BOTH the settings tools above AND the `adb_shell`
action, which runs **developer adb shell** commands on the device over
Wireless Debugging (no root, no Termux-shell access): e.g. `pm list packages`,
`dumpsys battery`, `input tap x y`, `am start ...`.

```bash
python ~/s26-agent/agent.py --allow-adb
```

## Task approval (`--auto`) — one directive approves the whole task
By default, each setting change / adb command asks you to confirm. With
`--auto`, **your request is the approval**: the agent runs every step the task
needs, in order, without per-step prompts, until the task is done.

```bash
python ~/s26-agent/agent.py --allow-adb --auto
```

**Guardrails that remain even under `--auto`:**
- The **destructive-command denylist still blocks** clearly dangerous commands
  outright (`rm -rf /`, `mkfs`, `dd of=/dev/…`, `fastboot`, `wipe`/`format`,
  uninstalling core `com.android.*` packages, fork bombs). This is a backstop
  and **cannot** be turned off by `--auto`.
- Under `--auto` each command is still **printed** (marked `[auto-approved for
  this task]`) so you can see what ran.
- The model driving this is a small local model and can be wrong or be swayed
  by text it reads. `--auto` trades per-step review for convenience — use it
  for tasks you trust; drop `--auto` when you want to approve each command.
- Still **not root**.
