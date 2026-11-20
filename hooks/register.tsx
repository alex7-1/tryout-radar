// Tryout Radar panel: /radar opens a pane with today's digest, your projects, your topics and the trial queue.
// It reads and writes the same files the Python CLI uses under ~/.tryout-radar (or $TRYOUT_RADAR_HOME), and
// starts the scout, the trial runner or the setup by submitting a prompt that uses the tryout-radar skill.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type {
  TryoutRadarDraft, TryoutRadarItem, TryoutRadarOption, TryoutRadarProject, TryoutRadarSnapshot, TryoutRadarTopic,
  TryoutRadarTrial,
} from '../types'
import { INTRO } from './intro'

const PANE = 'tryout-radar'
const EMPTY_DRAFT: TryoutRadarDraft = { kind: '', name: '', path: '', about: '', keywords: '', projects: [] }
const tab = atom({ plugin: 'tryout-radar', key: 'tab' } as const, 'today')
const snapshot = atom({ plugin: 'tryout-radar', key: 'snapshot' } as const, null)
const openTrial = atom({ plugin: 'tryout-radar', key: 'openTrial' } as const, '')
const message = atom({ plugin: 'tryout-radar', key: 'message' } as const, '')
const draft = atom({ plugin: 'tryout-radar', key: 'draft' } as const, EMPTY_DRAFT)

