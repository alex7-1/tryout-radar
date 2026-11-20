# Scheduling the two agents

Tryout Radar is two agent prompts plus a small tool. You need an agent that can read files, fetch web pages, search the web and run shell commands. It was built and tested with **Claude Code**; other coding agents that can run a prompt non-interactively should work but are untested. The scout can also run without an agent, with any chat model: see [API mode](#api-mode-the-scout-with-any-model-no-agent) below.

Run both from the repository root (the folder with `config.toml`).

| Job | Prompt | Suggested time |
| --- | --- | --- |
| Scout | `prompts/scout.md` | once a day, e.g. 12:00 |
| Trial runner | `prompts/trial.md` | once a night, e.g. 22:00 (match `trial.schedule_note`) |

The trial runner needs the machine where your projects live. The scout can run anywhere that can reach the site's data folder (directly or over ssh).

## Claude Code desktop: scheduled tasks

Create two scheduled tasks with the repository root as their folder and a one-line prompt each:

```
Read prompts/scout.md in this folder completely and follow it exactly.
```

```
Read prompts/trial.md in this folder completely and follow it exactly.
```

Press "Run now" once on each so the permissions they need are approved before the first unattended run. Scheduled tasks run while the app is open.

## Claude Code CLI with cron (Linux / macOS)

Non-interactive mode is `claude -p "<prompt>"`. Decide which tools you allow unattended runs to use; see the Claude Code documentation on permissions and settings. Example crontab:

```
0 12 * * *  cd /path/to/tryout-radar && claude -p "Read prompts/scout.md in this folder completely and follow it exactly." >> data/scout.log 2>&1
0 22 * * *  cd /path/to/tryout-radar && claude -p "Read prompts/trial.md in this folder completely and follow it exactly." >> data/trial.log 2>&1
```

## Windows Task Scheduler

Create a task that starts `cmd.exe` with:

```
/c cd /d C:\path\to\tryout-radar && claude -p "Read prompts/scout.md in this folder completely and follow it exactly." >> data\scout.log 2>&1
```

## API mode: the scout with any model, no agent

With `[model]` set in `config.toml` (see the README, "Run with any model"), the scout is one plain command. Run `python -m tryout_radar scout --dry-run` once by hand first. The scheduled job needs the key's environment variable (and `GITHUB_TOKEN`, if you use one) in its own environment.

cron (Linux / macOS):

```
0 12 * * *  cd /path/to/tryout-radar && DEEPSEEK_API_KEY=... python3 -m tryout_radar scout >> data/scout.log 2>&1
```

Better: keep the key in a file only you can read and load it in a small wrapper script instead of the crontab line.

Windows Task Scheduler: set the variable once with `setx DEEPSEEK_API_KEY "..."` (user environment), then create a task that starts `cmd.exe` with:

```
/c cd /d C:\path\to\tryout-radar && python -m tryout_radar scout >> data\scout.log 2>&1
```

With the plugin, use `python "<plugin folder>/radar.py" scout` from any folder; settings are in `~/.tryout-radar/`.

## Site on a different machine

If `tryout_radar serve` runs on a server and your projects are on your PC, keep a copy of the repository and `config.toml` on both. On the PC, run the data commands on the server over ssh; every command that takes a file accepts `-` for standard input:

```
ssh you@server "cd /opt/tryout-radar && python3 -m tryout_radar queue list"
ssh you@server "cd /opt/tryout-radar && python3 -m tryout_radar queue finish <tid> --result -" < result.json
```

Tell the agents about this by adding one line to the top of each prompt, for example: "Run every `python -m tryout_radar` command on the server as `ssh you@server \"cd /opt/tryout-radar && python3 -m tryout_radar …\"`."
