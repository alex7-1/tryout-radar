"""File-based storage under data_dir: daily reports, feedback marks and the trial queue.

data/
  reports/<YYYY-MM-DD>.json   one digest per day (the JSON the scout agent writes)
  feedback.json               {item_id: {status, title, url, category, date, updatedAt}}
  trials/<tid>.json           one trial request each (queued -> running -> done | blocked | failed)
All writes are atomic (write temp file, then rename)."""
import json
import os
import re
import threading
import time
from datetime import date, timedelta
from pathlib import Path

from .config import AUTO_FILE, KEY_RE, OVERRIDES_FILE, TOPICS_FILE, project, project_names, slug

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
TID_RE = re.compile(r"^\d{8}-\d{6}-[a-z0-9-]{1,40}$")
FEEDBACK = ("want", "done", "skip")
TRIAL_STATES = ("queued", "running", "done", "blocked", "failed", "closed", "adopt-requested", "adopting", "adopted")
VERDICTS = ("adopt", "reject", "decide")
DECIDABLE = ("done", "blocked", "failed", "adopted")   # states where the owner picks one of the report's options
ACTIONS = ("continue", "retarget", "close", "adopt")


def _one_line(s, n):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def clean_plain(p, summary=""):
    """The part of a report written for the owner: a plain headline, what is good, what is not, cost, the question."""
    p = p if isinstance(p, dict) else {}
    lst = lambda v: [_one_line(x, 200) for x in (v if isinstance(v, list) else []) if _one_line(x, 200)][:3]  # noqa: E731
    return {"headline": _one_line(p.get("headline") or summary, 240), "good": lst(p.get("good")), "bad": lst(p.get("bad")),
            "cost": _one_line(p.get("cost"), 200), "ask": _one_line(p.get("ask"), 240)}


DEFAULT_OPTION_TEXT = {   # label, effect of the choices added when the trial runner's report leaves them out
    "en": {"close": ("Not now", "This trial ends here; its files stay."),
           "retry": ("Try again", "Runs again at the next trial run."),
           "adopt": ("Adopt", "The trial runner merges it locally through the project's own process at its next run; "
                              "no push, no deploy.")},
    "zh": {"close": ("先不用", "这次试用到此结束，文件留着。"),
           "retry": ("再试一次", "下次试用时重新跑一遍。"),
           "adopt": ("采纳", "试用员下次运行时按项目自己的流程在本机合并；不推送、不上线。")},
}


def default_options(t, lang="en"):
    """Choices the report always offers: a way out, adopt for an adopt verdict, retry for a failure."""
    tx = DEFAULT_OPTION_TEXT["zh" if str(lang or "").lower().startswith("zh") else "en"]
    close = {"id": "close", "label": tx["close"][0], "action": "close", "effect": tx["close"][1]}
    if t["status"] == "failed":
        return [{"id": "retry", "label": tx["retry"][0], "action": "continue", "approval": "", "effect": tx["retry"][1]}, close]
    if t["status"] == "done" and t.get("verdict") == "adopt":
        return [{"id": "adopt", "label": tx["adopt"][0], "action": "adopt", "effect": tx["adopt"][1]}, close]
    return [close] if t["status"] in DECIDABLE else []


def clean_options(opts, t, lang="en"):
    out = []
    for o in opts if isinstance(opts, list) else []:
        if not isinstance(o, dict) or o.get("action") not in ACTIONS:
            continue
        oid = str(o.get("id") or "")
        if not re.fullmatch(r"[a-z0-9-]{1,30}", oid) or oid in {x["id"] for x in out}:
            continue
        if o["action"] == "retarget" and not KEY_RE.match(str(o.get("project") or "")):
            continue
        out.append({"id": oid, "label": re.sub(r"[<>\[\]`*]", "", _one_line(o.get("label") or oid, 30)),
                    "effect": _one_line(o.get("effect"), 200), "action": o["action"], "project": str(o.get("project") or ""),
                    "approval": _one_line(o.get("approval"), 600)})
    have = {o["action"] for o in out}
    for d in default_options(t, lang):
        if d["action"] not in have and d["id"] not in {o["id"] for o in out}:
            out.append(dict(d, project="", approval=d.get("approval", "")))
    return out[:5]
