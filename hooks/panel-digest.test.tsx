import { describe, expect, test } from 'claude-code/testing'

import { HOME, PANE, PROPS, REPORT, fakeDisk } from './panel-fake'

describe('Tryout Radar panel', () => {
  test('shows the digest and writes trials, marks and ignores', async ($, on) => {
    const { writes } = fakeDisk(on, {
      [`${HOME}/config.toml`]: 'language = "en"\n[site]\ntitle = "My Radar"\nbase_url = "https://r.example.com/x/"\n',
      [`${HOME}/data/reports/2026-10-23.json`]: JSON.stringify({ date: '2026-10-23', items: [] }),
      [`${HOME}/data/reports/2026-10-24.json`]: JSON.stringify(REPORT),
      [`${HOME}/data/projects.auto.json`]: JSON.stringify([{ key: 'shop-stickers', name: 'Shop stickers', trial_mode: 'assess', status: 'active' }]),
      [`${HOME}/data/trials/20261023-220000-shop.json`]: JSON.stringify({
        tid: '20261023-220000-shop', status: 'done', verdict: 'adopt', itemId: 'gh-x', project: 'shop',
        item: { title: 'x/y' }, summary: 'Works well', report_md: '## Verdict\nadopt' }),
    })
    for (const surface of ['terminal', 'desktop'] as const) {
      const ui = await $.ui.mount({ plugin: 'tryout-radar', surface, ...PANE, props: PROPS })
      const txt = async () => (await ui.find({ type: 'Box' }))?.text ?? ''
      await ui.press({ key: (await ui.find({ key: 'load' })) ? 'load' : 'refresh' })
      expect(await ui.find({ text: /a\/b sticker maker/ })).toBeDefined()
      expect(await txt()).toContain('5 sessions about stickers')
      await ui.press({ key: 'tab-trials' })
      expect(await txt()).toContain('Works well')
      await ui.press({ key: 'tb-20261023-220000-shop' })
      expect(await txt()).toContain('Verdict')
      await ui.press({ key: 'tb-20261023-220000-shop' })   // close it again: pane state is shared across surfaces
      expect(await txt()).not.toContain('Verdict')
      await ui.press({ key: 'tab-today' })
      await ui.unmount()
    }
    const ui = await $.ui.mount({ plugin: 'tryout-radar', surface: 'desktop', ...PANE, props: PROPS })
    await ui.press({ key: 'refresh' })
    await ui.press({ key: 'try-gh-c-d' })
    const trialPath = Object.keys(writes).find(p => /\/data\/trials\/\d{8}-\d{6}-shop\.json$/.test(p))
    expect(trialPath).toBeDefined()
    const trial = JSON.parse(writes[trialPath!])
    expect([trial.status, trial.itemId, trial.project, trial.mode]).toEqual(['queued', 'gh-c-d', 'shop', 'try'])
    await ui.press({ key: 'want-gh-a-b' })
    expect(JSON.parse(writes[`${HOME}/data/feedback.json`])['gh-a-b'].status).toBe('want')
    await ui.press({ key: 'np-ig-shop-stickers' })
    expect(JSON.parse(writes[`${HOME}/data/projects.auto.json`])[0].status).toBe('ignored')
    await ui.unmount()
  })
})
