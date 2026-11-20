import { describe, expect, test } from 'claude-code/testing'

import { HOME, PANE, PROPS, REPORT, fakeDisk } from './panel-fake'

describe('Tryout Radar panel', () => {
  test('asks to set up when there is no config', async ($, on) => {
    const { prompts } = fakeDisk(on, {})
    for (const surface of ['terminal', 'desktop'] as const) {
      const ui = await $.ui.mount({ plugin: 'tryout-radar', surface, ...PANE, props: PROPS })
      if (await ui.find({ key: 'load' })) await ui.press({ key: 'load' })
      expect((await ui.find({ type: 'Box' }))?.text ?? '').toContain('not set up')
      await ui.press({ key: 'setup' })
      await ui.unmount()
    }
    expect(prompts.some(p => p.includes('set up Tryout Radar'))).toBe(true)
  })

})

describe('Tryout Radar panel: About', () => {
  test('explains itself in Chinese and English, before and after setup', async ($, on) => {
    fakeDisk(on, {})
    for (const surface of ['terminal', 'desktop', 'mobile'] as const) {
      const ui = await $.ui.mount({ plugin: 'tryout-radar', surface, ...PANE, props: PROPS })
      await ui.press({ key: (await ui.find({ key: 'load' })) ? 'load' : 'refresh' })
      await ui.press({ key: 'what' })
      const text = (await ui.find({ key: 'intro' }))?.text ?? JSON.stringify(await ui.find({ key: 'intro' }))
      expect(text).toContain('试用雷达')
      expect(text).toContain('How it works')
      await ui.press({ key: 'what' })
      expect(await ui.find({ key: 'intro' })).toBeUndefined()
      await ui.unmount()
    }
  })
})
