import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { ReleaseStage, ReleaseStatus, StageState } from '../types'

const PANE = 'release'
const TITLE = 'Release'
const DEFAULT_STATUS_PATH = 'build/release-status.json'
// A finished run this recent still opens the pane when the mod first sees it.
const RECENT_SECONDS = 120

const status = atom({ plugin: 'release-pane-plugin', key: 'status' } as const, null)
const now = atom({ plugin: 'release-pane-plugin', key: 'now' } as const, 0)

const MARK: Record<StageState, string> = {
  pending: '○',
  running: '●',
  done: '✓',
  failed: '✗',
  skipped: '–',
}

const COLOR: Record<StageState, string | undefined> = {
  pending: undefined,
  running: 'warning',
  done: 'success',
  failed: 'error',
  skipped: undefined,
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rest = String(s % 60).padStart(2, '0')
  if (m < 60) return `${m}m ${rest}s`

  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`
}

function stageElapsed(stage: ReleaseStage, at: number): string {
  if (stage.startedAt === null) return ''

  return formatElapsed((stage.endedAt ?? at) - stage.startedAt)
}

function relativeTo(path: string, root: string): string {
  return root !== '' && path.startsWith(root + '/') ? path.slice(root.length + 1) : path
}

function formatSize(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`
}

let path = DEFAULT_STATUS_PATH
let lastMtime = -1
let openedRunId: string | undefined

async function poll($: EngineInterface): Promise<void> {
  const seconds = Math.floor((await $.clock.now()) / 1000)
  const stat = await $.fs.stat(path).catch(() => undefined)
  if (stat !== undefined && stat.mtimeMs !== lastMtime) {
    const text = await $.fs.read(path).catch(() => undefined)
    let next: ReleaseStatus | undefined
    try {
      next = typeof text === 'string' ? (JSON.parse(text) as ReleaseStatus) : undefined
    } catch {
      // Caught mid-write: the next tick reads it again.
    }
    if (next !== undefined) {
      lastMtime = stat.mtimeMs
      const fresh = next
      await update($, status, () => fresh)
      const isRecent =
        fresh.state === 'running' || seconds - (fresh.endedAt ?? fresh.updatedAt) < RECENT_SECONDS
      if (fresh.runId !== openedRunId && isRecent) {
        openedRunId = fresh.runId
        void $.ui.open({ id: PANE, title: TITLE })
      }
    }
  }
  const current = await read($, status)
  if (current?.state === 'running') await update($, now, () => seconds)
}

export const register: Register = (on, options) => {
  const configured = typeof options.statusPath === 'string' ? options.statusPath.trim() : ''
  const statusPath = configured !== '' ? configured : DEFAULT_STATUS_PATH

  on('session.start', async ($, e, next) => {
    path = statusPath.startsWith('/') ? statusPath : `${e.cwd}/${statusPath}`
    await $.command.register({
      name: 'release-pane',
      description: 'Show the stages of the release build in a pane',
    })
    await update($, now, () => 0)
    $.clock.every(1000, () => void poll($))

    return next(e)
  })

  on('command.run', { command: 'release-pane' }, async $ => {
    await poll($)
    await $.ui.open({ id: PANE, title: TITLE })

    return { text: 'Release pane opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const run = await read($, status)
    if (run === null) {
      return (
        <Box flexDirection="column">
          <Text dimColor>No release run yet.</Text>
          <Text dimColor>The pane follows {statusPath}, which the release script writes.</Text>
        </Box>
      )
    }

    const ticked = await read($, now)
    const at = run.state === 'running' ? Math.max(ticked, run.updatedAt) : (run.endedAt ?? run.updatedAt)
    const failed = run.stages.find(stage => stage.state === 'failed')
    const heading = `${run.appName || 'Release'} ${run.version || '…'}${run.dryRun ? ' · dry run' : ''}`
    const summary =
      run.state === 'running'
        ? `running · ${formatElapsed(at - run.startedAt)}`
        : run.state === 'done'
          ? `done in ${formatElapsed(at - run.startedAt)}`
          : `failed after ${formatElapsed(at - run.startedAt)}`

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>{heading}</Text>
          <Text color={run.state === 'failed' ? 'error' : run.state === 'done' ? 'success' : undefined}>
            {summary}
          </Text>
          {run.waiting !== '' && <Text color="warning">{run.waiting}</Text>}
        </Box>
        <Box flexDirection="column">
          {run.stages.map((stage, index) => (
            <Box key={stage.id} flexDirection="row" gap={1}>
              <Box flexShrink={0}>
                <Text color={COLOR[stage.state]} dimColor={stage.state === 'pending' || stage.state === 'skipped'}>
                  {MARK[stage.state]} {String(index + 1).padStart(2, ' ')}. {stage.title}
                </Text>
              </Box>
              {stage.startedAt !== null && (
                <Box flexShrink={0}>
                  <Text dimColor tabular>
                    {stageElapsed(stage, at)}
                  </Text>
                </Box>
              )}
              {stage.note !== '' && (
                // The note gives way first: cut at the pane's edge, wherever that is.
                <Box flexShrink={1} minWidth={0}>
                  <Text dimColor wrap="truncate-end">
                    {stage.note}
                  </Text>
                </Box>
              )}
            </Box>
          ))}
        </Box>
        {run.state === 'failed' && (
          <Box flexDirection="column">
            <Text color="error">
              {failed ? `${failed.title} failed` : 'The run failed'}
              {run.error !== '' ? `: ${run.error}` : ''}
            </Text>
            <Text dimColor>
              {failed && failed.log !== ''
                ? `See ${relativeTo(failed.log, run.projectDir)}`
                : 'See the script output in the terminal.'}
            </Text>
          </Box>
        )}
        {run.state === 'done' && run.dmgPath !== '' && (
          <Text color="success">
            {relativeTo(run.dmgPath, run.projectDir)}
            {run.dmgSize !== null ? ` · ${formatSize(run.dmgSize)}` : ''}
            {run.dryRun ? ' · not notarized, not released' : ''}
          </Text>
        )}
      </Box>
    )
  })
}
