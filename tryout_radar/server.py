"""Serve the static site and the small API the site's buttons use (Python standard library only).

GET  <prefix>/...            files from site_dir (index.html, <date>.html, trials/<tid>.html)
GET  <prefix>/api/trials     latest trial status per item
GET  <prefix>/api/feedback   the owner's marks (want / done / skip)
POST <prefix>/api/trial      {"date","id","project","note"} -> queue a trial, notify the owner
POST <prefix>/api/feedback   {"date","id","status": "want"|"done"|"skip"|null}
POST <prefix>/api/project    {"date","key"} -> stop following a newly discovered project
POST <prefix>/api/decide     {"tid","option"} -> the owner's choice on a trial report (continue / retarget / close / adopt)
GET  <prefix>/api/ignored    discovered projects you stopped following

<prefix> is "/<server.secret_path>" when set, otherwise "". Anyone who knows the URL can use the buttons,
so keep secret_path long and random, and put the server behind HTTPS (see deploy/)."""
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import notify, render
from .config import project_names
from .render import strings
from .store import Store

MAX_BODY = 4096


def make_handler(cfg):
    store = Store(cfg)
    site = Path(cfg["_site"]).resolve()
    secret = cfg["server"]["secret_path"]
    prefix = f"/{secret}/" if secret else "/"

    def ack(trial):
        S = strings(cfg)
        name = project_names(cfg).get(trial["project"], trial["project"])
        title = (trial.get("item") or {}).get("title") or trial["itemId"]
        lines = [f"**{S['try_btn']}**", f"{title} → **{name}**"]
        if trial.get("note"):
            lines.append(f"> {trial['note']}")
        lines.append(S["queued_msg"].format(when=cfg["trial"].get("schedule_note") or ""))
        threading.Thread(target=notify.send_all, args=(cfg, "\n".join(lines)), daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        server_version = "tryout-radar"

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _rel(self):
            path = unquote(urlsplit(self.path).path)
            if secret and path == prefix.rstrip("/"):
                return ""
            if not path.startswith(prefix):
                return None
            return path[len(prefix):]

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            rel = self._rel()
            if rel is None:
                return self._send(404, b"Not found", "text/plain; charset=utf-8")
            if rel == "api/trials":
                return self._json(200, store.public_status())
            if rel == "api/feedback":
                return self._json(200, {k: {"status": v.get("status")} for k, v in store.feedback().items()})
            if rel == "api/ignored":
                return self._json(200, {p["key"]: True for p in store.auto_projects() if p.get("status") == "ignored"})
            target = (site / (rel or "index.html")).resolve()
            if target.is_dir():
                target = target / "index.html"
            if site not in target.parents or not target.is_file():
                return self._send(404, b"Not found", "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/"):
                ctype += "; charset=utf-8"
            return self._send(200, target.read_bytes(), ctype)

        def do_POST(self):
            rel = self._rel()
            if rel not in ("api/trial", "api/feedback", "api/project", "api/decide"):
                return self._json(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0 or n > MAX_BODY:
                return self._json(413, {"error": "body too large or empty"})
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"error": "bad json"})
            if rel == "api/feedback":
                ok, res = store.set_feedback(body)
                return self._json(200 if ok else 400, res)
            if rel == "api/decide":
                ok, res, t, new = store.decide(body)
                if ok:
                    S = strings(cfg)
                    res["message"] = S["decided"][t["decision"]["action"]].format(
                        project=project_names(cfg).get(new["project"], new["project"]) if new else "")
                    render.build_site(cfg, store)
                    title = (t.get("item") or {}).get("title") or t["itemId"]
                    threading.Thread(target=notify.send_all, daemon=True, args=(
                        cfg, f"**{res['message']}**\n{title} · {t['decision']['label']}")).start()
                return self._json(200 if ok else 400, res)
            if rel == "api/project":
                ok, res, hit = store.web_ignore_project(body)
                if hit:
                    S = strings(cfg)
                    threading.Thread(target=notify.send_all, args=(cfg, S["ignored_msg"].format(name=hit["name"])),
                                     daemon=True).start()
                return self._json(200 if ok else 400, res)
            ok, res, trial = store.enqueue(body)
            if trial:
                ack(trial)
            return self._json(200 if ok else 400, res)

        def log_message(self, fmt, *args):
            pass

    return Handler


def serve(cfg):
    host, port = cfg["server"]["host"], int(cfg["server"]["port"])
    httpd = ThreadingHTTPServer((host, port), make_handler(cfg))
    sp = cfg["server"]["secret_path"]
    if not sp or "CHANGE-ME" in sp:
        print("Warning: set server.secret_path in config.toml to a long random string before exposing this server.")
    print(f"Tryout Radar serving {cfg['_site']} on http://{host}:{port}/{sp + '/' if sp else ''}")
    httpd.serve_forever()
