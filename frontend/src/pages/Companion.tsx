import { ArrowUp, BookOpen, Clipboard, Gamepad2, Globe, Lightbulb, MessageCircle, Plus, Telescope } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ReplyText } from '../companion/ReplyText'
import { byteLength, checkModel, MESSAGE_LIMIT } from '../companion/session'
import type { CompanionSession, ModelStatus } from '../companion/session'
import '../styles/companion.css'

const starters = [
  { icon: BookOpen, text: 'Tell me a story.' },
  { icon: Lightbulb, text: 'Teach me something interesting.' },
  { icon: Gamepad2, text: "Let's play a game." },
  { icon: Telescope, text: 'Give me a science quiz.' },
  { icon: Globe, text: "Let's talk about life on Earth." },
  { icon: MessageCircle, text: 'Surprise me with an interesting topic.' },
]

type Availability = ModelStatus | 'checking' | 'backend-unavailable'

function describeAvailability(status: Availability) {
  if (status === 'checking') return 'Checking local model…'
  if (status === 'backend-unavailable') return 'Companion could not reach the ASTRA backend.'
  if (status.ready) return 'Qwen3 · Running locally'
  if (status.issue === 'model_missing') return 'The approved Qwen3 model is missing from Ollama.'
  if (status.issue === 'ollama_unavailable') return 'Ollama is unavailable. Start it locally, then check again.'
  return 'Could not verify the Ollama model. Check again.'
}

function AssistantReply({ text, truncated }: { text: string; truncated: boolean }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  return <li className="companion-message assistant">
    <span className="companion-speaker">ASTRA Companion</span>
    <ReplyText text={text} />
    {truncated && <p className="companion-note">Reply reached the length limit.</p>}
    <div className="companion-copy">
      <button type="button" className="companion-button" onClick={() => void copy()} aria-label="Copy response">
        <Clipboard size={15} aria-hidden="true" />{copyState === 'copied' ? 'Copied' : 'Copy'}
      </button>
      {copyState !== 'idle' && <span className="companion-note" role="status">
        {copyState === 'copied' ? 'Response copied.' : 'Clipboard unavailable. Select the text to copy it.'}
      </span>}
    </div>
  </li>
}

export default function Companion({ session }: { session: CompanionSession }) {
  const [availability, setAvailability] = useState<Availability>('checking')
  const [draft, setDraft] = useState(() => session.draft.current)
  const editor = useRef<HTMLTextAreaElement>(null)
  const transcript = useRef<HTMLDivElement>(null)
  const statusRequest = useRef<AbortController | null>(null)
  const { turns, pending } = session
  const ready = typeof availability === 'object' && availability.ready
  const waiting = pending !== null && !pending.error
  const oversized = byteLength(draft.trim()) > MESSAGE_LIMIT

  const refreshStatus = useCallback(async () => {
    statusRequest.current?.abort()
    const controller = new AbortController()
    statusRequest.current = controller
    try {
      const result = await checkModel(controller.signal)
      if (!controller.signal.aborted) setAvailability(result)
    } catch {
      if (!controller.signal.aborted) setAvailability('backend-unavailable')
    }
  }, [])

  useEffect(() => {
    void refreshStatus()
    const timer = window.setInterval(() => void refreshStatus(), 12_000)
    return () => {
      window.clearInterval(timer)
      statusRequest.current?.abort()
    }
  }, [refreshStatus])

  useEffect(() => {
    const area = transcript.current
    if (area) area.scrollTop = area.scrollHeight
  }, [turns, pending])

  function updateDraft(value: string) {
    session.draft.current = value
    setDraft(value)
  }

  function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!ready || pending || !session.send(draft)) return
    updateDraft('')
  }

  function chooseStarter(value: string) {
    updateDraft(value)
    editor.current?.focus()
  }

  function newConversation() {
    if (session.clear()) chooseStarter('')
  }

  function editFailed() {
    const previous = session.editFailed()
    if (previous !== undefined) chooseStarter(previous)
  }

  return <section className="companion surface" aria-label="Conversation">
    <div className="companion-toolbar">
      <div className="companion-model">
        <p className="companion-status" data-tone={ready ? 'good' : availability === 'checking' ? 'neutral' : 'warn'} role="status">
          <span className="status-dot" aria-hidden="true" />{describeAvailability(availability)}
        </p>
        {!ready && <button type="button" className="companion-button" onClick={() => { setAvailability('checking'); void refreshStatus() }}
          disabled={availability === 'checking'}>Check again</button>}
      </div>
      <button type="button" className="companion-button companion-new" onClick={newConversation}
        disabled={waiting || (!turns.length && !pending && !draft)}>
        <Plus size={16} aria-hidden="true" />New Conversation
      </button>
    </div>

    <div className="companion-transcript" ref={transcript} role="log" aria-label="Conversation messages" tabIndex={0}>
      {turns.length === 0 && !pending
        ? <div className="companion-welcome">
          <span className="companion-emblem"><MessageCircle size={24} aria-hidden="true" /></span>
          <h2>What’s on your mind?</h2>
          <p>Pick a prompt or start anywhere.</p>
          <div className="companion-starters" aria-label="Conversation starters">
            {starters.map(({ icon: Icon, text }) => <button type="button" key={text} onClick={() => chooseStarter(text)}>
              <Icon size={17} aria-hidden="true" />{text}
            </button>)}
          </div>
        </div>
        : <ol className="companion-messages" aria-label="Chat transcript">
          {turns.map(({ question, answer, truncated }, index) => <ReplyPair key={index} question={question} answer={answer} truncated={truncated} />)}
          {pending && <>
            <UserMessage text={pending.question} />
            <li className="companion-message assistant">
              {pending.error ? <>
                <p className="companion-error" role="alert">{pending.error}</p>
                <div className="companion-error-actions">
                  <button type="button" className="companion-button" onClick={() => session.send(pending.question)} disabled={!ready}>Retry</button>
                  <button type="button" className="companion-button" onClick={editFailed}>Edit message</button>
                </div>
              </> : <p className="companion-generating" role="status">
                <span className="companion-pulse" aria-hidden="true" />Qwen is replying…
              </p>}
            </li>
          </>}
        </ol>}
    </div>

    <form className="companion-composer" onSubmit={submit}>
      <label htmlFor="companion-message" className="sr-only">Message</label>
      <div className="companion-entry">
        <textarea id="companion-message" ref={editor} rows={2} value={draft} maxLength={MESSAGE_LIMIT}
          placeholder="Write a message…" onChange={(event) => updateDraft(event.target.value)}
          aria-describedby="companion-hint" aria-invalid={oversized || undefined} onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              submit()
            }
          }} />
        <button type="submit" className="companion-send" disabled={!ready || !!pending || !draft.trim() || oversized}>
          <ArrowUp size={19} aria-hidden="true" />Send
        </button>
      </div>
      <p id="companion-hint" className="companion-note" data-tone={oversized ? 'warn' : 'neutral'}>
        {oversized ? 'This message is too long. Shorten it to send.' : 'Enter to send · Shift+Enter for a new line'}
      </p>
    </form>
  </section>
}

function UserMessage({ text }: { text: string }) {
  return <li className="companion-message user"><span className="companion-speaker">You</span><p>{text}</p></li>
}

function ReplyPair({ question, answer, truncated }: { question: string; answer: string; truncated: boolean }) {
  return <><UserMessage text={question} /><AssistantReply text={answer} truncated={truncated} /></>
}