const EN = {
  title: 'Tryout Radar',
  notSetUp: 'Tryout Radar is not set up yet. Setup asks about your projects and where to send the daily summary, then schedules the scout and the trial runner.',
  setUp: 'Set up now',
  today: 'Today', projects: 'Projects', topics: 'Topics', trials: 'Trials', about: 'About · 介绍',
  whatIsThis: 'What is this?',
  noDigest: 'No digest yet. Run the scout once to make the first one.',
  runScout: 'Run scout now', runTrials: 'Run trials now', refresh: 'Refresh', openSite: 'Open the site',
  tryIn: 'Try in', want: 'Want', skip: 'Not relevant', marked: '✓ ',
  newDirections: 'New directions spotted', stopFollowing: 'Stop following', follow: 'Follow',
  following: 'following', ignored: 'not following', paused: 'paused', active: 'on',
  source: { config: 'from config.toml', discovered: 'discovered', manual: 'added by you', custom: 'added by you' } as Record<string, string>,
  addProject: 'Add a project', addTopic: 'Add a topic', save: 'Save', cancel: 'Cancel',
  name: 'Name', folder: 'Folder (optional)', about: 'What it is / what it needs (optional)',
  interests: 'What to look for (comma separated)', keywords: 'Search keywords (comma separated)',
  topicFor: 'For which projects (none = all):', forAll: 'all projects', forSome: 'for',
  pause: 'Pause', resume: 'Resume', configTopic: 'Change topics from config.toml in that file.',
  needName: 'Give it a name first.', saved: (n: string) => `Saved: ${n}. The scout uses it from its next run.`,
  noTrials: 'No trials yet. Press “Try in …” on an item; the trial runner picks it up on its next run.',
  queued: (t: string, p: string) => `Queued: ${t} → ${p}. It runs at the next trial run.`,
  already: 'Already queued for that project.',
  status: { queued: 'queued', running: 'running', done: 'report', blocked: 'needs you', failed: 'failed', closed: 'closed',
    'adopt-requested': 'to adopt', adopting: 'merging', adopted: 'adopted' } as Record<string, string>,
  verdict: { adopt: 'adopt', reject: "don't use", decide: 'your call' } as Record<string, string>,
  yourCall: 'Your call:', techDetails: 'Technical details', hideDetails: 'Hide details', youChose: 'You chose:',
  alreadyChosen: 'This one was already decided.', noTarget: 'That project is not available for trials.',
  decided: { continue: 'Got it: it continues at the next trial run.', retarget: 'Got it: moved to {project}; tried at the next run.',
    close: 'Got it: this trial ends here.', adopt: 'Got it: it is merged locally at the next trial run.' } as Record<string, string>,
  scoutPrompt: 'Use the tryout-radar skill to run the Tryout Radar scout now.',
  trialPrompt: 'Use the tryout-radar skill to run the Tryout Radar trial runner now.',
  setupPrompt: 'Use the tryout-radar skill to set up Tryout Radar.',
  started: 'Started in this session.',
  switched: (n: string, on: boolean) => (on ? `Following ${n} again.` : `Stopped following ${n}.`),
}
const ZH: typeof EN = {
  title: 'Tryout Radar 试用雷达',
  notSetUp: 'Tryout Radar 还没设置。设置时会问你有哪些项目、每天的摘要发到哪里，然后把侦察员和试用员定时跑起来。',
  setUp: '现在设置',
  today: '今天', projects: '项目', topics: '主题', trials: '试用', about: '介绍 · About',
  whatIsThis: '这是什么？',
  noDigest: '还没有日报。先跑一次侦察员，就有第一期了。',
  runScout: '现在跑侦察员', runTrials: '现在跑试用员', refresh: '刷新', openSite: '打开网页版',
  tryIn: '交给', want: '想试', skip: '不相关', marked: '✓ ',
  newDirections: '新发现的方向', stopFollowing: '不用关注', follow: '关注',
  following: '关注中', ignored: '不关注', paused: '已停用', active: '启用中',
  source: { config: '配置里写的', discovered: '自动发现', manual: '你加的', custom: '你加的' },
  addProject: '加项目', addTopic: '加主题', save: '保存', cancel: '取消',
  name: '名字', folder: '文件夹（可不填）', about: '是做什么的 / 需要什么（可不填）',
  interests: '想找哪类工具（逗号分隔）', keywords: '搜索关键词（逗号分隔）',
  topicFor: '对应哪些项目（不选 = 全部）：', forAll: '全部项目', forSome: '对应',
  pause: '停用', resume: '启用', configTopic: '配置文件里的主题请在 config.toml 里改。',
  needName: '先填个名字。', saved: (n: string) => `已保存：${n}，侦察员下次运行起生效。`,
  noTrials: '还没有试用。在条目上点「交给…」，试用员下次运行时就会试。',
  queued: (t: string, p: string) => `已排队：${t} → ${p}，试用员下次运行时试。`,
  already: '这个项目已经在排队了。',
  status: { queued: '排队中', running: '试用中', done: '报告', blocked: '要你决定', failed: '没试成', closed: '已结束',
    'adopt-requested': '要采纳', adopting: '正在合并', adopted: '已采纳' },
  verdict: { adopt: '建议采纳', reject: '不建议用', decide: '要你决定' },
  yourCall: '要你决定：', techDetails: '技术细节', hideDetails: '收起细节', youChose: '你选了：',
  alreadyChosen: '这条已经选过了。', noTarget: '那个项目现在不能试用。',
  decided: { continue: '收到，试用员下次运行时接着做。', retarget: '收到，已转给「{project}」，下次运行时试。',
    close: '收到，这条到此为止。', adopt: '收到，试用员下次运行时在本机合并。' },
  scoutPrompt: '用 tryout-radar skill 现在跑一次 Tryout Radar 侦察员。',
  trialPrompt: '用 tryout-radar skill 现在跑一次 Tryout Radar 试用员。',
  setupPrompt: '用 tryout-radar skill 设置 Tryout Radar。',
  started: '已在这个会话里开始。',
  switched: (n: string, on: boolean) => (on ? `已重新关注「${n}」。` : `已不再关注「${n}」。`),
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/
const KEY_RE = /^[a-z0-9][a-z0-9-]{0,39}$/

function joinPath(base: string, ...parts: string[]): string {
  const sep = base.includes('\\') ? '\\' : '/'
  return [base.replace(/[\\/]+$/, ''), ...parts.map(p => p.replace(/^[\\/]+|[\\/]+$/g, ''))].join(sep)
}

async function readJson<T>($: EngineInterface, path: string, fallback: T): Promise<T> {
  try {
    const data = JSON.parse((await $.fs.read(path)) as string)
    return (Array.isArray(fallback) ? Array.isArray(data) : data && typeof data === 'object') ? (data as T) : fallback
  } catch {
    return fallback
  }
}

async function writeJson($: EngineInterface, path: string, data: unknown): Promise<void> {
  await $.fs.write(path, JSON.stringify(data, null, 1))
}

function tomlString(text: string, key: string): string {
  const m = text.match(new RegExp(`^\\s*${key}\\s*=\\s*"([^"]*)"`, 'm'))
  return m ? m[1] : ''
}

/** Same rule as the CLI: ASCII words joined by '-', or prefix + time for names that are mostly not ASCII. */
function slug(name: string, prefix: string): string {
  const s = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40).replace(/-+$/, '')
  const letters = name.replace(/\s/g, '').length || 1
  const ascii = (name.match(/[A-Za-z0-9]/g) ?? []).length
  return ascii / letters >= 0.5 && s.length >= 3 && KEY_RE.test(s) ? s : `${prefix}-${Math.floor(Date.now() / 1000).toString(16)}`
}