LOCK = threading.Lock()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def clean_text(s, limit):
    """One line of user text: no markup characters, collapsed whitespace, limited length."""
    return re.sub(r"\s+", " ", re.sub(r"[<>\[\]`*]", "", str(s or ""))).strip()[:limit]


class Store:
    def __init__(self, cfg):
        self.cfg = cfg
        self.dir = Path(cfg["_data"])
        self.reports = self.dir / "reports"
        self.trials_dir = self.dir / "trials"

    # ---------- reports ----------
    def save_report(self, rep):
        if not isinstance(rep, dict) or not DATE_RE.match(str(rep.get("date", ""))):
            raise ValueError("report needs a 'date' in YYYY-MM-DD form")
        items = rep.get("items")
        if not isinstance(items, list):
            raise ValueError("report needs an 'items' list")
        for it in items:
            if not ID_RE.match(str(it.get("id", ""))):
                raise ValueError(f"item id {it.get('id')!r} must match {ID_RE.pattern}")
        write_json(self.reports / f"{rep['date']}.json", rep)

    def report_dates(self):
        if not self.reports.is_dir():
            return []
        return sorted((p.stem for p in self.reports.glob("*.json") if DATE_RE.match(p.stem)), reverse=True)

    def load_report(self, d):
        return read_json(self.reports / f"{d}.json")

    def find_item(self, d, item_id):
        rep = self.load_report(d) if DATE_RE.match(str(d)) else None
        return next((i for i in (rep or {}).get("items") or [] if str(i.get("id")) == item_id), None)

    def history(self, days):
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        out = []
        for d in self.report_dates():
            if d < cutoff:
                break
            rep = self.load_report(d) or {}
            for it in rep.get("items") or []:
                out.append({"date": d, "id": it.get("id"), "url": it.get("url"), "title": it.get("title")})
            for sec in rep.get("sections") or []:
                for c in sec.get("cards") or []:
                    out.append({"date": d, "section": sec.get("title"), "title": c.get("title")})
        return out

    def prune(self, keep=120):
        """Keep the newest `keep` reports (by count, so an old example report is never deleted on publish)."""
        for d in self.report_dates()[keep:]:
            (self.reports / f"{d}.json").unlink(missing_ok=True)

    # ---------- feedback ----------
    def feedback(self):
        return read_json(self.dir / "feedback.json", {}) or {}

    def set_feedback(self, body):
        if not isinstance(body, dict):
            return False, {"error": "bad request"}
        iid, d, status = str(body.get("id", "")), str(body.get("date", "")), body.get("status")
        if not ID_RE.match(iid) or (status is not None and status not in FEEDBACK):
            return False, {"error": "bad request"}
        item = self.find_item(d, iid)
        if not item:
            return False, {"error": "item not found"}
        with LOCK:
            fb = self.feedback()
            if status is None:
                fb.pop(iid, None)
            else:
                fb[iid] = {"status": status, "title": str(item.get("title") or "")[:300], "url": str(item.get("url") or ""),
                           "category": str(item.get("category") or ""), "date": d, "updatedAt": now()}
            write_json(self.dir / "feedback.json", fb)
        return True, {"id": iid, "status": status}

    # ---------- discovered projects ----------
    def auto_projects(self):
        data = read_json(self.dir / AUTO_FILE, [])
        return data if isinstance(data, list) else []

    def all_project_keys(self):
        return ({p.get("key") for p in self.cfg.get("projects", []) + self.cfg.get("_ignored_projects", [])}
                | {q.get("key") for q in self.auto_projects()})

    def add_project(self, p, source="discovered"):
        """Add a project: one the scout discovered, or one added by hand (source="manual").
        Returns the stored entry; raises ValueError on bad input. A key used before, even by a project you
        stopped following, is refused, so the scout never brings back what you switched off."""
        if not isinstance(p, dict):
            raise ValueError("project must be a JSON object")
        name = clean_text(p.get("name"), 40)
        if not name:
            raise ValueError("name is required")
        key = str(p.get("key") or (slug(name) if source == "manual" else ""))
        if not KEY_RE.match(key):
            raise ValueError("key must be lowercase letters, digits or '-' (max 40)")
        if key in self.all_project_keys():
            raise ValueError(f"project {key!r} already exists (or was switched off before)")
        today = date.today().isoformat()
        auto = self.auto_projects()
        if source == "discovered":
            limit = int(self.cfg["discovery"].get("max_new_per_day", 2))
            if sum(1 for q in auto if q.get("found") == today and q.get("source", "discovered") == "discovered") >= limit:
                raise ValueError(f"already added {limit} projects today (discovery.max_new_per_day)")
        mode = p.get("trial_mode", "assess")
        if mode not in ("try", "assess", "off"):
            raise ValueError("trial_mode must be try, assess or off")
        entry = {"key": key, "name": name, "parent": str(p.get("parent") or ""), "path": str(p.get("path") or ""),
                 "about": str(p.get("about") or "")[:1000], "interests": [str(x)[:80] for x in p.get("interests") or []][:10],
                 "rules_files": [str(x)[:120] for x in p.get("rules_files") or []][:5], "trial_mode": mode,
                 "why": str(p.get("why") or "")[:300], "found": today, "status": "active", "source": source}
        with LOCK:
            write_json(self.dir / AUTO_FILE, self.auto_projects() + [entry])
        return entry

    def set_project_status(self, key, status):
        """Follow ("active") or stop following ("ignored") any project: added later or written in config.toml."""
        if status not in ("active", "ignored"):
            raise ValueError("status must be active or ignored")
        with LOCK:
            auto = self.auto_projects()
            hit = next((q for q in auto if q.get("key") == key), None)
            if hit:
                hit.update({"status": status, "changedAt": now()})
                write_json(self.dir / AUTO_FILE, auto)
                return hit
            hit = next((q for q in self.cfg.get("projects", []) + self.cfg.get("_ignored_projects", [])
                        if q.get("key") == key), None)
            if not hit:
                raise ValueError(f"no project {key!r}")
            ov = read_json(self.dir / OVERRIDES_FILE, {}) or {}
            ov[key] = status
            write_json(self.dir / OVERRIDES_FILE, ov)
        return dict(hit, status=status)

    def ignore_project(self, key):
        return self.set_project_status(key, "ignored")

    # ---------- topics added by hand ----------
    def custom_topics(self):
        data = read_json(self.dir / TOPICS_FILE, [])
        return data if isinstance(data, list) else []

    def add_topic(self, t):
        """A topic to watch, optionally tied to some projects: {name, focus?, keywords?, projects?: [keys]}."""
        if not isinstance(t, dict):
            raise ValueError("topic must be a JSON object")
        name = clean_text(t.get("name"), 40)
        if not name:
            raise ValueError("name is required")
        key = str(t.get("key") or slug(name, "t"))
        if not KEY_RE.match(key):
            raise ValueError("key must be lowercase letters, digits or '-' (max 40)")
        if key in {x.get("key") for x in self.cfg.get("topics", []) + self.cfg.get("_paused_topics", []) + self.custom_topics()}:
            raise ValueError(f"topic {key!r} already exists")
        keywords = t.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [k for k in re.split(r"[,，;；\n]+", keywords)]
        keywords = [clean_text(k, 60) for k in keywords if clean_text(k, 60)][:12]
        projects = [str(k) for k in t.get("projects") or []]
        unknown = [k for k in projects if k not in self.all_project_keys()]
        if unknown:
            raise ValueError(f"unknown project keys: {', '.join(unknown)}")
        entry = {"key": key, "name": name, "focus": str(t.get("focus") or "")[:500], "github_queries": keywords,
                 "x_queries": keywords, "watch": [u for u in (t.get("watch") or []) if str(u).startswith("http")][:10],
                 "projects": projects, "status": "active", "added": date.today().isoformat()}
        with LOCK:
            write_json(self.dir / TOPICS_FILE, self.custom_topics() + [entry])
        return entry

    def set_topic(self, key, **changes):
        """Pause/resume a hand-added topic (status) or change which projects it is for (projects)."""
        with LOCK:
            topics = self.custom_topics()
            hit = next((x for x in topics if x.get("key") == key), None)
            if not hit:
                raise ValueError(f"no hand-added topic {key!r} (topics from config.toml are changed there)")
            if "status" in changes:
                if changes["status"] not in ("active", "paused"):
                    raise ValueError("status must be active or paused")
                hit["status"] = changes["status"]
            if "projects" in changes:
                unknown = [k for k in changes["projects"] if k not in self.all_project_keys()]
                if unknown:
                    raise ValueError(f"unknown project keys: {', '.join(unknown)}")
                hit["projects"] = list(changes["projects"])
            write_json(self.dir / TOPICS_FILE, topics)
        return hit

    def web_ignore_project(self, body):
        """The site's "Stop following" button. Only works for projects listed as new in that day's digest."""
        if not isinstance(body, dict):
            return False, {"error": "bad request"}, None
        key, rep = str(body.get("key", "")), self.load_report(body.get("date")) if DATE_RE.match(str(body.get("date", ""))) else None
        if not rep or key not in {str(p.get("key")) for p in rep.get("newProjects") or []}:
            return False, {"error": "not a newly discovered project"}, None
        try:
            hit = self.ignore_project(key)
        except ValueError as ex:
            return False, {"error": str(ex)}, None
        return True, {"key": key, "status": "ignored"}, hit

    # ---------- trials ----------
    def trials(self):
        if not self.trials_dir.is_dir():
            return []
        out = []
        for p in sorted(self.trials_dir.glob("*.json")):
            t = read_json(p)
            if isinstance(t, dict) and TID_RE.match(str(t.get("tid", ""))):
                out.append(t)
        return out

    def trial(self, tid):
        if not TID_RE.match(str(tid)):
            raise ValueError(f"bad trial id {tid!r}")
        t = read_json(self.trials_dir / f"{tid}.json")
        if not t:
            raise ValueError(f"no trial {tid}")
        return t

    def save_trial(self, t):
        write_json(self.trials_dir / f"{t['tid']}.json", t)

    def enqueue(self, body):
        """Called by the site's 'Try it' button. Returns (ok, response, trial or None)."""
        if not isinstance(body, dict):
            return False, {"error": "bad request"}, None
        d, iid, key = str(body.get("date", "")), str(body.get("id", "")), str(body.get("project", ""))
        if not ID_RE.match(iid):
            return False, {"error": "item not found"}, None
        proj = project(self.cfg, key)
        if not proj:
            return False, {"error": "unknown project"}, None
        if proj["trial_mode"] == "off":
            return False, {"error": "trials are off for this project"}, None
        item = self.find_item(d, iid)
        if not item:
            return False, {"error": "item not found"}, None
        note = clean_text(body.get("note"), 300)
        limit = int(self.cfg["trial"]["daily_request_limit"])
        with LOCK:
            ts = self.trials()
            for t in ts:
                if t["itemId"] == iid and t["project"] == key and t["status"] in ("queued", "running"):
                    return True, {"tid": t["tid"], "status": t["status"], "duplicate": True}, None
            today = time.strftime("%Y-%m-%d")
            if sum(1 for t in ts if str(t.get("createdAt", "")).startswith(today)) >= limit:
                return False, {"error": f"daily limit of {limit} requests reached"}, None
            tid = time.strftime("%Y%m%d-%H%M%S") + "-" + key
            while (self.trials_dir / f"{tid}.json").exists():
                time.sleep(1)
                tid = time.strftime("%Y%m%d-%H%M%S") + "-" + key
            keep = {k: item.get(k) for k in ("title", "url", "source", "author", "category", "summary", "projects",
                                             "effort", "verdict", "caution")}
            t = {"tid": tid, "status": "queued", "createdAt": now(), "updatedAt": now(), "date": d, "itemId": iid,
                 "project": key, "mode": proj["trial_mode"], "note": note, "item": keep}
            self.save_trial(t)
        return True, {"tid": tid, "status": "queued"}, t

    def set_trial_status(self, tid, status):
        with LOCK:
            t = self.trial(tid)
            if t["status"] in ("adopt-requested", "adopting"):   # an adoption keeps its own states
                status = {"running": "adopting", "queued": "adopt-requested"}.get(status, status)
            t["status"] = status
            t["updatedAt"] = now()
            self.save_trial(t)
        return t

    def finish(self, tid, res):
        if res.get("status") not in ("done", "blocked", "failed", "adopted"):
            raise ValueError("result status must be done, blocked, failed or adopted")
        with LOCK:
            t = self.trial(tid)
            t.update({"status": res["status"], "verdict": res.get("verdict") if res.get("verdict") in VERDICTS else None,
                      "summary": str(res.get("summary") or "")[:500], "report_md": str(res.get("report_md") or "")[:60000],
                      "branch": str(res.get("branch") or t.get("branch") or "")[:200],
                      "sandbox": str(res.get("sandbox") or t.get("sandbox") or "")[:300], "finishedAt": now(), "updatedAt": now()})
            t["plain"] = clean_plain(res.get("plain"), t["summary"])
            t["options"] = clean_options(res.get("options"), t, self.cfg.get("language"))
            if t.get("decision"):
                t.setdefault("history", []).append(t.pop("decision"))
            self.save_trial(t)
        return t

    def decide(self, body):
        """The owner picks one of a report's options (site button, panel button or CLI).
        Returns (ok, response, trial, new_trial). continue: back in the queue with the owner's approval;
        retarget: a new request for another project; close: ends it; adopt: waits for the trial runner to merge."""
        if not isinstance(body, dict):
            return False, {"error": "bad request"}, None, None
        tid, oid = str(body.get("tid", "")), str(body.get("option", ""))
        if not TID_RE.match(tid):
            return False, {"error": "no such trial"}, None, None
        new = None
        with LOCK:
            try:
                t = self.trial(tid)
            except ValueError:
                return False, {"error": "no such trial"}, None, None
            if t.get("decision"):
                return False, {"error": f"already chosen: {t['decision'].get('label')}"}, None, None
            if t["status"] not in DECIDABLE:
                return False, {"error": "nothing to choose for this trial now"}, None, None
            opt = next((o for o in t.get("options") or clean_options([], t, self.cfg.get("language")) if o["id"] == oid), None)
            if not opt:
                return False, {"error": "no such option"}, None, None
            if opt["action"] == "retarget":
                target = project(self.cfg, opt["project"])
                if not target or target["trial_mode"] == "off":
                    return False, {"error": "that project is not available for trials"}, None, None
                new = {"tid": time.strftime("%Y%m%d-%H%M%S") + "-" + target["key"], "status": "queued", "createdAt": now(),
                       "updatedAt": now(), "date": t["date"], "itemId": t["itemId"], "project": target["key"],
                       "mode": target["trial_mode"], "note": f"moved from {t['project']}: {opt['label']}", "item": t.get("item") or {}}
                self.save_trial(new)
                t["status"] = "closed"
            elif opt["action"] == "close":
                t["status"] = "closed"
            elif opt["action"] == "adopt":
                t["status"] = "adopt-requested"
            else:
                t["status"] = "queued"
                t.setdefault("approvals", []).append({"text": opt.get("approval", ""), "label": opt["label"], "at": now()})
            t["decision"] = {"option": oid, "label": opt["label"], "action": opt["action"], "at": now()}
            t["updatedAt"] = now()
            self.save_trial(t)
        return True, {"status": t["status"], "newTid": new["tid"] if new else None}, t, new

    def public_status(self):
        """Latest trial per (item, project), without report text."""
        names = project_names(self.cfg)
        latest = {}
        for t in self.trials():
            k = (t["itemId"], t["project"])
            if k not in latest or t["createdAt"] > latest[k]["createdAt"]:
                latest[k] = t
        out = {}
        for (iid, key), t in latest.items():
            out.setdefault(iid, []).append({
                "project": key, "projectName": names.get(key, key), "status": t["status"], "verdict": t.get("verdict"),
                "report": f"trials/{t['tid']}.html" if t.get("finishedAt") else None})
        return out
