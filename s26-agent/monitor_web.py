#!/data/data/com.termux/files/usr/bin/env python3
"""
Full-screen control panel for the on-device agent.

One whole-screen window:
  - TOP:    live thoughts + system responses (the agent's log, auto-updating)
  - MIDDLE: a command/code input box (type a request, hit Send)
  - BOTTOM: a rolling list of quick-action buttons (from commands.json)

Open it full-screen in the browser:  http://127.0.0.1:8899
Start it with the same flags you'd give the agent, e.g.:
    python monitor_web.py --allow-adb --auto

Standard library only. Binds to localhost — on-device only.
"""
import html
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "agent.log")
COMMANDS_FILE = os.path.join(HERE, "commands.json")
AGENT = os.path.join(HERE, "agent.py")
PORT = 8899
TAIL = 400

# Forward agent flags given on this server's command line (e.g. --allow-adb --auto)
AGENT_FLAGS = [a for a in sys.argv[1:]
               if a in ("--allow-adb", "--auto", "--allow-sms")]

TAG_COLOR = {"YOU": "#35c7ff", "THINK": "#c77dff", "RULE": "#ffd166",
             "ACT": "#ffd166", "RESULT": "#8cff98", "ERROR": "#ff6b6b",
             "TASK": "#ffa94d"}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Agent Console</title>
<style>
  :root{color-scheme:dark}
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:#0b0f14;color:#d7e0ea;
    font-family:ui-monospace,Menlo,Consolas,monospace}
  #app{display:flex;flex-direction:column;height:100dvh}
  header{padding:8px 12px;background:#111823;border-bottom:1px solid #223;
    font-weight:700;display:flex;justify-content:space-between;align-items:center}
  header small{color:#6b7a8d;font-weight:400}
  #thoughts{flex:1 1 auto;overflow-y:auto;padding:10px 12px;font-size:13px;line-height:1.5}
  .line{white-space:pre-wrap;word-break:break-word;padding:1px 0}
  .t{color:#55657a}.tag{font-weight:700}.blocked{color:#ff9a9a}
  #inputbar{display:flex;gap:6px;padding:8px;background:#0e141c;border-top:1px solid #223}
  #cmd{flex:1;min-height:42px;max-height:120px;resize:vertical;background:#0b0f14;
    color:#e6edf3;border:1px solid #2a3a4d;border-radius:8px;padding:10px;
    font-family:inherit;font-size:15px}
  #send{background:#1f6feb;color:#fff;border:0;border-radius:8px;padding:0 18px;
    font-weight:700;font-size:15px}
  #send:active{background:#1856b8}
  #quick{flex:0 0 auto;max-height:34vh;overflow-y:auto;padding:8px;background:#0e141c;
    border-top:1px solid #223;display:flex;flex-wrap:wrap;gap:8px;align-content:flex-start}
  .qa{background:#15202b;color:#cfe3f5;border:1px solid #27384a;border-radius:20px;
    padding:9px 14px;font-size:14px;white-space:nowrap}
  .qa:active{background:#1f6feb;color:#fff}
  #status{font-size:11px;color:#6b7a8d}
</style></head><body>
<div id="app">
  <header>🧠 Agent Console <small id="status">connecting…</small></header>
  <div id="thoughts">loading…</div>
  <div id="inputbar">
    <textarea id="cmd" placeholder="Type a command or request…  (Enter = send)"></textarea>
    <button id="send">Send</button>
  </div>
  <div id="quick"></div>
</div>
<script>
const thoughts=document.getElementById('thoughts');
const status=document.getElementById('status');
const cmd=document.getElementById('cmd');
let pinned=true;
thoughts.addEventListener('scroll',()=>{
  pinned = thoughts.scrollTop+thoughts.clientHeight >= thoughts.scrollHeight-30;
});
async function refresh(){
  try{
    const r=await fetch('/log'); const t=await r.text();
    thoughts.innerHTML=t; status.textContent='live';
    if(pinned) thoughts.scrollTop=thoughts.scrollHeight;
  }catch(e){ status.textContent='disconnected'; }
}
async function run(text){
  if(!text.trim()) return;
  status.textContent='running…';
  try{ await fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({text})}); }catch(e){}
  setTimeout(refresh,400);
}
document.getElementById('send').onclick=()=>{ run(cmd.value); cmd.value=''; };
cmd.addEventListener('keydown',e=>{
  if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); run(cmd.value); cmd.value=''; }
});
async function loadQuick(){
  try{
    const r=await fetch('/actions'); const list=await r.json();
    const q=document.getElementById('quick'); q.innerHTML='';
    list.forEach(a=>{
      const b=document.createElement('button'); b.className='qa'; b.textContent=a.label;
      b.onclick=()=>run(a.cmd); q.appendChild(b);
    });
  }catch(e){}
}
loadQuick(); refresh(); setInterval(refresh,1500);
</script></body></html>"""


def render_log():
    try:
        with open(LOG_FILE, "r", errors="replace") as f:
            lines = f.readlines()[-TAIL:]
    except FileNotFoundError:
        return "(no activity yet — send a command below)"
    out = []
    for ln in lines:
        ln = ln.rstrip("\n")
        ts, tag, rest = "", "", ln
        if len(ln) > 9 and ln[2] == ":" and ln[5] == ":":
            ts, rest = ln[:8], ln[9:]
        if rest.startswith("[") and "]" in rest:
            tag = rest[1:rest.index("]")]
            rest = rest[rest.index("]") + 1:]
        color = TAG_COLOR.get(tag, "#9fb0c3")
        cls = "blocked" if "Blocked:" in rest else ""
        out.append(f'<div class="line"><span class="t">{html.escape(ts)}</span> '
                   f'<span class="tag" style="color:{color}">{html.escape(tag)}</span>'
                   f'<span class="{cls}">{html.escape(rest)}</span></div>')
    return "\n".join(out)


def quick_actions():
    try:
        return json.load(open(COMMANDS_FILE)).get("quick_actions", [])
    except Exception:
        return []


def run_agent(text):
    """Run the agent with the given text (logs to agent.log, which the page shows)."""
    try:
        subprocess.Popen(["python3", AGENT, *AGENT_FLAGS, "--notify-reply", text])
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(PAGE)
        elif path == "/log":
            self._send(render_log())
        elif path == "/actions":
            self._send(json.dumps(quick_actions()), "application/json")
        else:
            self._send("not found", code=404)

    def do_POST(self):
        if urlparse(self.path).path == "/run":
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
                text = str(data.get("text", ""))[:2000]
            except Exception:
                text = ""
            if text.strip():
                run_agent(text)
            self._send(json.dumps({"ok": True}), "application/json")
        else:
            self._send("not found", code=404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    flags = " ".join(AGENT_FLAGS) or "(normal mode)"
    print(f"Agent Console on http://127.0.0.1:{PORT}  flags: {flags}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