function splitList(text: string): string[] {
  return text.split(/[,，;；\n]+/).map(s => s.trim()).filter(Boolean).slice(0, 12)
}

async function radarHome($: EngineInterface): Promise<string> {
  const own = await $.env.get('TRYOUT_RADAR_HOME')
  if (own) return own
  const home = (await $.env.get('USERPROFILE')) || (await $.env.get('HOME')) || '.'
  return joinPath(home, '.tryout-radar')
}

async function load($: EngineInterface): Promise<TryoutRadarSnapshot> {
  const home = await radarHome($)
  const configPath = joinPath(home, 'config.toml')
  const empty: TryoutRadarSnapshot = {
    home, dataDir: joinPath(home, 'data'), isZh: false, title: 'Tryout Radar', baseUrl: '', isConfigured: false,
    date: '', headline: '', items: [], picks: [], projects: [], topics: [], newProjects: [], feedback: {}, trials: [],
  }
  if (!(await $.fs.exists(configPath))) return empty
  const toml = (await $.fs.read(configPath)) as string
  const dataSetting = tomlString(toml, 'data_dir') || 'data'
  const dataDir = /^([A-Za-z]:)?[\\/]/.test(dataSetting) ? dataSetting : joinPath(home, dataSetting)
  const snap: TryoutRadarSnapshot = {
    ...empty, dataDir, isConfigured: true, isZh: tomlString(toml, 'language').toLowerCase().startsWith('zh'),
    title: tomlString(toml, 'title') || 'Tryout Radar', baseUrl: tomlString(toml, 'base_url'),
  }
  const reportsDir = joinPath(dataDir, 'reports')
  if (await $.fs.exists(reportsDir)) {
    const dates = (await $.fs.list(reportsDir)).map(f => f.name.replace(/\.json$/, '')).filter(n => DATE_RE.test(n)).sort()
    const latest = dates[dates.length - 1]
    if (latest) {
      const rep = await readJson<Record<string, any>>($, joinPath(reportsDir, `${latest}.json`), {})
      snap.date = latest
      snap.headline = String(rep.headline ?? '')
      snap.picks = Array.isArray(rep.picks) ? rep.picks.map(String) : []
      snap.items = (Array.isArray(rep.items) ? rep.items : []).map((it: any): TryoutRadarItem => ({
        id: String(it.id ?? ''), title: String(it.title ?? ''), url: String(it.url ?? ''), category: String(it.category ?? ''),
        summary: String(it.summary ?? ''), verdict: String(it.verdict ?? ''), effort: String(it.effort ?? ''),
        projects: (Array.isArray(it.projects) ? it.projects : []).map((p: any) => ({
          key: String(p.key ?? ''), fit: Number(p.fit) || 0, how: String(p.how ?? '') })),
      }))
      snap.newProjects = (Array.isArray(rep.newProjects) ? rep.newProjects : []).map((p: any) => ({
        key: String(p.key ?? ''), why: String(p.why ?? '') }))
      for (const [key, info] of Object.entries((rep._projects ?? {}) as Record<string, any>)) {
        snap.projects.push({ key, name: String(info?.name ?? key), trialMode: String(info?.trial_mode ?? 'assess'),
          source: info?.source === 'discovered' || info?.source === 'manual' ? info.source : 'config',
          status: info?.status === 'ignored' ? 'ignored' : 'active' })
      }
      for (const t of Array.isArray(rep._topics) ? rep._topics : []) {
        snap.topics.push({ key: String(t.key ?? ''), name: String(t.name ?? t.key ?? ''), focus: String(t.focus ?? ''),
          projects: Array.isArray(t.projects) ? t.projects.map(String) : [], source: t.source === 'custom' ? 'custom' : 'config',
          status: t.status === 'paused' ? 'paused' : 'active' })
      }
    }
  }
  // The files the panel itself changes win over what the last digest recorded.
  const overrides = await readJson<Record<string, string>>($, joinPath(dataDir, 'project-overrides.json'), {})
  for (const p of snap.projects) if (p.source === 'config' && overrides[p.key]) p.status = overrides[p.key] === 'ignored' ? 'ignored' : 'active'
  for (const p of await readJson<any[]>($, joinPath(dataDir, 'projects.auto.json'), [])) {
    const key = String(p?.key ?? '')
    if (!key) continue
    const entry: TryoutRadarProject = { key, name: String(p.name ?? key), trialMode: String(p.trial_mode ?? 'assess'),
      source: p.source === 'manual' ? 'manual' : 'discovered', status: p.status === 'ignored' ? 'ignored' : 'active' }
    const known = snap.projects.find(q => q.key === key)
    if (known) Object.assign(known, entry)
    else snap.projects.push(entry)
  }
  for (const t of await readJson<any[]>($, joinPath(dataDir, 'topics.custom.json'), [])) {
    const key = String(t?.key ?? '')
    if (!key) continue
    const entry: TryoutRadarTopic = { key, name: String(t.name ?? key), focus: String(t.focus ?? ''),
      projects: Array.isArray(t.projects) ? t.projects.map(String) : [], source: 'custom',
      status: t.status === 'paused' ? 'paused' : 'active' }
    const known = snap.topics.find(q => q.key === key)
    if (known) Object.assign(known, entry)
    else snap.topics.push(entry)
  }
  const fb = await readJson<Record<string, any>>($, joinPath(dataDir, 'feedback.json'), {})
  for (const [k, v] of Object.entries(fb)) snap.feedback[k] = String(v?.status ?? '')
  const trialsDir = joinPath(dataDir, 'trials')
  if (await $.fs.exists(trialsDir)) {
    const names = (await $.fs.list(trialsDir)).map(f => f.name).filter(n => /^\d{8}-\d{6}-[a-z0-9-]+\.json$/.test(n)).sort().reverse()
    for (const n of names.slice(0, 30)) {
      const t = await readJson<Record<string, any>>($, joinPath(trialsDir, n), {})
      snap.trials.push({ tid: String(t.tid ?? n.replace(/\.json$/, '')), itemId: String(t.itemId ?? ''),
        title: String(t.item?.title ?? t.itemId ?? ''), project: String(t.project ?? ''), status: String(t.status ?? ''),
        verdict: String(t.verdict ?? ''), summary: String(t.summary ?? ''), report: String(t.report_md ?? ''),
        headline: String(t.plain?.headline || t.summary || ''), ask: String(t.plain?.ask ?? ''),
        options: (Array.isArray(t.options) ? t.options : []).filter((o: any) => ['continue', 'retarget', 'close', 'adopt'].includes(o?.action))
          .map((o: any) => ({ id: String(o.id ?? ''), label: String(o.label ?? o.id ?? ''), effect: String(o.effect ?? ''),
            action: o.action, project: String(o.project ?? ''), approval: String(o.approval ?? '') })),
        decision: String(t.decision?.label ?? '') })
    }
  }
  return snap
}

