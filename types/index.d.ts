export type TryoutRadarItem = {
  id: string
  title: string
  url: string
  category: string
  summary: string
  verdict: string
  effort: string
  projects: { key: string; fit: number; how: string }[]
}

export type TryoutRadarProject = {
  key: string
  name: string
  trialMode: string
  source: 'config' | 'discovered' | 'manual'
  status: 'active' | 'ignored'
}

export type TryoutRadarTopic = {
  key: string
  name: string
  focus: string
  projects: string[]
  source: 'config' | 'custom'
  status: 'active' | 'paused'
}

export type TryoutRadarOption = {
  id: string
  label: string
  effect: string
  action: 'continue' | 'retarget' | 'close' | 'adopt'
  project: string
  approval: string
}

export type TryoutRadarTrial = {
  tid: string
  itemId: string
  title: string
  project: string
  status: string
  verdict: string
  summary: string
  headline: string
  ask: string
  options: TryoutRadarOption[]
  decision: string
  report: string
}

export type TryoutRadarSnapshot = {
  home: string
  dataDir: string
  isZh: boolean
  title: string
  baseUrl: string
  isConfigured: boolean
  date: string
  headline: string
  items: TryoutRadarItem[]
  picks: string[]
  projects: TryoutRadarProject[]
  topics: TryoutRadarTopic[]
  newProjects: { key: string; why: string }[]
  feedback: Record<string, string>
  trials: TryoutRadarTrial[]
}

export type TryoutRadarDraft = {
  kind: '' | 'project' | 'topic'
  name: string
  path: string
  about: string
  keywords: string
  projects: string[]
}

declare module 'claude-code' {
  interface PluginState {
    'tryout-radar': {
      tab: 'today' | 'projects' | 'topics' | 'trials' | 'about'
      snapshot: TryoutRadarSnapshot | null
      openTrial: string
      message: string
      draft: TryoutRadarDraft
    }
  }
}
