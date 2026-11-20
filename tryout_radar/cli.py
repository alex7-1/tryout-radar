"""Command line used by the scout agent, the trial runner agent and you.

  python -m tryout_radar publish REPORT.json|-     save today's digest and rebuild the site
  python -m tryout_radar history [--days N]        items reported recently (for de-duplication)
  python -m tryout_radar feedback                  the owner's marks: {item_id: {status, ...}}
  python -m tryout_radar notify MESSAGE.md|-       send a short Markdown message to every [[notify]] channel
  python -m tryout_radar queue list|adoptions      queued trial requests / trials the owner chose to adopt (JSON)
  python -m tryout_radar queue decide TID OPTION   pick one of a report's options (what the site and panel buttons do)
  python -m tryout_radar queue start|requeue TID   mark a trial running / put it back in the queue
  python -m tryout_radar queue finish TID --result RESULT.json|-
                                                   store the trial result, build its report page, notify
  python -m tryout_radar discover                  what you worked on lately (agent session titles + folders) and
                                                   the known projects, so the scout can spot new ones
  python -m tryout_radar project add PROJECT.json|- [--manual]   add a project (discovered, or by hand)
  python -m tryout_radar project follow|ignore KEY follow / stop following any project
  python -m tryout_radar project list              all projects with source and status
  python -m tryout_radar topic add TOPIC.json|-    add a topic: {"name","keywords","focus","projects":[keys]}
  python -m tryout_radar topic pause|resume KEY    switch a hand-added topic off / on
  python -m tryout_radar topic link KEY --projects a,b   tie a hand-added topic to projects ('' = all)
  python -m tryout_radar topic list                all topics with status and projects
  python -m tryout_radar init [--language zh-CN]   create ~/.tryout-radar/config.toml (once)
  python -m tryout_radar rebuild                   rebuild the whole site
  python -m tryout_radar serve                     serve the site and its button API
  python -m tryout_radar scout [--dry-run|--collect-only] [--no-notify] [--out FILE]
                                                   API mode: the whole daily scout with any model set in [model]
  python -m tryout_radar model check               send one short request to the model in [model]

Global option: --config PATH (default: ./config.toml or $TRYOUT_RADAR_CONFIG).
'-' reads the file from standard input, so the commands also work over ssh."""
import argparse
import json
import sys
from pathlib import Path

from . import config as config_mod
from . import discover as discover_mod
from . import notify, render, server
from .config import project_names
from .store import Store


def _read(path):
    data = sys.stdin.buffer.read() if path == "-" else open(path, "rb").read()
    return data.decode("utf-8-sig")


def _notify(cfg, md):
    res = notify.send_all(cfg, md)
    for typ, ok, msg in res:
        print(f"notify {typ}: {'ok' if ok else 'FAILED - ' + msg}")
    if not res:
        print("notify: no [[notify]] channels configured")
    return all(ok for _, ok, _ in res)


INIT_TEMPLATE = '''# Tryout Radar settings, made by `radar init`. Projects and topics are added with the panel (/radar) or
# `radar project add --manual` / `radar topic add`; you can also write [[projects]] / [[topics]] here
# (see config.example.toml in the plugin folder for every option). Never put secrets here: name environment variables.

language = "{language}"

[site]
title = "Tryout Radar"
base_url = ""                    # https URL of the site when you serve it publicly (see deploy/); used in notifications

[server]
host = "127.0.0.1"
port = 8091
secret_path = "{secret}"

[digest]
min_items = 5
max_items = 15

[trial]
max_per_run = 3
schedule_note = "22:00"

[discovery]
enabled = true
days = 7
max_new_per_day = 2
watch_folders = []
ignore_titles = []
ignore_paths = []
collapse_paths = []

[sources.github]
enabled = true
token_env = "GITHUB_TOKEN"
trending = ["https://github.com/trending?since=daily"]

[sources.x]
mode = "search"
accounts = ["claudeai", "AnthropicAI", "OpenAIDevs"]

[sources.web]
enabled = true

# API mode (optional): any chat model runs the scout with `radar scout`, no coding agent needed.
# Any OpenAI-compatible endpoint works (OpenAI, DeepSeek, Qwen, Kimi, GLM, Gemini, OpenRouter, Ollama, ...).
# [model]
# base_url = "https://api.deepseek.com/v1"
# model = "deepseek-chat"
# api_key_env = "DEEPSEEK_API_KEY"   # the environment variable that holds the key; "" for a local model

# Notifications: uncomment one and set the environment variable it names.
# [[notify]]
# type = "telegram"              # or wecom_webhook, wecom_app, feishu_webhook, slack_webhook, discord_webhook
# token_env = "TELEGRAM_BOT_TOKEN"
# chat_id_env = "TELEGRAM_CHAT_ID"
'''


