
export const HOME = '/home/u/.tryout-radar'
export const PANE = { component: 'Pane', requestId: 'tryout-radar' } as const
export const PROPS = { title: 'Tryout Radar', isFocused: true, bodyColumns: 70, bodyRows: 40, placement: 'dock' } as any

export const REPORT = {
  date: '2026-10-24',
  headline: 'Two good finds today',
  picks: ['gh-a-b'],
  items: [
    { id: 'gh-a-b', title: 'a/b sticker maker', url: 'https://github.com/a/b', category: 'aigc', summary: 'Makes stickers',
      verdict: 'try', effort: '10 min', projects: [{ key: 'shop-stickers', fit: 3, how: 'Generate the sticker set' }] },
    { id: 'gh-c-d', title: 'c/d test runner', url: 'https://github.com/c/d', category: 'web', summary: 'Runs tests',
      verdict: 'save', effort: '1 h', projects: [{ key: 'shop', fit: 2, how: 'E2E tests for checkout' }] },
  ],
  newProjects: [{ key: 'shop-stickers', parent: 'shop', why: '5 sessions about stickers' }],
  _projects: { shop: { name: 'Web shop', trial_mode: 'try' }, 'shop-stickers': { name: 'Shop stickers', trial_mode: 'assess' } },
}

export function fakeDisk(on: any, files: Record<string, string>) {
  const writes: Record<string, string> = {}
  const prompts: string[] = []
  const all = () => ({ ...files, ...writes })
  const norm = (p: string) => p.replace(/^[A-Za-z]:/, '').split(String.fromCharCode(92)).join('/')
  on('env.get', ($: any, e: any) => ({ value: e.name === 'HOME' ? '/home/u' : undefined }))
  on('fs.exists', ($: any, e: any) => ({ value: Object.keys(all()).some(p => p === norm(e.path) || p.startsWith(norm(e.path) + '/')) }))
  on('fs.read', ($: any, e: any) => {
    const v = all()[norm(e.path)]
    if (v === undefined) throw new Error('ENOENT ' + norm(e.path))
    return { value: v }
  })
  on('fs.list', ($: any, e: any) => {
    const names = new Set<string>()
    for (const p of Object.keys(all())) if (p.startsWith(norm(e.path) + '/')) names.add(p.slice(norm(e.path).length + 1).split('/')[0])
    return { value: [...names].map(name => ({ name, kind: 'file', size: 1, mtimeMs: 0, isLink: false })) }
  })
  on('fs.write', ($: any, e: any) => { writes[norm(e.path)] = e.text; return { value: undefined } })
  on('prompt.submit', ($: any, e: any) => { prompts.push(e.text); return { text: e.text } })
  return { writes, prompts }
}

