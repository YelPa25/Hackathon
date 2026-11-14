// Exercise the real isolated workers with review-approved local test fixtures.
// The caller supplies a 320x240 RGBA frame and a 15-second mono 16 kHz float32 sample.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'

const [framePath, audioPath, profilePath] = process.argv.slice(2)
if (!framePath || !audioPath) throw new Error('Provide raw RGBA and float32 input fixtures.')
const port = 18051
const broker = spawn(process.execPath, ['face_speech/live/broker.mjs'], {
  env: { ...process.env, ASTRA_RESEARCH_PORT: String(port) }, stdio: 'inherit', windowsHide: true,
})
const base = 'http://127.0.0.1:' + port + '/research-api'
const auth = { 'X-Astra-Research': 'local-capture' }
const active = new Set()

async function send(url, init = {}, expected) {
  const res = await fetch(url, { ...init, headers: { ...auth, ...init.headers }, signal: AbortSignal.timeout(45_000) })
  const data = await res.json()
  assert.equal(expected === undefined ? res.ok : res.status === expected, true, JSON.stringify(data))
  return data
}

async function start(modality) {
  const path = base + '/' + modality + '/' + randomUUID()
  active.add(path)
  await send(path, { method: 'POST' })
  for (let i = 0; i < 60; i++) {
    const ready = await send(path)
    if (ready.status === 'ready') return path
    await delay(500)
  }
  throw new Error('Worker did not become ready.')
}

function control(path, command, profile, expected) {
  return send(path + '/' + command, {
    method: 'POST',
    ...(profile ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(profile) } : {}),
  }, expected)
}

async function stop(path) {
  await send(path, { method: 'DELETE' })
  active.delete(path)
}

function sample(path, body, sequence, rate) {
  return send(path + '/sample', {
    method: 'POST',
    body,
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Astra-Sample-Sequence': String(sequence),
      ...(rate ? { 'X-Astra-Sample-Rate': String(rate) } : {}),
    },
  })
}

async function verify(modality, body, target, pieces, rate) {
  let path = await start(modality)
  let sequence = 1
  const started = performance.now()
  for (let n = 1; n <= target; n++) {
    let result
    for (let piece = 0; piece < pieces; piece++) result = await sample(path, body, sequence++, rate)
    assert.equal(result.window.baseline.n, n)
    assert.equal(result.window.score, null)

    if (n === 1) {
      await control(path, 'pause')
      await control(path, 'save', undefined, 422)
      const resumed = await control(path, 'resume')
      assert.equal(resumed.sequence, sequence - 1)
      assert.equal(resumed.window.baseline.n, n)
    }
  }
  console.log(modality + ' completed ' + target + ' real model windows (accelerated fixture feed) in ' +
    ((performance.now() - started) / 1000).toFixed(1) + ' seconds')
  await control(path, 'pause')
  const { profile } = await control(path, 'save')
  assert.deepEqual(Object.keys(profile).sort(), ['drift', 'mads', 'medians', 'version'])
  assert.ok(profile.drift.enabled, 'Verify scoring with the fitted drift model enabled')
  assert.ok(!('buffer' in profile.drift))
  await stop(path)

  path = await start(modality)
  await control(path, 'load', { ...profile, version: 'wrong version' }, 422)
  await control(path, 'load', { ...profile, mads: {} }, 422)
  await control(path, 'load', profile)
  let scored
  for (let piece = 1; piece <= pieces; piece++) scored = await sample(path, body, piece, rate)
  assert.equal(scored.window.baseline.n, target)
  assert.equal(scored.window.baseline.ready, true)
  assert.equal(scored.window.state, 'normal')
  assert.equal(typeof scored.window.score, 'number')
  await stop(path)
  console.log(modality + ' reused fitted statistics and scored its first valid window')
  return profile
}

try {
  await delay(1200)
  assert.equal((await send(base + '/health')).available, true)
  const [frame, voice] = await Promise.all([readFile(framePath), readFile(audioPath)])
  const [facial, speech] = await Promise.all([
    verify('facial', frame, 40, 20),
    verify('speech', voice, 20, 1, 16000),
  ])
  if (profilePath) await writeFile(profilePath, JSON.stringify({ facial, speech }))
} finally {
  await Promise.allSettled([...active].map(stop))
  broker.kill()
}
