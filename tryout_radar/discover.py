"""List what you have been working on recently, so the scout can spot new projects.

Reads metadata only, never message content:
  - Claude Code sessions: ~/.claude/projects/*/*.jsonl -> session title ("custom-title" / "summary" lines) and working folder ("cwd")
  - Codex sessions: ~/.codex/sessions/YYYY/MM/DD/*.jsonl -> working folder from the session_meta line
  - new folders created directly under the folders you list in `watch_folders`

Output (JSON): {"since": ..., "workspaces": [{"cwd", "titles", "claude_sessions", "codex_sessions", "last_active"}],
                "new_folders": [{"path", "created"}]}
Usable on its own:  python -m tryout_radar.discover --days 7 --watch ~/code --ignore-title "^\\[cron\\]" """
import argparse
import json
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

WORKTREE_RE = re.compile(r"[\\/]\.claude[\\/]worktrees[\\/].*$", re.I)   # Claude Code worktrees live inside the project


def _norm(cwd):
    """Map agent worktrees back to their project folder and normalise separators."""
    cwd = WORKTREE_RE.sub("", str(cwd or "").strip())
    return cwd.rstrip("\\/")


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


def claude_sessions(home, cutoff):
    out = []
    root = home / ".claude" / "projects"
    if not root.is_dir():
        return out
    for f in root.glob("*/*.jsonl"):
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue
        cwd, title = None, None
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if cwd is None and '"cwd"' in line:
                        m = re.search(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', line)
                        if m:
                            cwd = json.loads(f'"{m.group(1)}"')
                    if '"custom-title"' in line or '"type":"summary"' in line or '"type": "summary"' in line:
                        try:
                            j = json.loads(line)
                        except ValueError:
                            continue
                        title = j.get("customTitle") or j.get("summary") or j.get("title") or title
        except OSError:
            continue
        if cwd:
            out.append({"cwd": _norm(cwd), "title": (title or "").strip()[:120], "at": mtime})
    return out


def codex_sessions(home, since_day):
    out = []
    root = home / ".codex" / "sessions"
    d = since_day
    while d <= date.today():
        day_dir = root / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
        if day_dir.is_dir():
            for f in day_dir.glob("*.jsonl"):
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        first = fh.readline(2_000_000)
                    m = re.search(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', first)
                    if m:
                        out.append({"cwd": _norm(json.loads(f'"{m.group(1)}"')), "at": f.stat().st_mtime})
                except (OSError, ValueError):
                    continue
        d += timedelta(days=1)
    return out


def new_folders(watch, cutoff):
    out = []
    for w in watch:
        root = Path(os.path.expanduser(w))
        if not root.is_dir():
            continue
        for child in root.iterdir():
            try:
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if (child / ".git").is_file():          # a git worktree of another project, not a new project
                    continue
                created = child.stat().st_ctime         # creation time on Windows, metadata change time elsewhere
            except OSError:
                continue
            if created >= cutoff:
                out.append({"path": str(child), "created": _iso(created)})
    return sorted(out, key=lambda x: x["created"], reverse=True)


def _under(path, roots):
    c = path.lower()
    return next((r for r in roots if c == r.lower() or c.startswith(r.lower() + "\\") or c.startswith(r.lower() + "/")), None)


def discover(days=7, watch=(), ignore_titles=(), ignore_paths=(), collapse=(), home=None):
    """collapse: folders whose many per-session subfolders (e.g. throwaway workspaces) count as one workspace."""
    home = Path(home or Path.home())
    cutoff = time.time() - days * 86400
    since_day = date.today() - timedelta(days=days)
    title_res = [re.compile(p) for p in ignore_titles]
    ignore = [_norm(os.path.expanduser(p)) for p in ignore_paths]
    collapse = [_norm(os.path.expanduser(p)) for p in collapse]

    def ignored(cwd):
        return _under(cwd, ignore) is not None

    ws = {}
    for s in claude_sessions(home, cutoff):
        if ignored(s["cwd"]) or any(r.search(s["title"]) for r in title_res):
            continue
        root = _under(s["cwd"], collapse)
        if root:
            s["cwd"] = root + " (each session its own folder)"
        w = ws.setdefault(s["cwd"].lower(), {"cwd": s["cwd"], "titles": [], "claude_sessions": 0, "codex_sessions": 0, "at": 0})
        w["claude_sessions"] += 1
        w["at"] = max(w["at"], s["at"])
        if s["title"] and s["title"] not in w["titles"]:
            w["titles"].append(s["title"])
    for s in codex_sessions(home, since_day):
        if ignored(s["cwd"]):
            continue
        root = _under(s["cwd"], collapse)
        if root:
            s["cwd"] = root + " (each session its own folder)"
        w = ws.setdefault(s["cwd"].lower(), {"cwd": s["cwd"], "titles": [], "claude_sessions": 0, "codex_sessions": 0, "at": 0})
        w["codex_sessions"] += 1
        w["at"] = max(w["at"], s["at"])
    workspaces = []
    for w in sorted(ws.values(), key=lambda x: x["at"], reverse=True):
        w["last_active"] = _iso(w.pop("at"))
        w["titles"] = w["titles"][:40]
        workspaces.append(w)
    return {"since": since_day.isoformat(), "workspaces": workspaces,
            "new_folders": [f for f in new_folders(watch, cutoff) if not ignored(f["path"])]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="List recent agent work (titles and folders only).")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--watch", action="append", default=[], help="folder whose new subfolders count as new projects")
    ap.add_argument("--ignore-title", action="append", default=[], help="regex; matching session titles are skipped")
    ap.add_argument("--ignore-path", action="append", default=[], help="folder to skip (and everything below it)")
    ap.add_argument("--collapse", action="append", default=[], help="folder whose per-session subfolders count as one")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(discover(a.days, a.watch, a.ignore_title, a.ignore_path, a.collapse), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
