#!/data/data/com.termux/files/usr/bin/env python3
"""
Full-screen live dashboard for the on-device agent.

Serves a dark, auto-refreshing page showing the agent's thoughts, actions,
and system responses from agent.log. Open it full-screen in your browser:

    python ~/s26-agent/monitor_web.py      # then open http://127.0.0.1:8899

Standard library only. Runs for as long as you leave it (hours is fine).
"""
import html
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "agent.log")
PORT = 8899
TAIL_LINES = 500

TAG_COLOR = {
    "YOU": "#35c7ff", "THINK": "#c77dff", "ACT": "#ffd166",
    "RESULT": "#8cff98", "ERROR": "#ff6b6b", "TASK": "#ffa94d",
}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="2">
<title>Agent Monitor</title>
<style>
  :root {{ color-scheme: dark; }}
  html,body {{ margin:0; height:100%; background:#0b0f14; color:#d7e0ea;
    font-family:ui-monospace,Menlo,Consolas,monospace; }}
  header {{ position:sticky; top:0; background:#111823; padding:10px 14px;
    border-bottom:1px solid #223; font-weight:700; letter-spacing:.3px; }}
  header small {{ color:#6b7a8d; font-weight:400; }}
  #log {{ padding:10px 14px 60vh; font-size:14px; line-height:1.5; }}
  .line {{ white-space:pre-wrap; word-break:break-word; padding:1px 0; }}
  .t {{ color:#55657a; }}
  .tag {{ font-weight:700; }}
  .blocked {{ color:#ff9a9a; }}
</style></head><body>
<header>🧠 On-device Agent — live thoughts &amp; responses
  <small>auto-refreshes every 2s · {n} lines</small></header>
<div id="log">{body}</div>
<script>window.scrollTo(0, document.body.scrollHeight);</script>
</body></html>"""


def render():
    try:
        with open(LOG_FILE, "r", errors="replace") as f:
            lines = f.readlines()[-TAIL_LINES:]
    except FileNotFoundError:
        lines = ["(no log yet — talk to the agent and it will appear here)\n"]
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
        cls = " blocked" if "Blocked:" in rest else ""
        out.append(
            f'<div class="line"><span class="t">{html.escape(ts)}</span> '
            f'<span class="tag" style="color:{color}">{html.escape(tag)}</span>'
            f'<span class="{cls.strip()}">{html.escape(rest)}</span></div>')
    return "\n".join(out), len(lines)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body, n = render()
        page = PAGE.format(body=body, n=n)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def log_message(self, *a):
        pass  # quiet


if __name__ == "__main__":
    print(f"Agent monitor on http://127.0.0.1:{PORT}  (log: {LOG_FILE})")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
