import { describe, expect, test } from 'claude-code/testing'

import { HOME, PANE, PROPS, REPORT, fakeDisk } from './panel-fake'

const BLOCKED = {
  tid: '20261024-172846-shop', status: 'blocked', verdict: 'decide', itemId: 'gh-a-b', project: 'shop', date: '2026-10-24',
  item: { title: 'a/b sticker maker' }, summary: 'tech summary',
  plain: { headline: 'Stuck: it wants to install a plugin into your image tool', ask: 'Install a separate copy?' },
  options: [
    { id: 'go', label: 'Yes, a separate copy', effect: 'Installs tonight', action: 'continue', approval: 'Owner allows a separate copy' },
    { id: 'move', label: 'Try it in stickers', effect: 'Fits better', action: 'retarget', project: 'shop-stickers' },
    { id: 'close', label: 'Not now', effect: 'Ends here', action: 'close' },
  ],
  report_md: '## Tech\n- npm ci',
}

describe('Tryout Radar panel: choices on a trial report', () => {
  test('shows the plain headline and records the choice', async ($, on) => {
    const { writes } = fakeDisk(on, {
      [`${HOME}/config.toml`]: 'language = "en"\n',
      [`${HOME}/data/reports/2026-10-24.json`]: JSON.stringify(REPORT),
      [`${HOME}/data/projects.auto.json`]: JSON.stringify([{ key: 'shop-stickers', name: 'Shop stickers', trial_mode: 'assess', status: 'active' }]),
      [`${HOME}/data/trials/20261024-172846-shop.json`]: JSON.stringify(BLOCKED),
    })
    const ui = await $.ui.mount({ plugin: 'tryout-radar', surface: 'desktop', ...PANE, props: PROPS })
    const txt = async () => (await ui.find({ type: 'Box' }))?.text ?? ''
    await ui.press({ key: (await ui.find({ key: 'load' })) ? 'load' : 'refresh' })
    await ui.press({ key: 'tab-trials' })
    expect(await txt()).toContain('Stuck: it wants to install a plugin')
    expect(await txt()).toContain('Install a separate copy?')
    expect(await txt()).not.toContain('npm ci')                     // technical layer hidden until asked
    await ui.press({ key: 'opt-20261024-172846-shop-move' })
    const t = JSON.parse(writes[`${HOME}/data/trials/20261024-172846-shop.json`])
    expect([t.status, t.decision.option]).toEqual(['closed', 'move'])
    const moved = Object.keys(writes).find(p => /trials\/\d{8}-\d{6}-shop-stickers\.json$/.test(p))
    expect(JSON.parse(writes[moved!]).status).toBe('queued')
    expect(await txt()).toContain('You chose: Try it in stickers')
    expect(await ui.find({ key: 'opt-20261024-172846-shop-go' })).toBeUndefined()
    await ui.unmount()
  })
})
