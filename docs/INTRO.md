# Tryout Radar 试用雷达 · Introduction / 介绍

Ready-to-use texts for the repository page, posts and messages. 仓库页面、发帖、转发时可以直接用的介绍。

## One line / 一句话

- **EN**: Finds new AI tools that fit your projects, tries them in a sandbox branch, and tells you whether they are worth using.
- **中文**：每天找出对你项目有用的新 AI 工具，放进项目里试一遍，告诉你值不值得用。

GitHub description (bilingual, under 350 characters):

> Daily scout for new AI skills & agent tools, scored against your own projects; one click tries one in a sandbox branch and reports back. 每天找对你项目有用的新 AI 工具，一键在单独分支里试用并出报告。Claude Code plugin with a /radar panel.

Suggested topics: `claude-code`, `claude-code-plugin`, `agent-skills`, `ai-tools`, `codex`, `mcp`, `developer-tools`, `automation`

## Short introduction / 简介

**中文**

新的 AI skill、MCP、agent 用法每天都在冒出来，真正能用在自己项目上的很少，挨个去试又太花时间。

Tryout Radar 把这件事分成两步交给 AI：

1. **每天的侦察员**：看 GitHub、X 和网上新出的工具，按你的每个项目打分，写清楚能用在哪、怎么用、上手要多久，出一份日报。
2. **每晚的试用员**：你在日报上点「交给〈项目〉」的，它在那个项目的单独分支里装上，跑项目自己的测试，给你一份有证据的报告：建议采纳、不建议用，还是要你决定。

它还会根据你最近在 Claude Code / Codex 里做的事发现新项目；你也可以自己加项目、加主题，把主题对应到具体项目。所有操作都能在 Claude Code 的 `/radar` 面板里完成。

试用时不合并、不推送、不上线；遇到要花钱、要钥匙、要碰线上，就停下来问你。

**English**

New AI skills, MCP servers and agent techniques appear every day. Few of them fit your own projects, and trying each one by hand takes too long.

Tryout Radar hands both steps to AI:

1. **A daily scout** reads GitHub, X and the web for new tools, scores each against every one of your projects, and writes a digest that says where it helps, how, and how long it takes to start.
2. **A nightly trial runner** takes what you sent to a project with "Try in <project>", installs it in a sandbox branch of that project, runs the project's own tests, and writes an evidence-based report: adopt, don't use, or your call.

It also notices new projects from what you worked on lately in Claude Code / Codex, and you can add your own projects and topics and tie topics to projects. Everything is in the `/radar` panel inside Claude Code.

Trials never merge, push or deploy, and stop to ask before anything that needs money, keys or production access.

## Install / 安装

```
/plugin install tryout-radar --marketplace alex7-1/tryout-radar
```

Then say "set up Tryout Radar" and open `/radar`. 装好后说一句“设置 Tryout Radar”，再打开 `/radar`。Needs Python 3.11+ / 需要 Python 3.11 或更新。

## Posts / 发帖

**X (English)**

> I kept bookmarking new AI tools and never trying them. So I built Tryout Radar, a Claude Code plugin: a daily scout scores new skills and agent tools against my own projects, and one click tries one in a sandbox branch overnight and reports back: adopt or not.
> /plugin install tryout-radar --marketplace alex7-1/tryout-radar

**朋友圈 / 小红书（中文）**

> 新的 AI 工具天天出，收藏了一堆从来没试过。做了个 Claude Code 插件 Tryout Radar（试用雷达）：每天自动找对我自己项目有用的新 skill 和 agent 工具，写清楚用在哪；看中哪个点一下，晚上它就在项目的单独分支里装上试一遍，第二天告诉我值不值得用。开源免费，一行命令安装。
