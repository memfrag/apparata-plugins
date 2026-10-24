export type StageState = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

export type ReleaseStage = {
  id: string
  title: string
  state: StageState
  startedAt: number | null
  endedAt: number | null
  note: string
  log: string
}

/** build/release-status.json as a release script writes it (times in epoch seconds). */
export type ReleaseStatus = {
  runId: string
  appName: string
  projectDir: string
  dryRun: boolean
  state: 'running' | 'done' | 'failed'
  startedAt: number
  endedAt: number | null
  updatedAt: number
  version: string
  dmgPath: string
  dmgSize: number | null
  waiting: string
  error: string
  stages: ReleaseStage[]
}

declare module 'claude-code' {
  interface PluginState {
    'release-pane-plugin': {
      status: ReleaseStatus | null
      /** Epoch seconds, advanced each second while a run is going so elapsed times tick. */
      now: number
    }
  }
}