def init(config_path, language):
    import os
    import secrets
    from pathlib import Path
    path = Path(config_path or os.environ.get("TRYOUT_RADAR_CONFIG")
                or Path(os.environ.get("TRYOUT_RADAR_HOME") or Path.home() / ".tryout-radar") / "config.toml").expanduser()
    if path.exists():
        print(f"already set up: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lang = "zh-CN" if str(language).lower().startswith("zh") else "en"
    path.write_text(INIT_TEMPLATE.format(language=lang, secret=secrets.token_urlsafe(18)), encoding="utf-8")
    for sub in ("data", "site", "sandbox"):
        (path.parent / sub).mkdir(exist_ok=True)
    print(f"created {path}")


def _scout(cfg, a):
    from datetime import date

    from . import collect, llm, scout
    from .store import read_json
    if a.collect_only:
        store = Store(cfg)
        today = date.today().isoformat()
        history = [h for h in store.history(int(cfg["digest"]["dedupe_days"])) if h.get("date") != today]
        state = read_json(Path(cfg["_data"]) / scout.STATE_FILE, {}) or {}
        print("collecting (GitHub search is paced to its rate limit)…", file=sys.stderr)
        got = collect.collect(cfg, history, store.feedback(), state)
        got.pop("state")
        print(json.dumps(got, ensure_ascii=False, indent=1))
        return
    log = lambda s: print(s, file=sys.stderr if a.dry_run else sys.stdout)  # noqa: E731
    try:
        rep = scout.run(cfg, dry_run=a.dry_run, send=not a.no_notify, log=log)
    except llm.ModelError as ex:
        sys.exit(f"scout: {ex}")
    problems = rep.pop("_problems", [])
    if a.out:
        Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.dry_run:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        print("\n" + scout.summary_md(cfg, rep, (cfg["site"].get("base_url") or "") + f"{rep['date']}.html"), file=sys.stderr)
    names = project_names(cfg)
    print(f"\n{rep.get('headline') or ''}")
    by_id = {i["id"]: i for i in rep["items"]}
    for n, pid in enumerate(rep.get("picks") or [], 1):
        it = by_id[pid]
        best = (it.get("projects") or [{}])[0]
        print(f"{n}. {it['title']} -> {names.get(best.get('key'), best.get('key') or '-')}")
    e = rep["engine"]
    print(f"{len(rep['items'])} items from {e['candidates']} candidates ({e['judged']} judged by {e['model']} in "
          f"{e['modelCalls']} calls, {e['seconds']} s)")
    for p in problems:
        print(f"problem: {p}")


def _model_check(cfg):
    import time

    from . import llm
    try:
        c = llm.Client(cfg)
        t0 = time.time()
        res = c.ask_json("Reply with one JSON object only.", 'Reply with {"ok": true, "language": "<the language you write best>"}')
    except (llm.ModelError, ValueError) as ex:
        sys.exit(f"model check failed: {ex}")
    print(f"model ok: {c.model} at {c.url} answered {json.dumps(res, ensure_ascii=False)} in {time.time() - t0:.1f} s"
          + ("" if c.json_mode else " (JSON mode not supported; plain replies are parsed instead)"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tryout_radar", description="Tryout Radar command line")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish")
    p.add_argument("report")
    p = sub.add_parser("history")
    p.add_argument("--days", type=int)
    sub.add_parser("feedback")
    p = sub.add_parser("notify")
    p.add_argument("message")
    p = sub.add_parser("queue")
    p.add_argument("action", choices=["list", "adoptions", "start", "requeue", "finish", "decide"])
    p.add_argument("option", nargs="?", help="decide: the option id from the report")
    p.add_argument("tid", nargs="?")
    p.add_argument("--result")
    sub.add_parser("discover")
    p = sub.add_parser("project")
    p.add_argument("action", choices=["add", "follow", "ignore", "list"])
    p.add_argument("arg", nargs="?")
    p.add_argument("--manual", action="store_true", help="add: a project you add by hand (no daily limit)")
    p = sub.add_parser("topic")
    p.add_argument("action", choices=["add", "pause", "resume", "link", "list"])
    p.add_argument("arg", nargs="?")
    p.add_argument("--projects", default=None, help="link: comma-separated project keys ('' = all projects)")
    sub.add_parser("rebuild")
    sub.add_parser("serve")
    p = sub.add_parser("scout", help="API mode: run the scout with the model in [model]")
    p.add_argument("--dry-run", action="store_true", help="change nothing, send nothing; print the report")
    p.add_argument("--collect-only", action="store_true", help="print today's candidates (no model needed)")
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--out", help="also write the report JSON to this file")
    p = sub.add_parser("model", help="check the [model] settings with one short request")
    p.add_argument("action", choices=["check"])
    p = sub.add_parser("init")
    p.add_argument("--language", default="en")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # output and progress stay UTF-8 on Windows consoles and pipes
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    if a.cmd == "init":
        return init(a.config, a.language)
    cfg = config_mod.load(a.config)
    store = Store(cfg)
    base = cfg["site"].get("base_url") or ""

    if a.cmd == "publish":
        rep = json.loads(_read(a.report))
        try:
            url = render.publish(cfg, store, rep)   # also records every project and topic's state for the panel
        except ValueError as ex:
            sys.exit(f"Report not saved: {ex}")
        print(f"published {rep['date']} ({len(rep.get('items') or [])} items) -> {url}")
    elif a.cmd == "scout":
        return _scout(cfg, a)
    elif a.cmd == "model":
        return _model_check(cfg)
    elif a.cmd == "history":
        print(json.dumps(store.history(a.days or int(cfg["digest"]["dedupe_days"])), ensure_ascii=False, indent=1))
    elif a.cmd == "feedback":
        print(json.dumps(store.feedback(), ensure_ascii=False, indent=1))
    elif a.cmd == "notify":
        if not _notify(cfg, _read(a.message)):
            sys.exit(1)
    elif a.cmd == "queue":
        if a.action in ("list", "adoptions"):
            want = "queued" if a.action == "list" else "adopt-requested"
            print(json.dumps([t for t in store.trials() if t["status"] == want], ensure_ascii=False, indent=1))
            return
        if not a.tid:
            sys.exit("queue start/requeue/finish needs a trial id")
        try:
            if a.action in ("start", "requeue"):
                t = store.set_trial_status(a.tid, "running" if a.action == "start" else "queued")
                print(f"{t['tid']} -> {t['status']}")
                return
            if a.action == "decide":
                ok, res, t, new = store.decide({"tid": a.tid, "option": a.option or ""})
                if not ok:
                    sys.exit(res["error"])
                render.build_site(cfg, store)
                print(f"{t['tid']} -> {t['status']}" + (f" (new request {new['tid']})" if new else ""))
                return
            if not a.result:
                sys.exit("queue finish needs --result FILE (or -)")
            t = store.finish(a.tid, json.loads(_read(a.result)))
        except ValueError as ex:
            sys.exit(str(ex))
        render.build_site(cfg, store)
        S = render.strings(cfg)
        url = f"{base}trials/{t['tid']}.html"
        title = (t.get("item") or {}).get("title") or t["itemId"]
        verdict = f" · **{S['tverdict'][t['verdict']]}**" if t.get("verdict") and t["status"] == "done" else ""
        plain = t.get("plain") or {}
        ask = f"> {S['ask']}: {plain['ask']}\n" if plain.get("ask") else ""
        md = (f"**{S['report']}** ({S['status'].get(t['status'], t['status'])}){verdict}\n"
              f"{title} → {project_names(cfg).get(t['project'], t['project'])}\n"
              f"{plain.get('headline') or t.get('summary', '')}\n{ask}[{url}]({url})")
        print(f"finished {t['tid']} -> {url}")
        _notify(cfg, md)
    elif a.cmd == "discover":
        dc = cfg["discovery"]
        if not dc.get("enabled", True):
            print(json.dumps({"disabled": True}))
            return
        found = discover_mod.discover(int(dc.get("days", 7)), dc.get("watch_folders", []), dc.get("ignore_titles", []),
                                      list(dc.get("ignore_paths", [])) + [str(cfg["_root"])], dc.get("collapse_paths", []))
        found["known_projects"] = [
            {"key": p["key"], "name": p["name"], "path": p.get("path", ""), "status": st, "source": p.get("source")}
            for st, ps in (("active", cfg["projects"]), ("ignored", cfg["_ignored_projects"])) for p in ps]
        found["max_new_per_day"] = int(dc.get("max_new_per_day", 2))
        print(json.dumps(found, ensure_ascii=False, indent=1))
    elif a.cmd == "project":
        try:
            if a.action == "list":
                print(json.dumps([dict(p, status=st) for st, ps in (("active", cfg["projects"]), ("ignored", cfg["_ignored_projects"]))
                                  for p in ps], ensure_ascii=False, indent=1, default=str))
            elif a.action == "add":
                if not a.arg:
                    sys.exit("project add needs a JSON file (or -)")
                p = store.add_project(json.loads(_read(a.arg)), source="manual" if a.manual else "discovered")
                print(f"added {p['key']} ({p['name']})")
            else:
                if not a.arg:
                    sys.exit(f"project {a.action} needs a key")
                p = store.set_project_status(a.arg, "active" if a.action == "follow" else "ignored")
                print(f"{a.arg}: {'following' if a.action == 'follow' else 'not following'}")
        except ValueError as ex:
            sys.exit(str(ex))
    elif a.cmd == "topic":
        try:
            if a.action == "list":
                print(json.dumps([dict(t, status=st) for st, ts in (("active", cfg["topics"]), ("paused", cfg["_paused_topics"]))
                                  for t in ts], ensure_ascii=False, indent=1))
            elif a.action == "add":
                if not a.arg:
                    sys.exit('topic add needs a JSON file (or -): {"name", "keywords", "focus", "projects": [keys]}')
                t = store.add_topic(json.loads(_read(a.arg)))
                print(f"added topic {t['key']} ({t['name']})")
            else:
                if not a.arg:
                    sys.exit(f"topic {a.action} needs a key")
                if a.action == "link":
                    keys = [k.strip() for k in (a.projects or "").split(",") if k.strip()]
                    t = store.set_topic(a.arg, projects=keys)
                else:
                    t = store.set_topic(a.arg, status="paused" if a.action == "pause" else "active")
                print(f"topic {t['key']}: {t['status']}, projects: {', '.join(t['projects']) or 'all'}")
        except ValueError as ex:
            sys.exit(str(ex))
    elif a.cmd == "rebuild":
        dates = render.build_site(cfg, store)
        print(f"rebuilt {len(dates)} day pages in {cfg['_site']}")
    elif a.cmd == "serve":
        server.serve(cfg)
