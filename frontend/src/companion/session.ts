import { useRef, useState } from 'react'

export const MESSAGE_LIMIT = 2000
const CONTEXT_LIMIT = 6500
const HISTORY_TURNS = 6
const CHAT_TIMEOUT = 82_000
const encoder = new TextEncoder()

export type Turn = { question: string; answer: string; truncated: boolean }
type HistoryMessage = { role: 'user' | 'assistant'; content: string }
type Pending = { question: string; error?: string }

export type ModelStatus = {
  ready: boolean
  issue: 'ollama_unavailable' | 'model_missing' | 'invalid_runtime_response' | null
}

export function byteLength(text: string) {
  return encoder.encode(text).length
}

function historyFor(turns: Turn[], question: string): HistoryMessage[] {
  const history: HistoryMessage[] = []
  let size = byteLength(question)
  for (const turn of turns.slice(-HISTORY_TURNS).reverse()) {
    size += byteLength(turn.question) + byteLength(turn.answer)
    if (size > CONTEXT_LIMIT) break
    history.unshift({ role: 'user', content: turn.question }, { role: 'assistant', content: turn.answer })
  }
  return history
}

export async function checkModel(signal: AbortSignal): Promise<ModelStatus> {
  const response = await fetch('/api/companion/status', {
    cache: 'no-store', signal: AbortSignal.any([signal, AbortSignal.timeout(4500)]),
  })
  if (!response.ok) throw new Error('Could not check Companion availability.')
  const result: ModelStatus = await response.json()
  if (typeof result.ready !== 'boolean') throw new Error('Could not check Companion availability.')
  return result
}

export function useCompanionSession() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState<Pending | null>(null)
  const inFlight = useRef(false)
  const draft = useRef('')

  function send(text: string) {
    const question = text.trim()
    if (inFlight.current || !question || byteLength(question) > MESSAGE_LIMIT) return false
    inFlight.current = true
    setPending({ question })
    void (async () => {
      try {
        const response = await fetch('/api/companion/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: question, history: historyFor(turns, question) }),
          signal: AbortSignal.timeout(CHAT_TIMEOUT),
        })
        const payload = await response.json().catch(() => null)
        if (!response.ok || typeof payload?.text !== 'string' || !payload.text.trim()) {
          throw new Error(payload?.error?.message ?? 'Companion could not get a reply. Try again.')
        }
        setTurns((previous) => [...previous, { question, answer: payload.text, truncated: payload.truncated === true }])
        setPending(null)
      } catch (error) {
        const message = error instanceof DOMException && error.name === 'TimeoutError'
          ? 'Qwen took too long to reply. Try again.'
          : error instanceof Error && error.name !== 'TypeError'
            ? error.message
            : 'Could not connect to the ASTRA backend. Try again.'
        setPending({ question, error: message })
      } finally {
        inFlight.current = false
      }
    })()
    return true
  }

  function clear() {
    if (inFlight.current) return false
    setTurns([])
    setPending(null)
    draft.current = ''
    return true
  }

  function editFailed() {
    if (!pending?.error || inFlight.current) return
    setPending(null)
    draft.current = pending.question
    return pending.question
  }

  return { turns, pending, draft, send, clear, editFailed }
}

export type CompanionSession = ReturnType<typeof useCompanionSession>
