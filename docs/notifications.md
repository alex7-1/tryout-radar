# Notifications: WeCom, Feishu, Telegram, Slack, Discord

[中文](notifications.zh-CN.md) · [Back to the README](../README.md)

Once set up, these messages go to the channels you pick: the daily digest summary (the three picks and a link to the digest), the receipt when you press "Try in project", trial reports, and receipts for what you decide on the site (adopt, stop following). You can turn on several channels; each one gets every message. Long messages are split into several.

Three steps:

1. **Get the key from the platform** (steps for each platform below). Most platforms give you a *webhook URL*: a private address that posts whatever is sent to it into your group or channel. Anyone who has it can post there, so keep it private.
2. **Put the key in an environment variable**, so the key is read when the program runs and never written into a file.
3. **Turn the channel on in the config and send a test message.**

> Easiest: with the plugin installed, tell Claude Code **"Send my Tryout Radar notifications to Slack"** (or whichever channel). Claude adds the config, tells you which environment variable to set, and sends a test message. You set the key yourself; Claude never writes it into a file.

## Step 1: get the key

| Channel | What you need | Environment variables |
| --- | --- | --- |
| [WeCom group robot](#wecom-group-robot-recommended-for-wecom) | the group's webhook URL | `WECOM_WEBHOOK_KEY` |
| [WeCom self-built app](#wecom-self-built-app) | corp ID, app secret, AgentId, recipients | `WECOM_CORP_ID`, `WECOM_APP_SECRET`, `WECOM_TO_USER` |
| [Feishu / Lark](#feishu--lark) | the group's webhook URL | `FEISHU_WEBHOOK_URL` |
| [Telegram](#telegram) | bot token, chat_id | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| [Slack](#slack) | webhook URL | `SLACK_WEBHOOK_URL` |
| [Discord](#discord) | webhook URL | `DISCORD_WEBHOOK_URL` |

You can rename the variables, as long as the `*_env` names in the config match.

### WeCom group robot (recommended for WeCom)

1. Open an **internal group** (members of your organization only; groups with external contacts can't have robots).
2. Top right of the chat, "…" → "Message push" (older versions: "Group robot" → "Add robot") → create one and name it, e.g. Tryout Radar.
3. Copy the webhook URL, like `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx`. Store either the whole URL or just the part after `key=`.

```toml
[[notify]]
type = "wecom_webhook"
key_env = "WECOM_WEBHOOK_KEY"
```

### WeCom self-built app

Sends to a person instead of a group. Needs a WeCom admin, and the sending machine should have a fixed public IP, so the group robot is usually enough.

1. WeCom admin console → "App Management" → "Self-built" → "Create an app"; note its **AgentId** and **Secret**.
2. The **Corp ID** is at the bottom of "My Company".
3. Recipients: the member's account ID (the "Account" field in the member's details); separate several with `|`, or use `@all`.
4. In the app's details, add the sending machine's public IP to the trusted IPs. WeCom asks for a trusted domain or a message-receiving server before it accepts trusted IPs.

```toml
[[notify]]
type = "wecom_app"
corp_id_env = "WECOM_CORP_ID"
secret_env = "WECOM_APP_SECRET"
to_user_env = "WECOM_TO_USER"
agent_id = 1000002          # your AgentId (not a secret, so it goes here)
```

### Feishu / Lark

1. Open a group (an existing one or a new one).
2. Group settings → "Bots" → "Add Bot" → "Custom Bot" → name it → Add.
3. Copy the webhook URL, like `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx` (Lark uses `open.larksuite.com`; both work).
4. **Leave every security option off** (the URL itself is the key):
   - "Signature verification" isn't supported by Tryout Radar yet; with it on, nothing gets through.
   - Don't use "Custom keywords" either: the messages vary, so some would be blocked.
   - "IP whitelist" only suits a server with a fixed IP.

```toml
[[notify]]
type = "feishu_webhook"
url_env = "FEISHU_WEBHOOK_URL"
```

### Telegram

1. In Telegram, open **@BotFather**, send `/newbot` and follow the prompts (the username must end in `bot`). It replies with a **token** like `123456789:AAE…`.
2. Open your bot and press "Start" (or send anything). For a group: add the bot to the group and send `/start@your_bot_username` there.
3. Open `https://api.telegram.org/bot<token>/getUpdates` in a browser (put your token in place of `<token>`) and find `"chat":{"id":`; the number after it is the **chat_id**. Group IDs are negative; keep the minus sign. If the result is empty, send another message (step 2) and reload.

```toml
[[notify]]
type = "telegram"
token_env = "TELEGRAM_BOT_TOKEN"
chat_id_env = "TELEGRAM_CHAT_ID"
```

### Slack

1. Go to <https://api.slack.com/apps> → "Create New App" → "From scratch"; name it and pick your workspace.
2. "Incoming Webhooks" on the left → switch it on → "Add New Webhook" (or "Add New Webhook to Workspace") at the bottom → pick a channel → "Allow". Some workspaces need an admin to approve the app.
3. Copy the webhook URL, like `https://hooks.slack.com/services/T…/B…/…`.

```toml
[[notify]]
type = "slack_webhook"
url_env = "SLACK_WEBHOOK_URL"
```

### Discord

1. You need the "Manage Webhooks" permission on the server.
2. Server Settings → "Integrations" → "Webhooks" → "New Webhook" → name it and pick a channel → "Copy Webhook URL".

```toml
[[notify]]
type = "discord_webhook"
url_env = "DISCORD_WEBHOOK_URL"
```

## Step 2: put the key in an environment variable

**Windows** (PowerShell, one variable per line):

```powershell
setx SLACK_WEBHOOK_URL "https://hooks.slack.com/services/xxxx"
```

Then **quit Claude completely** (not just close the window) and open it again; close and reopen any open terminals too, or they won't see the new value.

**macOS / Linux**: add it to `~/.zshrc` (the macOS default) or `~/.bashrc`:

```bash
echo 'export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/xxxx"' >> ~/.zshrc
```

Then open a new terminal, and quit and reopen the Claude desktop app.

**If the test says `environment variable … is empty`**, Claude can't see the variable. You can put it in Claude Code's settings file `~/.claude/settings.json` instead (on Windows `C:\Users\<you>\.claude\settings.json`); if the file already has content, merge the `"env"` part into it:

```json
{ "env": { "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/xxxx" } }
```

The key then lives in that file, so don't share it or upload it anywhere.

Jobs run by cron or Windows Task Scheduler (for example API mode) need the key in that job's own environment; see [deploy/scheduling.md](../deploy/scheduling.md).

## Step 3: turn the channel on and send a test message

The config file is `~/.tryout-radar/config.toml` with the plugin, or `config.toml` in the repository folder without it. Add the `[[notify]]` block from above (they are also at the end of [config.example.toml](../config.example.toml); remove the leading `#`).

Send a test message:

- With the plugin: tell Claude Code **"Send a test Tryout Radar notification"**.
- From the repository folder:

  ```bash
  echo "Tryout Radar test" | python3 -m tryout_radar notify -
  ```

  In Windows PowerShell: `"Tryout Radar test" | python -m tryout_radar notify -`.

Each channel prints one line: `notify slack_webhook: ok` means it was sent; after `FAILED -` comes the reason, see below.

## Not arriving?

| You see | Cause and fix |
| --- | --- |
| `environment variable … is empty` | The variable isn't set, or Claude / the terminal wasn't restarted; see step 2 |
| `Feishu error 19001` | Wrong Feishu URL, or the bot was removed: copy it again |
| `Feishu error 19021` | Signature verification is on: turn it off in the bot's security settings |
| `Feishu error 19024` | Custom keywords are on: turn them off |
| `Feishu error 19022` | IP whitelist is on and this machine's IP isn't in it |
| `WeCom error 93000` | Wrong WeCom URL or key: copy it again |
| `WeCom error 60020` | Self-built app: this machine's IP isn't a trusted IP |
| `HTTP Error 401` (Telegram) | Wrong token |
| `HTTP Error 400` (Telegram) | Wrong chat_id, or you haven't messaged the bot yet |
| `HTTP Error 403` (Telegram) | You blocked the bot, or it was removed from the group |
| `HTTP Error 403` / `404` (Slack) | Wrong webhook URL, or it was deleted |
| `HTTP Error 404` (Discord) | Wrong webhook URL, or it was deleted |
| `timed out`, `URLError` | Network problem; see below |

## Network

Tryout Radar uses the system proxy settings (on Linux, the `HTTPS_PROXY` environment variable). In mainland China, Telegram, Slack and Discord need a proxy: turning on your proxy app's "system proxy" is usually enough, or set `HTTPS_PROXY`, for example `setx HTTPS_PROXY "http://127.0.0.1:7890"` (use your proxy's port). WeCom and Feishu don't need one.
