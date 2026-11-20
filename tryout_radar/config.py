"""Load config.toml, fill defaults and resolve paths relative to the config file."""
import json
import os
import re
import tomllib
from pathlib import Path

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

DEFAULTS = {
    "language": "en",
    "paths": {"data_dir": "data", "site_dir": "site", "sandbox_dir": "sandbox"},
    "site": {"title": "Tryout Radar", "base_url": ""},
    "digest": {"min_items": 5, "max_items": 15, "lookback_hours": 72, "dedupe_days": 14, "summary_max_bytes": 1500},
    "trial": {"max_per_run": 3, "daily_request_limit": 10, "minutes_per_trial": 40, "schedule_note": "22:00",
              "extra_stop_rules": []},
    "server": {"host": "127.0.0.1", "port": 8091, "secret_path": ""},
    "discovery": {"enabled": True, "days": 7, "max_new_per_day": 2, "watch_folders": [], "ignore_titles": [],
                  "ignore_paths": [], "collapse_paths": []},
    # API mode (`radar scout`): any chat model behind an OpenAI-compatible API does the judging; code does the rest.
    "model": {"base_url": "", "model": "", "api_key_env": "", "temperature": 0.2, "timeout": 180, "json_mode": True,
              "max_tokens": 0},
    "scout": {"max_candidates": 40, "batch_size": 12, "excerpt_chars": 1000, "check_links": True},
    "sources": {"github": {"enabled": True, "token_env": "GITHUB_TOKEN", "trending": [], "max_requests": 24},
                "x": {"mode": "search", "accounts": []},
                "web": {"enabled": True},
                "hn": {"enabled": True, "min_points": 30},
                "search": {"provider": "none", "url": "", "key_env": "", "max_requests": 12}},
}
# Files in data_dir that the panel, the site and the CLI change, so nobody has to edit config.toml for them:
AUTO_FILE = "projects.auto.json"         # projects added later: discovered by the scout or added by hand
OVERRIDES_FILE = "project-overrides.json"  # {key: "active" | "ignored"} for projects written in config.toml
TOPICS_FILE = "topics.custom.json"       # topics added by hand, each optionally tied to some projects


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (FileNotFoundError, ValueError):
        return default


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load(path=None):
    path = Path(path or os.environ.get("TRYOUT_RADAR_CONFIG") or "config.toml").expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Config not found: {path}\nCopy config.example.toml to config.toml and edit it.")
    with open(path, "rb") as f:
        cfg = _merge(DEFAULTS, tomllib.load(f))
    root = path.parent
    cfg["_root"] = root
    for name in ("data_dir", "site_dir", "sandbox_dir"):
        cfg["_" + name.split("_")[0]] = (root / Path(cfg["paths"][name]).expanduser()).resolve()
    # Projects: config.toml's, minus the ones switched off from the panel or site, plus the ones added later.
    # Switched-off projects are kept in cfg["_ignored_projects"] so they are never re-added or re-suggested.
    overrides = _read_json(cfg["_data"] / OVERRIDES_FILE, {})
    active, ignored = [], []
    for p in cfg.get("projects", []):
        p.setdefault("source", "config")
        (ignored if overrides.get(p.get("key")) == "ignored" else active).append(p)
    known = {p.get("key") for p in active + ignored}
    for p in _read_json(cfg["_data"] / AUTO_FILE, []):
        if isinstance(p, dict) and p.get("key") not in known:
            p = dict(p, source=p.get("source") if p.get("source") in ("discovered", "manual") else "discovered")
            (active if p.get("status", "active") == "active" else ignored).append(p)
            known.add(p.get("key"))
    cfg["projects"], cfg["_ignored_projects"] = active, ignored
    # Topics: config.toml's plus the ones added by hand (paused ones kept aside the same way).
    cfg.setdefault("topics", [])
    for t in cfg["topics"]:
        t.setdefault("source", "config")
    cfg["_paused_topics"] = []
    tkeys = {t.get("key") for t in cfg["topics"]}
    for t in _read_json(cfg["_data"] / TOPICS_FILE, []):
        if isinstance(t, dict) and KEY_RE.match(str(t.get("key", ""))) and t["key"] not in tkeys:
            t = dict(t, source="custom")
            (cfg["topics"] if t.get("status", "active") == "active" else cfg["_paused_topics"]).append(t)
            tkeys.add(t["key"])
    seen = set()
    for p in cfg.get("projects", []):
        if not KEY_RE.match(str(p.get("key", ""))):
            raise SystemExit(f"Project key {p.get('key')!r} must be lowercase letters, digits or '-' (max 40).")
        if p["key"] in seen:
            raise SystemExit(f"Duplicate project key {p['key']!r}.")
        seen.add(p["key"])
        p.setdefault("name", p["key"])
        p.setdefault("trial_mode", "assess")
        if p["trial_mode"] not in ("try", "assess", "off"):
            raise SystemExit(f"Project {p['key']}: trial_mode must be try, assess or off.")
    for t in cfg.get("topics", []) + cfg["_paused_topics"]:
        if not KEY_RE.match(str(t.get("key", ""))):
            raise SystemExit(f"Topic key {t.get('key')!r} must be lowercase letters, digits or '-' (max 40).")
        t.setdefault("name", t["key"])
        t.setdefault("projects", [])        # project keys this topic is mainly for; empty = all projects
    sp = str(cfg["server"].get("secret_path") or "").strip("/")
    if sp and not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", sp):
        raise SystemExit("server.secret_path must be 8-128 letters, digits, '-' or '_'.")
    cfg["server"]["secret_path"] = sp
    return cfg


def env(name):
    """Value of the environment variable called `name`, or None."""
    return os.environ.get(name) if name else None


def project_names(cfg):
    return {p["key"]: p["name"] for p in cfg.get("projects", [])}


def project(cfg, key):
    return next((p for p in cfg.get("projects", []) if p["key"] == key), None)


def slug(name, prefix="p"):
    """A key from a name: ASCII words joined by '-', or prefix + time when the name has none (e.g. Chinese)."""
    import time
    name = str(name)
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-")
    letters = len(re.sub(r"\s", "", name)) or 1
    mostly_ascii = len(re.findall(r"[A-Za-z0-9]", name)) / letters >= 0.5
    return s if mostly_ascii and len(s) >= 3 and KEY_RE.match(s) else f"{prefix}-{int(time.time()):x}"


def topic_names(cfg):
    names = {t["key"]: t["name"] for t in cfg.get("topics", [])}
    names.setdefault("other", "Other" if cfg.get("language", "en") == "en" else "其他")
    return names
