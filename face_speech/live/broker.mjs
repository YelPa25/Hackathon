import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { createInterface } from 'node:readline'
import { join } from 'node:path'
import { access } from 'node:fs/promises'

const root = join(process.env.LOCALAPPDATA, 'ASTRAResearch')
const python = join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python311', 'python.exe')
const port = Number(process.env.ASTRA_RESEARCH_PORT ?? 8051)
const origin = process.env.ASTRA_RESEARCH_ORIGIN ?? 'http://127.0.0.1:5180'
const sessions = new Map()
const readyWorkerPaths = [python, join(root, 'isolate.py'), join(root, 'worker.py'), join(root, 'calibration.py')]
const maxAudioBytes = 15 * 96000 * 4
const leaseMs = 90_000
const pausedLeaseMs = 15 * 60_000
const maxProfileBytes = 512 * 1024

function respond(response, status, payload) {
  if (response.destroyed) return
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
  response.end(JSON.stringify(payload))
}

function renew(session) {
  clearTimeout(session.lease)
  session.lease = setTimeout(() => {
    const message = session.pending || session.control
      ? 'The local model timed out while processing a sample.'
      : session.status === 'loading'
        ? 'The local model timed out while starting.'
        : session.paused
          ? 'The paused session expired. Start a new session or use a saved calibration.'
          : 'The browser stopped checking in with the local capture service.'
    endSession(session, message)
  }, session.paused && !session.pending && !session.control ? pausedLeaseMs : leaseMs).unref()
}

function endSession(session, message) {
  if (session.status === 'unavailable') return
  clearTimeout(session.lease)
  session.status = 'unavailable'
  session.message = message
  session.child.kill()
  session.pending?.finish({ status: 410, body: { message } })
  session.control?.({ message })
  // Keep the actual cause available briefly to the browser after a failure.
  session.lease = setTimeout(() => sessions.delete(session.id), 60_000).unref()
}

function removeSession(session) {
  endSession(session, 'Capture stopped.')
  clearTimeout(session.lease)
  sessions.delete(session.id)
}

function launch(id, mode) {
  const child = spawn(python, ['-I', '-B', join(root, 'isolate.py'), join(root, 'worker.py'), mode], {
    cwd: root,
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })
  const session = {
    id, mode, child, pending: null, control: null, lastSample: null,
    lastWindow: null, paused: false, pausedCount: 0, status: 'loading',
  }
  sessions.set(id, session)
  renew(session)

  let diagnostics = ''
  child.stderr.setEncoding('utf8')
  child.stderr.on('data', (chunk) => { diagnostics = (diagnostics + chunk).slice(-4000) })
  child.stdin.on('error', () => {}) // Process exit is handled below.
  child.on('error', (error) => { diagnostics = error.message })
  child.on('close', (code, signal) => {
    if (session.status === 'unavailable') return
    console.error('ASTRA Research worker exited:', mode, code ?? signal, diagnostics)
    const verb = session.status === 'loading' ? 'could not start' : 'stopped during capture'
    endSession(session, 'The local model ' + verb + '. Check the research terminal before restarting.')
  })
  createInterface({ input: child.stdout }).on('line', (line) => {
    if (session.status === 'unavailable') return
    try {
      const reply = JSON.parse(line)
      if (reply.kind === 'ready') {
        session.status = 'ready'
        session.target = reply.target
        session.features = reply.features
        renew(session)
      } else if (reply.kind === 'sample' && session.pending) {
        const result = { status: 200, body: { window: reply.window } }
        session.lastSample = { sequence: session.pending.sequence, result }
        if (reply.window) session.lastWindow = reply.window
        session.pending.finish(result)
      } else if (reply.kind === 'control') {
        session.control?.(reply)
      }
    } catch {
      endSession(session, 'The local model returned an unreadable response. Start a new capture to retry.')
    }
  })
  return session
}

async function readSample(request, expected) {
  const chunks = []
  let length = 0
  try {
    for await (const chunk of request) {
      length += chunk.length
      if (length > expected) return null
      chunks.push(chunk)
    }
  } catch (error) {
    if (!request.complete && request.destroyed) return null
    throw error
  }
  return length === expected ? Buffer.concat(chunks, length) : null
}

async function processSample(request, session, sequence, rate, expected) {
  if (request.headers['content-type'] !== 'application/octet-stream' ||
      Number(request.headers['content-length']) !== expected) {
    request.resume()
    return { status: 400, body: { message: 'Invalid capture sample.' } }
  }
  if (session.lastSample?.sequence === sequence) {
    request.resume()
    return session.lastSample.result
  }
  if (session.pending?.sequence === sequence) {
    request.resume()
    return session.pending.completion
  }
  if (session.pending || sequence !== (session.lastSample?.sequence ?? 0) + 1) {
    request.resume()
    return { status: 409, body: { message: 'Sample arrived out of order. Start a new capture.' } }
  }

  // Keep an accepted sample independent of the HTTP response. A retry after an
  // interrupted response can reuse the result without re-running calibration.
  const { promise: completion, resolve } = Promise.withResolvers()
  const pending = { sequence, completion, finish: resolve }
  session.pending = pending
  renew(session)
  try {
    const body = await readSample(request, expected)
    if (session.status === 'unavailable') return await completion
    if (!body) {
      resolve({ status: 503, body: { message: 'Sample upload was interrupted.' } })
    } else {
      session.child.stdin.write(JSON.stringify({ body: body.toString('base64'), rate }) + '\n')
    }
    return await completion
  } catch (error) {
    console.error('ASTRA Research sample transport:', error.message)
    resolve({ status: 503, body: { message: 'Sample upload was interrupted.' } })
    return await completion
  } finally {
    session.pending = null
    if (session.status === 'ready') renew(session)
  }
}

