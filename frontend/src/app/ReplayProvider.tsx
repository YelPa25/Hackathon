import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchMissionData } from '../services/mission'
import type { ReplayAction, ReplaySpeed, ReplayView } from '../services/mission'
import { ReplayContext } from '../services/replay-state'

function message(error: unknown) {
  return error instanceof Error && error.name === 'Error' ? error.message : 'Replay connection unavailable.'
}

export function ReplayProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ReplayView>()
  const [pollError, setPollError] = useState<string>()
  const [commandError, setCommandError] = useState<string>()
  const [pending, setPending] = useState(false)
  const busy = useRef(false)
  const generation = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      const version = generation.current
      let interval = 800
      try {
        const latest = await fetchMissionData<ReplayView>('/api/replay', controller.signal)
        interval = latest.status === 'RUNNING' ? 250 : 800
        if (!controller.signal.aborted && !busy.current && version === generation.current) {
          setState((previous) => previous?.revision === latest.revision && previous.playback_error === latest.playback_error
            ? previous : latest)
          setPollError(undefined)
        }
      } catch (error) {
        if (!controller.signal.aborted && version === generation.current) setPollError(message(error))
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, interval)
      }
    }
    void poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [])

  async function send(action: ReplayAction, speed?: ReplaySpeed) {
    if (!state || busy.current) return
    busy.current = true
    generation.current++
    setPending(true)
    setCommandError(undefined)
    try {
      const latest = await fetchMissionData<ReplayView>('/api/replay', AbortSignal.timeout(6000), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: action, expected_revision: state.revision, speed }),
      })
      setState(latest)
      setPollError(undefined)
    } catch (error) {
      setCommandError(message(error))
    } finally {
      generation.current++
      busy.current = false
      setPending(false)
    }
  }

  return <ReplayContext.Provider value={{ state, pending, offline: Boolean(pollError), error: pollError ?? commandError, send }}>
    {children}
  </ReplayContext.Provider>
}