async function refresh($: EngineInterface, note = ''): Promise<void> {
  const snap = await load($)
  await update($, snapshot, () => snap)
  await update($, message, () => note)
}

function stamp(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

function iso(d = new Date()): string {
  return d.toISOString().replace(/\.\d+Z$/, 'Z')
}

async function queueTrial($: EngineInterface, snap: TryoutRadarSnapshot, item: TryoutRadarItem, project: TryoutRadarProject) {
  const S = snap.isZh ? ZH : EN
  if (snap.trials.some(t => t.itemId === item.id && t.project === project.key && (t.status === 'queued' || t.status === 'running'))) {
    return refresh($, S.already)
  }
  const tid = `${stamp()}-${project.key}`
  await writeJson($, joinPath(snap.dataDir, 'trials', `${tid}.json`), {
    tid, status: 'queued', createdAt: iso(), updatedAt: iso(), date: snap.date, itemId: item.id, project: project.key,
    mode: project.trialMode, note: '', source: 'panel',
    item: { title: item.title, url: item.url, category: item.category, summary: item.summary, projects: item.projects,
      effort: item.effort, verdict: item.verdict },
  })
  return refresh($, S.queued(item.title, project.name))
}

async function mark($: EngineInterface, snap: TryoutRadarSnapshot, item: TryoutRadarItem, status: string) {
  const path = joinPath(snap.dataDir, 'feedback.json')
  const fb = await readJson<Record<string, any>>($, path, {})
  if (fb[item.id]?.status === status) delete fb[item.id]
  else fb[item.id] = { status, title: item.title, url: item.url, category: item.category, date: snap.date, updatedAt: iso() }
  await writeJson($, path, fb)
  return refresh($)
}

async function setProjectStatus($: EngineInterface, snap: TryoutRadarSnapshot, project: TryoutRadarProject, on: boolean) {
  const S = snap.isZh ? ZH : EN
  const status = on ? 'active' : 'ignored'
  if (project.source === 'config') {
    const path = joinPath(snap.dataDir, 'project-overrides.json')
    const ov = await readJson<Record<string, string>>($, path, {})
    ov[project.key] = status
    await writeJson($, path, ov)
  } else {
    const path = joinPath(snap.dataDir, 'projects.auto.json')
    const auto = await readJson<any[]>($, path, [])
    const hit = auto.find(p => p?.key === project.key)
    if (hit) {
      hit.status = status
      hit.changedAt = iso()
      await writeJson($, path, auto)
    }
  }
  return refresh($, S.switched(project.name, on))
}

async function changeTopic($: EngineInterface, snap: TryoutRadarSnapshot, key: string, change: (t: any) => void) {
  const path = joinPath(snap.dataDir, 'topics.custom.json')
  const topics = await readJson<any[]>($, path, [])
  const hit = topics.find(t => t?.key === key)
  if (hit) {
    change(hit)
    await writeJson($, path, topics)
  }
  return refresh($)
}

async function saveDraft($: EngineInterface, snap: TryoutRadarSnapshot) {
  const S = snap.isZh ? ZH : EN
  const d = (await read($, draft)) as TryoutRadarDraft
  const name = d.name.replace(/[<>\[\]`*]/g, '').trim().slice(0, 40)
  if (!name) return update($, message, () => S.needName)
  if (d.kind === 'project') {
    const path = joinPath(snap.dataDir, 'projects.auto.json')
    const auto = await readJson<any[]>($, path, [])
    let key = slug(name, 'p')
    while (snap.projects.some(p => p.key === key) || auto.some(p => p?.key === key)) key = `${key.slice(0, 36)}-${Math.floor(Math.random() * 900 + 100)}`
    auto.push({ key, name, parent: '', path: d.path.trim(), about: d.about.trim().slice(0, 1000), interests: splitList(d.keywords),
      rules_files: [], trial_mode: 'assess', why: '', found: iso().slice(0, 10), status: 'active', source: 'manual' })
    await writeJson($, path, auto)
  } else if (d.kind === 'topic') {
    const path = joinPath(snap.dataDir, 'topics.custom.json')
    const topics = await readJson<any[]>($, path, [])
    let key = slug(name, 't')
    while (snap.topics.some(t => t.key === key) || topics.some(t => t?.key === key)) key = `${key.slice(0, 36)}-${Math.floor(Math.random() * 900 + 100)}`
    const keywords = splitList(d.keywords)
    topics.push({ key, name, focus: d.about.trim().slice(0, 500), github_queries: keywords, x_queries: keywords, watch: [],
      projects: d.projects.filter(k => snap.projects.some(p => p.key === k)), status: 'active', added: iso().slice(0, 10) })
    await writeJson($, path, topics)
  }
  await update($, draft, () => EMPTY_DRAFT)
  return refresh($, S.saved(name))
}

/** A choice on a trial report: the same rules as `radar queue decide`. */
async function decideTrial($: EngineInterface, snap: TryoutRadarSnapshot, trial: TryoutRadarTrial, option: TryoutRadarOption) {
  const S = snap.isZh ? ZH : EN
  const path = joinPath(snap.dataDir, 'trials', `${trial.tid}.json`)
  const t = await readJson<Record<string, any>>($, path, {})
  if (!t.tid || t.decision || !['done', 'blocked', 'failed', 'adopted'].includes(t.status)) return refresh($, S.alreadyChosen)
  let note = S.decided[option.action]
  if (option.action === 'retarget') {
    const target = snap.projects.find(p => p.key === option.project && p.status === 'active' && p.trialMode !== 'off')
    if (!target) return refresh($, S.noTarget)
    const tid = `${stamp()}-${target.key}`
    await writeJson($, joinPath(snap.dataDir, 'trials', `${tid}.json`), {
      tid, status: 'queued', createdAt: iso(), updatedAt: iso(), date: t.date, itemId: t.itemId, project: target.key,
      mode: target.trialMode, note: `moved from ${t.project}: ${option.label}`, item: t.item ?? {}, source: 'panel' })
    t.status = 'closed'
    note = S.decided.retarget.replace('{project}', target.name)
  } else if (option.action === 'close') {
    t.status = 'closed'
  } else if (option.action === 'adopt') {
    t.status = 'adopt-requested'
  } else {
    t.status = 'queued'
    t.approvals = [...(Array.isArray(t.approvals) ? t.approvals : []), { text: option.approval, label: option.label, at: iso() }]
  }
  t.decision = { option: option.id, label: option.label, action: option.action, at: iso() }
  t.updatedAt = iso()
  await writeJson($, path, t)
  return refresh($, note)
}

async function startRun($: EngineInterface, text: string, S: typeof EN) {
  await update($, message, () => S.started)
  void $.prompt.submit({ text })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'radar', description: 'Open the Tryout Radar panel: digest, projects, topics and trials' })
    return next(e)
  })

  on('command.run', { command: 'radar' }, async $ => {
    await refresh($)
    if (!(await $.store.get('seenIntro'))) {          // the first time, open on the introduction
      await update($, tab, () => 'about')
      await $.store.set('seenIntro', true)
    }
    await $.ui.open({ id: PANE, title: 'Tryout Radar' })
    return { text: 'Tryout Radar panel opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Link, Markdown, Input } = $.ui.resolve(e) as any
    const snap = (await read($, snapshot)) as TryoutRadarSnapshot | null
    const S = snap?.isZh ? ZH : EN
    const current = await read($, tab)
    const note = await read($, message)
    const opened = await read($, openTrial)
    const d = (await read($, draft)) as TryoutRadarDraft
    const canType = e.surface !== 'mobile' && Boolean(Input)   // mobile draws no Input: the forms are left out there

    if (!snap) {
      return (
        <Box flexDirection="column" gap={1}>
          <Text bold>{S.title}</Text>
          <Button key="load" label={S.refresh} onPress={() => void refresh($)} />
        </Box>
      )
    }
    if (!snap.isConfigured) {
      return (
        <Box flexDirection="column" gap={1}>
          <Text bold>{S.title}</Text>
          <Text>{S.notSetUp}</Text>
          <Box flexDirection="row" gap={1}>
            <Button key="setup" variant="primary" label={S.setUp} onPress={() => void startRun($, S.setupPrompt, S)} />
            <Button key="refresh" label={S.refresh} onPress={() => void refresh($)} />
            <Button key="what" label={S.whatIsThis} onPress={() => void update($, tab, v => (v === 'about' ? 'today' : 'about'))} />
          </Box>
          {note ? <Text dimColor>{note}</Text> : null}
          {current === 'about' ? <Markdown key="intro" text={INTRO} /> : null}
        </Box>
      )
    }

    const names: Record<string, TryoutRadarProject> = {}
    for (const p of snap.projects) names[p.key] = p
    const active = (key: string) => names[key] && names[key].status === 'active'
    const nameOf = (key: string) => names[key]?.name ?? key
    const setDraft = (patch: Partial<TryoutRadarDraft>) => void update($, draft, v => ({ ...(v ?? EMPTY_DRAFT), ...patch }))

    const tabs = (
      <Box flexDirection="row" gap={1} flexWrap="wrap">
        {(['today', 'projects', 'topics', 'trials', 'about'] as const).map(t => (
          <Button key={`tab-${t}`} label={S[t]} variant={current === t ? 'primary' : 'secondary'}
            onPress={() => void update($, tab, () => t)} />
        ))}
      </Box>
    )

    const field = (key: string, label: string, value: string, set: (v: string) => void) => (
      <Input key={key} label={label} value={value} onInput={(v: string) => set(v)} onSubmit={(v: string) => set(v)} />
    )
    const form = d.kind && canType ? (
      <Box key="form" flexDirection="column" gap={1} borderStyle="round" paddingX={1}>
        {field('in-name', S.name, d.name, v => setDraft({ name: v }))}
        {d.kind === 'project' ? field('in-path', S.folder, d.path, v => setDraft({ path: v })) : null}
        {field('in-about', S.about, d.about, v => setDraft({ about: v }))}
        {field('in-keywords', d.kind === 'project' ? S.interests : S.keywords, d.keywords, v => setDraft({ keywords: v }))}
        {d.kind === 'topic' ? (
          <Box flexDirection="column">
            <Text dimColor>{S.topicFor}</Text>
            <Box flexDirection="row" gap={1} flexWrap="wrap">
              {snap.projects.filter(p => p.status === 'active').map(p => (
                <Button key={`dp-${p.key}`} label={(d.projects.includes(p.key) ? S.marked : '') + p.name}
                  onPress={() => setDraft({ projects: d.projects.includes(p.key) ? d.projects.filter(k => k !== p.key) : [...d.projects, p.key] })} />
              ))}
            </Box>
          </Box>
        ) : null}
        <Box flexDirection="row" gap={1}>
          <Button key="save-draft" variant="primary" label={S.save} onPress={() => void saveDraft($, snap)} />
          <Button key="cancel-draft" label={S.cancel} onPress={() => void update($, draft, () => EMPTY_DRAFT)} />
        </Box>
      </Box>
    ) : null

    let body
    if (current === 'about') {
      body = <Markdown key="intro" text={INTRO} />
    } else if (current === 'today') {
      const order = [...snap.picks, ...snap.items.map(i => i.id).filter(id => !snap.picks.includes(id))]
      const items = order.map(id => snap.items.find(i => i.id === id)).filter((i): i is TryoutRadarItem => !!i)
      const fresh = snap.newProjects.filter(p => active(p.key))
      body = (
        <Box flexDirection="column" gap={1}>
          <Text dimColor>{snap.date}</Text>
          {snap.headline ? <Text>{snap.headline}</Text> : null}
          {items.length === 0 ? <Text dimColor>{S.noDigest}</Text> : null}
          {fresh.length > 0 ? (
            <Box flexDirection="column">
              <Text bold>{S.newDirections}</Text>
              {fresh.map(p => (
                <Box key={`np-${p.key}`} flexDirection="row" gap={1} flexWrap="wrap">
                  <Text>{nameOf(p.key)}: {p.why}</Text>
                  <Button key={`np-ig-${p.key}`} label={S.stopFollowing} onPress={() => void setProjectStatus($, snap, names[p.key], false)} />
                </Box>
              ))}
            </Box>
          ) : null}
          {items.slice(0, 20).map((it, i) => {
            const fits = it.projects.filter(p => active(p.key)).sort((a, b) => b.fit - a.fit)
            const best = fits.find(p => names[p.key].trialMode !== 'off')
            const status = snap.feedback[it.id]
            return (
              <Box key={`it-${it.id}`} flexDirection="column">
                <Text bold={i < snap.picks.length}>{i < snap.picks.length ? '★ ' : ''}{it.title}</Text>
                {fits[0] ? <Text dimColor>{nameOf(fits[0].key)}: {fits[0].how}</Text> : <Text dimColor>{it.summary}</Text>}
                <Box flexDirection="row" gap={1} flexWrap="wrap">
                  {it.url.startsWith('http') ? <Link href={it.url} label="↗" /> : null}
                  {best ? (
                    <Button key={`try-${it.id}`} label={`${S.tryIn} ${nameOf(best.key)}`}
                      onPress={() => void queueTrial($, snap, it, names[best.key])} />
                  ) : null}
                  <Button key={`want-${it.id}`} label={(status === 'want' ? S.marked : '') + S.want}
                    onPress={() => void mark($, snap, it, 'want')} />
                  <Button key={`skip-${it.id}`} label={(status === 'skip' ? S.marked : '') + S.skip}
                    onPress={() => void mark($, snap, it, 'skip')} />
                </Box>
              </Box>
            )
          })}
        </Box>
      )
    } else if (current === 'projects') {
      body = (
        <Box flexDirection="column" gap={1}>
          {snap.projects.map(p => (
            <Box key={`p-${p.key}`} flexDirection="row" gap={1} flexWrap="wrap">
              <Text bold={p.status === 'active'} dimColor={p.status !== 'active'}>{p.name}</Text>
              <Text dimColor>{S.source[p.source]} · {p.status === 'active' ? S.following : S.ignored}</Text>
              <Button key={`pt-${p.key}`} label={p.status === 'active' ? S.stopFollowing : S.follow}
                onPress={() => void setProjectStatus($, snap, p, p.status !== 'active')} />
            </Box>
          ))}
          {d.kind === 'project' ? form : canType ? (
            <Button key="add-project" label={`+ ${S.addProject}`} onPress={() => setDraft({ ...EMPTY_DRAFT, kind: 'project' })} />
          ) : null}
        </Box>
      )
    } else if (current === 'topics') {
      body = (
        <Box flexDirection="column" gap={1}>
          {snap.topics.map(t => (
            <Box key={`tp-${t.key}`} flexDirection="column">
              <Box flexDirection="row" gap={1} flexWrap="wrap">
                <Text bold={t.status === 'active'} dimColor={t.status !== 'active'}>{t.name}</Text>
                <Text dimColor>
                  {S.source[t.source]} · {t.status === 'active' ? S.active : S.paused} · {t.projects.length ? `${S.forSome} ${t.projects.map(nameOf).join(', ')}` : S.forAll}
                </Text>
                {t.source === 'custom' ? (
                  <Button key={`tt-${t.key}`} label={t.status === 'active' ? S.pause : S.resume}
                    onPress={() => void changeTopic($, snap, t.key, x => { x.status = t.status === 'active' ? 'paused' : 'active' })} />
                ) : null}
              </Box>
              {t.focus ? <Text dimColor>{t.focus}</Text> : null}
              {t.source === 'custom' ? (
                <Box flexDirection="row" gap={1} flexWrap="wrap">
                  {snap.projects.filter(p => p.status === 'active').map(p => (
                    <Button key={`tl-${t.key}-${p.key}`} label={(t.projects.includes(p.key) ? S.marked : '') + p.name}
                      onPress={() => void changeTopic($, snap, t.key, x => {
                        const list: string[] = Array.isArray(x.projects) ? x.projects : []
                        x.projects = list.includes(p.key) ? list.filter(k => k !== p.key) : [...list, p.key]
                      })} />
                  ))}
                </Box>
              ) : null}
            </Box>
          ))}
          <Text dimColor>{S.configTopic}</Text>
          {d.kind === 'topic' ? form : canType ? (
            <Button key="add-topic" label={`+ ${S.addTopic}`} onPress={() => setDraft({ ...EMPTY_DRAFT, kind: 'topic' })} />
          ) : null}
        </Box>
      )
    } else {
      body = (
        <Box flexDirection="column" gap={1}>
          {snap.trials.length === 0 ? <Text dimColor>{S.noTrials}</Text> : null}
          {snap.trials.map((t: TryoutRadarTrial) => {
            const canChoose = !t.decision && ['done', 'blocked', 'failed', 'adopted'].includes(t.status) && t.options.length > 0
            return (
              <Box key={`t-${t.tid}`} flexDirection="column">
                <Text bold>
                  {S.status[t.status] ?? t.status}{t.verdict && t.status === 'done' ? ` · ${S.verdict[t.verdict] ?? t.verdict}` : ''} <Text dimColor>{t.title} → {nameOf(t.project)}</Text>
                </Text>
                {t.headline ? <Text>{t.headline}</Text> : null}
                {canChoose && t.ask ? <Text color="yellow">{S.yourCall} {t.ask}</Text> : null}
                {canChoose ? (
                  <Box flexDirection="column">
                    {t.options.map(o => (
                      <Button key={`opt-${t.tid}-${o.id}`} plain onPress={() => void decideTrial($, snap, t, o)}>
                        [{o.label}] <Text dimColor>{o.effect}</Text>
                      </Button>
                    ))}
                  </Box>
                ) : null}
                {t.decision ? <Text dimColor>{S.youChose} {t.decision}</Text> : null}
                {t.report ? (
                  <Button key={`tb-${t.tid}`} plain label={opened === t.tid ? S.hideDetails : `${S.techDetails} ›`}
                    onPress={() => void update($, openTrial, v => (v === t.tid ? '' : t.tid))} />
                ) : null}
                {opened === t.tid && t.report ? <Markdown key={`tm-${t.tid}`} text={t.report} /> : null}
              </Box>
            )
          })}
        </Box>
      )
    }

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="row" gap={1} flexWrap="wrap">
          <Text bold>{snap.title}</Text>
          <Button key="about-top" plain label={`(${S.whatIsThis})`} onPress={() => void update($, tab, () => 'about')} />
        </Box>
        {tabs}
        {note ? <Text color="green">{note}</Text> : null}
        {body}
        <Box flexDirection="row" gap={1} flexWrap="wrap">
          <Button key="scout" variant="primary" label={S.runScout} onPress={() => void startRun($, S.scoutPrompt, S)} />
          <Button key="trials" label={S.runTrials} onPress={() => void startRun($, S.trialPrompt, S)} />
          <Button key="refresh" label={S.refresh} onPress={() => void refresh($)} />
          {snap.baseUrl.startsWith('https://') ? <Link href={snap.baseUrl} label={S.openSite} /> : null}
        </Box>
      </Box>
    )
  })
}
