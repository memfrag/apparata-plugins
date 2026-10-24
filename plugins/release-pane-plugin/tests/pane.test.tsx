import { expect, test } from 'claude-code/testing'

import type { ReleaseStage, ReleaseStatus } from '../types'

const PANE = {
  plugin: 'release-pane-plugin',
  component: 'Pane',
  requestId: 'release',
  props: {
    title: 'Release',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

function stage(id: string, title: string, rest: Partial<ReleaseStage>): ReleaseStage {
  return { id, title, state: 'pending', startedAt: null, endedAt: null, note: '', log: '', ...rest }
}

const FAILED: ReleaseStatus = {
  runId: '1-1',
  appName: 'Rigly',
  projectDir: '/p',
  dryRun: true,
  state: 'failed',
  startedAt: 1000,
  endedAt: 1400,
  updatedAt: 1400,
  version: '1.0.0',
  dmgPath: '',
  dmgSize: null,
  waiting: '',
  error: 'Archive failed. See /p/build/archive.log for details.',
  stages: [
    stage('clean', 'Clean build directory', { state: 'done', startedAt: 1000, endedAt: 1001 }),
    stage('archive', 'Archive', { state: 'failed', startedAt: 1001, endedAt: 1400, log: '/p/build/archive.log' }),
    stage('notarize', 'Notarize', { state: 'skipped', note: 'dry run' }),
  ],
}

test('a failed run names the stage and its log, on every surface', async ($, on) => {
  // Each hook here stands for the engine beneath the mod.
  let opened = 0
  on('command.register', () => ({ value: { command: 'release-pane' } }))
  on('ui.open', () => {
    opened += 1
    return { value: { isPlaced: true } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('clock.now', () => ({ value: 1_500_000 }))
  on('clock.every', () => ({ value: undefined }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 5, isLink: false } }))
  on('fs.read', () => ({ value: JSON.stringify(FAILED) }))

  await $.session.start({ cwd: '/p', surface: 'desktop', isInteractive: true })
  await $.command.run({
    command: 'release-pane',
    args: '',
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 },
  })
  expect(opened).toBeGreaterThan(0)

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text', text: /Archive failed:/ }))?.text).toBe(
      'Archive failed: Archive failed. See /p/build/archive.log for details.',
    )
    expect((await ui.find({ type: 'Text', text: /^See / }))?.text).toBe('See build/archive.log')
    expect((await ui.find({ type: 'Text', text: /6m 39s/ }))?.text).toBe('6m 39s')
    expect((await ui.find({ type: 'Text', text: /^Rigly/ }))?.text).toBe('Rigly 1.0.0 · dry run')
    expect(await ui.find({ type: 'Text', text: /Notarize/ })).toBeDefined()
    await ui.unmount()
  }
})