async function controlSession(session, action, request, response) {
  if (session.status !== 'ready') return respond(response, 409, { message: 'The local model is still loading.' })
  if (action === 'pause') {
    session.paused = true
    session.pausedCount++
    renew(session)
    return respond(response, 200, { paused: true })
  }

  if (session.control || (action === 'save' && !session.paused) ||
      (action === 'load' && (session.pending || session.lastSample))) {
    request.resume()
    return respond(response, 409, { message: 'This action requires a paused or new capture.' })
  }
  const pausedCount = session.pausedCount
  if (session.pending) await session.pending.completion
  if (session.status !== 'ready') return respond(response, 410, { message: session.message })
  if (session.control) return respond(response, 503, { message: 'The local capture service is busy.' })

  let profile
  if (action === 'load') {
    const size = Number(request.headers['content-length'])
    if (request.headers['content-type'] !== 'application/json' ||
        !Number.isInteger(size) || size < 2 || size > maxProfileBytes) {
      request.resume()
      return respond(response, 400, { message: 'Saved calibration has an invalid format.' })
    }
    const body = await readSample(request, size)
    try {
      profile = JSON.parse(body?.toString('utf8') ?? '')
    } catch {
      return respond(response, 400, { message: 'Saved calibration has an invalid format.' })
    }
  }

  if (session.status !== 'ready') return respond(response, 410, { message: session.message })
  if (session.control || session.pending) return respond(response, 503, { message: 'The local capture service is busy.' })
  const { promise, resolve } = Promise.withResolvers()
  session.control = resolve
  renew(session)
  let reply
  try {
    session.child.stdin.write(JSON.stringify({ command: action, profile }) + '\n')
    reply = await promise
  } finally {
    session.control = null
    if (session.status === 'ready') renew(session)
  }
  if (session.status !== 'ready') return respond(response, 410, { message: session.message })
  if (reply.message) return respond(response, 422, { message: reply.message })
  if (action === 'resume' && session.pausedCount === pausedCount) session.paused = false
  renew(session)
  return respond(response, 200, {
    paused: session.paused,
    sequence: session.lastSample?.sequence ?? 0,
    window: session.lastWindow,
    ...(action === 'save' ? { profile: reply.profile } : {}),
  })
}

async function route(request, response) {
  if (request.headers['x-astra-research'] !== 'local-capture' ||
      (request.headers.origin && request.headers.origin !== origin)) {
    return respond(response, 403, { message: 'Capture is limited to the local ASTRA page.' })
  }
  const path = new URL(request.url, 'http://localhost').pathname
  if (path === '/research-api/health' && request.method === 'GET') {
    await Promise.all(readyWorkerPaths.map((file) => access(file)))
    return respond(response, 200, { available: true })
  }
  const match = /^\/research-api\/(facial|speech)\/([0-9a-f-]{36})(?:\/(sample|pause|resume|save|load))?$/.exec(path)
  if (!match) return respond(response, 404, { message: 'Unknown capture request.' })
  const [, mode, id, action] = match
  let session = sessions.get(id)
  if (session && mode !== session.mode) return respond(response, 404, { message: 'Unknown capture session.' })

  if (!action && request.method === 'POST') {
    if (!session) {
      if ([...sessions.values()].some((item) => item.mode === mode && item.status !== 'unavailable')) {
        return respond(response, 409, { message: 'This device already has a session. Stop it or wait and try again.' })
      }
      session = launch(id, mode)
    }
    return respond(response, 202, { status: session.status })
  }
  if (!action && request.method === 'DELETE') {
    if (session) removeSession(session)
    return respond(response, 200, { status: 'stopped' })
  }
  if (!session) return respond(response, 410, { message: 'The local capture session ended.' })
  if (session.status === 'unavailable') {
    request.resume()
    return respond(response, 410, { message: session.message })
  }
  if (!action && request.method === 'GET') {
    if (session.status === 'ready' && !session.pending && !session.paused && !session.control) renew(session)
    return respond(response, 200, { status: session.status, target: session.target, features: session.features })
  }
  if (!action || request.method !== 'POST') return respond(response, 405, { message: 'Method unavailable.' })
  if (action !== 'sample') return controlSession(session, action, request, response)
  if (session.paused || session.control) {
    request.resume()
    return respond(response, 409, { message: 'Resume capture before sending a sample.' })
  }
  if (session.status !== 'ready') return respond(response, 409, { message: 'The local model is still loading.' })
  const rate = Number(request.headers['x-astra-sample-rate'])
  const sequence = Number(request.headers['x-astra-sample-sequence'])
  const expected = mode === 'facial' ? 320 * 240 * 4 : 15 * rate * 4
  if (!Number.isSafeInteger(sequence) || sequence < 1 ||
      (mode === 'speech' && (!Number.isInteger(rate) || rate < 8000 || expected > maxAudioBytes))) {
    request.resume()
    return respond(response, 400, { message: 'Invalid capture sample metadata.' })
  }
  const result = await processSample(request, session, sequence, rate, expected)
  return respond(response, result.status, result.body)
}

const server = createServer((request, response) => {
  route(request, response).catch((error) => {
    console.error('ASTRA Research broker:', error.message)
    if (!response.headersSent) respond(response, 503, { message: 'Local capture service is unavailable.' })
  })
})
server.requestTimeout = 100_000
server.listen(port, '127.0.0.1', () => console.log('ASTRA Research broker on 127.0.0.1:' + port))
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    for (const session of sessions.values()) removeSession(session)
    server.close(() => process.exit(0))
  })
}
