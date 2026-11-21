# 推送设置：把日报发到企业微信、飞书、Telegram、Slack、Discord

[English](notifications.md) · [回到说明页](../README.zh-CN.md)

设好以后，这些消息会发到你选的渠道：每天的日报摘要（先看哪三条 + 日报链接）、你点「交给项目试」后的排队回执、试用报告，以及你在网页上采纳、不再关注时的回执。可以同时开好几个渠道，每个都会收到。消息太长时会自动拆成几条。

一共三步：

1. **在平台上拿到钥匙**（下面每个平台有步骤）。大多数平台给的是一个 *webhook 地址*：一个专用网址，程序往它发消息，消息就出现在你的群或频道里。谁拿到这个网址都能往你的群里发消息，别贴到公开的地方。
2. **把钥匙存进环境变量**。环境变量是电脑里存钥匙的地方：程序运行时去读，钥匙不写进任何文件。
3. **在配置里打开这个渠道，发一条测试消息。**

> 最省事：装好插件后，在 Claude Code 里说 **「把 Tryout Radar 的推送设到飞书」**（换成你要的渠道）。Claude 会改好配置，告诉你要设哪个环境变量，再帮你发测试消息。钥匙由你自己设，Claude 不会把它写进文件。

## 第 1 步：拿到钥匙

