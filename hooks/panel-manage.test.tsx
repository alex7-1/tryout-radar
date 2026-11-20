import { describe, expect, test } from 'claude-code/testing'

import { HOME, PANE, PROPS, REPORT, fakeDisk } from './panel-fake'

const WITH_TOPICS = {
  ...REPORT,
  _topics: [{ key: 'web', name: 'Web design', focus: 'Pages that convert', projects: [], source: 'config', status: 'active' }],
}

describe('Tryout Radar panel: your own projects and topics', () => {
  test('switches projects, adds a project and a topic tied to projects', async ($, on) => {
    const { writes } = fakeDisk(on, {
      [`${HOME}/config.toml`]: 'language = "zh-CN"\n',
      [`${HOME}/data/reports/2026-10-24.json`]: JSON.stringify(WITH_TOPICS),
    })
    const ui = await $.ui.mount({ plugin: 'tryout-radar', surface: 'desktop', ...PANE, props: PROPS })
    const txt = async () => (await ui.find({ type: 'Box' }))?.text ?? ''
    await ui.press({ key: (await ui.find({ key: 'load' })) ? 'load' : 'refresh' })

    await ui.press({ key: 'tab-projects' })
    await ui.press({ key: 'pt-shop' })                       // a project from config.toml: switched off by override
    expect(JSON.parse(writes[`${HOME}/data/project-overrides.json`])).toEqual({ shop: 'ignored' })
    expect(await txt()).toContain('不关注')
    await ui.press({ key: 'pt-shop' })
    expect(JSON.parse(writes[`${HOME}/data/project-overrides.json`])).toEqual({ shop: 'active' })

    await ui.press({ key: 'add-project' })
    await ui.input({ key: 'in-name', text: 'Sticker shop' })
    await ui.input({ key: 'in-path', text: '~/code/stickers' })
    await ui.input({ key: 'in-keywords', text: 'sticker generator, 表情包' })
    await ui.press({ key: 'save-draft' })
    const added = JSON.parse(writes[`${HOME}/data/projects.auto.json`]).find((p: any) => p.key === 'sticker-shop')
    expect([added.source, added.status, added.path, added.interests]).toEqual(['manual', 'active', '~/code/stickers', ['sticker generator', '表情包']])
    expect(await txt()).toContain('Sticker shop')

    await ui.press({ key: 'tab-topics' })
    expect(await txt()).toContain('Web design')
    await ui.press({ key: 'add-topic' })
    await ui.input({ key: 'in-name', text: 'Sticker packs' })
    await ui.input({ key: 'in-keywords', text: 'sticker, animated sticker' })
    await ui.press({ key: 'dp-sticker-shop' })
    await ui.press({ key: 'save-draft' })
    let topic = JSON.parse(writes[`${HOME}/data/topics.custom.json`])[0]
    expect([topic.key, topic.projects, topic.github_queries]).toEqual(['sticker-packs', ['sticker-shop'], ['sticker', 'animated sticker']])
    await ui.press({ key: 'tl-sticker-packs-shop' })         // tie it to one more project
    await ui.press({ key: 'tt-sticker-packs' })              // pause it
    topic = JSON.parse(writes[`${HOME}/data/topics.custom.json`])[0]
    expect([topic.projects, topic.status]).toEqual([['sticker-shop', 'shop'], 'paused'])
    expect(await txt()).toContain('已停用')
    await ui.unmount()
  })

  test('the forms are left out where a surface cannot type', async ($, on) => {
    fakeDisk(on, { [`${HOME}/config.toml`]: '', [`${HOME}/data/reports/2026-10-24.json`]: JSON.stringify(WITH_TOPICS) })
    const ui = await $.ui.mount({ plugin: 'tryout-radar', surface: 'mobile', ...PANE, props: PROPS })
    await ui.press({ key: (await ui.find({ key: 'load' })) ? 'load' : 'refresh' })
    await ui.press({ key: 'tab-projects' })
    expect(await ui.find({ key: 'add-project' })).toBeUndefined()
    expect(await ui.find({ key: 'pt-shop' })).toBeDefined()
    await ui.unmount()
  })
})
