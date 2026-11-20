# Security

Tryout Radar asks a coding agent to download tools written by strangers and run them next to your projects. Read this before you enable `trial_mode = "try"`.

## What protects you today, and what does not

- **Agent rules, not a sandbox.** `prompts/trial.md` tells the agent to read code before running it, work only in a git worktree or a copy, never push or merge, and stop on a list of risky actions. These are instructions to a language model. They lower the risk; they are not an operating-system boundary. A malicious install script, or text written to manipulate the agent (prompt injection), can still cause harm if the agent runs it.
- **Git worktrees protect your branches, not your machine.** A worktree keeps your main working tree and branches untouched. Code running inside it has the same access as your user account: files, SSH keys, cloud credentials, the network.
- **`assess` is the safe default.** In `assess` mode nothing third-party is executed; the agent only reads and writes a report. Switch a project to `try` only when you accept the risk above.

## Recommended setup for `try`

1. Run the trial runner as a **separate OS user** or in a **VM / container** that has a copy of the project and no access to your personal files, SSH keys, password stores or production credentials.
2. Keep production secrets out of the projects the runner can see (use `.env` files that are not in the copy).
3. Give the runner's network only what it needs (package registries, GitHub).
4. Review the report and the diff before you adopt anything. Adopting is always a separate step that you start.

Container isolation built into the tool is planned; until then, isolation is your setup's job.

## The site and its buttons

- Everyone who knows the site URL can read the digest and press the buttons (queue a trial, mark items). Use a long random `server.secret_path`, serve it over HTTPS, and don't post the URL publicly.
- Requests are limited (`trial.daily_request_limit`), only items that exist in a published digest can be queued, and every queued request notifies you.
- Pages and reports are public to URL holders: the prompts tell the agents never to write customer data, secrets, server addresses or internal prices into them. Check your first reports.

## API mode: what goes to the model provider

`python -m tryout_radar scout` sends text to the provider in `[model]`: your project and topic descriptions, your "not relevant" / "want" marks (titles only), the public text of today's candidates and, when `[discovery]` is on, the titles and folder names of your recent Claude Code / Codex sessions (your home folder shown as `~`). Nothing else from your disk. Pick a provider whose data terms you accept, a local model (Ollama, LM Studio) if none fits, or switch discovery off.

The model gets no tools and nothing it writes is run. Text from the web can still try to steer it (prompt injection); the worst it can do is word a digest entry badly, because the model can only keep or drop candidates the code found, can only use your project and topic keys, and never sets links, titles or star counts.

## Secrets

`config.toml` holds no secrets; channels read tokens from environment variables named in the config. Keep `.env` files out of git (`.gitignore` already does).

## Reporting a problem

Please open a private security advisory on the repository rather than a public issue.