| 渠道 | 要准备的 | 环境变量 |
| --- | --- | --- |
| [企业微信群机器人](#企业微信群机器人推荐) | 群里的 webhook 地址 | `WECOM_WEBHOOK_KEY` |
| [企业微信自建应用](#企业微信自建应用) | 企业ID、应用 Secret、AgentId、收消息的人 | `WECOM_CORP_ID`、`WECOM_APP_SECRET`、`WECOM_TO_USER` |
| [飞书 / Lark](#飞书--lark) | 群里的 webhook 地址 | `FEISHU_WEBHOOK_URL` |
| [Telegram](#telegram) | 机器人 token、chat_id | `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` |
| [Slack](#slack) | webhook 地址 | `SLACK_WEBHOOK_URL` |
| [Discord](#discord) | webhook 地址 | `DISCORD_WEBHOOK_URL` |

环境变量的名字可以改，只要配置里 `*_env` 写的名字和你设的一致。

### 企业微信群机器人（推荐）

1. 打开一个**内部群**（只有本企业成员的群；有外部联系人的群加不了机器人）。
2. 群聊右上角「…」→「消息推送」（旧版本叫「群机器人」→「添加机器人」）→ 新建，起个名字，比如 Tryout Radar。
3. 复制 Webhook 地址，形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx`。把整个地址存进环境变量，或者只存 `key=` 后面那段，都可以。

```toml
[[notify]]
type = "wecom_webhook"
key_env = "WECOM_WEBHOOK_KEY"
```

### 企业微信自建应用

消息直接发给某个人，不进群。需要企业管理员，而且发消息的那台机器最好有固定的公网 IP，所以一般用上面的群机器人就够了。

1. 企业微信管理后台 →「应用管理」→「自建」→「创建应用」，记下应用的 **AgentId** 和 **Secret**。
2. 「我的企业」页面最下面的 **企业ID**。
3. 收消息的人：成员的账号（通讯录里成员详情的「账号」）。多人用 `|` 隔开，发给全员写 `@all`。
4. 在应用详情里把发消息那台机器的公网 IP 加进「企业可信IP」。企业微信要求先配好「可信域名」或「接收消息服务器」才能填可信 IP。

```toml
[[notify]]
type = "wecom_app"
corp_id_env = "WECOM_CORP_ID"
secret_env = "WECOM_APP_SECRET"
to_user_env = "WECOM_TO_USER"
agent_id = 1000002          # 换成你的 AgentId（它不是秘密，直接写在这里）
```

### 飞书 / Lark

1. 打开一个群（现有的群，或者新建一个）。
2. 群设置 →「群机器人」→「添加机器人」→「自定义机器人」→ 填名字 → 添加。
3. 复制 webhook 地址，形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`（Lark 国际版是 `open.larksuite.com`，一样能用）。
4. **安全设置都不勾**（地址本身就是钥匙）：
   - 「签名校验」Tryout Radar 还不支持，开了会发不出去。
   - 「自定义关键词」也别开：推送的消息有好几种，内容不固定，会有一部分被飞书拦下。
   - 「IP 白名单」只适合有固定 IP 的服务器。

```toml
[[notify]]
type = "feishu_webhook"
url_env = "FEISHU_WEBHOOK_URL"
```

### Telegram

在中国大陆要开代理，见后面的[网络](#网络)。

1. 在 Telegram 里找 **@BotFather**，发 `/newbot`，按提示起名字（用户名要以 `bot` 结尾）。它会回你一串 **token**，形如 `123456789:AAE…`。
2. 找到你的机器人，点「Start」或随便发一句。要发到群里：把机器人拉进群，在群里发一句 `/start@你的机器人用户名`。
3. 在浏览器打开 `https://api.telegram.org/bot<token>/getUpdates`（`<token>` 换成上一步那串），在返回的内容里找 `"chat":{"id":`，后面的数字就是 **chat_id**。群的 id 是负数，负号要带上。返回是空的，就回第 2 步再发一句，再刷新。

```toml
[[notify]]
type = "telegram"
token_env = "TELEGRAM_BOT_TOKEN"
chat_id_env = "TELEGRAM_CHAT_ID"
```

### Slack

1. 打开 <https://api.slack.com/apps> →「Create New App」→「From scratch」，起名字，选你的 workspace。
2. 左边「Incoming Webhooks」→ 打开开关 → 页面下方「Add New Webhook」（有的版本写「Add New Webhook to Workspace」）→ 选频道 →「Allow」。有的 workspace 要管理员批准才能装应用。
3. 复制生成的 Webhook URL，形如 `https://hooks.slack.com/services/T…/B…/…`。

```toml
[[notify]]
type = "slack_webhook"
url_env = "SLACK_WEBHOOK_URL"
```

### Discord

1. 你在这个服务器上要有「管理 Webhook」（Manage Webhooks）权限。
2. 服务器设置 →「整合」（Integrations）→「Webhook」→「新 Webhook」→ 起名字、选频道 →「复制 Webhook URL」。

```toml
[[notify]]
type = "discord_webhook"
url_env = "DISCORD_WEBHOOK_URL"
```

## 第 2 步：把钥匙存进环境变量

**Windows**（PowerShell，一个变量一行）：

```powershell
setx FEISHU_WEBHOOK_URL "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
```

设完要**完全退出** Claude（不是只关窗口）再打开；开着的终端也要关掉重开，新的值才读得到。

**macOS / Linux**：写进 `~/.zshrc`（macOS 默认）或 `~/.bashrc`：

```bash
echo 'export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"' >> ~/.zshrc
```

然后新开一个终端，Claude 桌面版完全退出再打开。

**测试时提示 `environment variable … is empty`**，说明 Claude 没读到。这时可以写进 Claude Code 的设置文件 `~/.claude/settings.json`（Windows 是 `C:\Users\<你的用户名>\.claude\settings.json`），文件里已有内容的话，把 `"env"` 这段合并进去：

```json
{ "env": { "FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx" } }
```

这样钥匙就存在这个文件里了，这个文件别分享、别传到网上。

用 cron 或 Windows「任务计划程序」定时跑的（比如 API 模式），钥匙要在那个任务自己的环境里，见 [deploy/scheduling.md](../deploy/scheduling.md)。

## 第 3 步：打开渠道，发一条测试消息

配置文件：装了插件的是 `~/.tryout-radar/config.toml`；直接用仓库的是仓库里的 `config.toml`。把上面对应的那段 `[[notify]]` 加进去（[config.example.toml](../config.example.toml) 最后也有，去掉行首的 `#` 就行）。

发测试消息：

- 装了插件：在 Claude Code 里说 **「给 Tryout Radar 发一条测试推送」**。
- 直接用仓库：在仓库文件夹里运行

  ```powershell
  "Tryout Radar test" | python -m tryout_radar notify -
  ```

  macOS / Linux 用 `echo "Tryout Radar test" | python3 -m tryout_radar notify -`。

每个渠道打印一行：`notify feishu_webhook: ok` 就是发出去了；`FAILED - …` 后面是原因，对照下表。

## 发不出去？

| 看到的提示 | 原因和办法 |
| --- | --- |
| `environment variable … is empty` | 环境变量没设上，或设完没重启 Claude / 终端，见第 2 步 |
| `Feishu error 19001` | 飞书地址不对，或机器人被删了：重新复制 |
| `Feishu error 19021` | 开了签名校验：在机器人的安全设置里关掉 |
| `Feishu error 19024` | 开了自定义关键词：关掉 |
| `Feishu error 19022` | 开了 IP 白名单，这台机器的 IP 不在里面 |
| `WeCom error 93000` | 企业微信的地址或 key 不对：重新复制 |
| `WeCom error 60020` | 自建应用：这台机器的 IP 不在「企业可信IP」里 |
| `HTTP Error 401`（Telegram） | token 不对 |
| `HTTP Error 400`（Telegram） | chat_id 不对，或还没在 Telegram 里给机器人发过消息 |
| `HTTP Error 403`（Telegram） | 你屏蔽了机器人，或机器人被移出了群 |
| `HTTP Error 403` / `404`（Slack） | webhook 地址不对，或已被删除 |
| `HTTP Error 404`（Discord） | webhook 地址不对，或已被删除 |
| `timed out`、`URLError` | 网络不通，见下面 |

## 网络

Telegram、Slack、Discord 在中国大陆需要代理。Tryout Radar 用系统的代理设置：代理软件开了「系统代理」一般就行（Linux 上要设环境变量）。也可以单独设环境变量 `HTTPS_PROXY`，比如：

```powershell
setx HTTPS_PROXY "http://127.0.0.1:7890"
```

端口换成你的代理软件用的端口。企业微信和飞书不需要代理。
