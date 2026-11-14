import { useCallback, useEffect, useRef, useState } from 'react'
import type { FeatureWindow, Modality } from './results'

const header = { 'X-Astra-Research': 'local-capture' }
const audioSeconds = 15
const frameInterval = 500

type Stage = 'idle' | 'loading' | 'permission' | 'active' | 'paused' | 'stopped' | 'error'
export type Snapshot = {
  stage: Stage
  detail: string
  windows: FeatureWindow[]
  features: string[]
  target: number
}
type Capture = {
  path: string
  controller: AbortController
  stream?: MediaStream
  audio?: AudioContext
  keepalive?: number
  ready?: boolean
  device?: string
}

type PausedCapture = {
  path: string
  device?: string
  confirmed: Promise<boolean>
}

type SavedCalibration = { device: string; savedAt: string; profile: unknown }
type StartMode = 'new' | 'resume' | 'saved'

const storageKey = (modality: Modality) => 'astra-research-calibration-v1:' + modality

function readCalibration(modality: Modality): SavedCalibration | null {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(modality)) ?? 'null')
    return saved && typeof saved.device === 'string' && typeof saved.savedAt === 'string' && saved.profile
      ? saved : null
  } catch {
    return null
  }
}

async function captureDevice(track: MediaStreamTrack) {
  const id = track.getSettings().deviceId
  if (!id) return undefined
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(id))
  return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

class CaptureRequestError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, cache: 'no-store', headers: { ...header, ...init.headers } })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload) {
    throw new CaptureRequestError(payload ? response.status : 503, payload?.message ?? 'Local capture service is unavailable.')
  }
  return payload as T
}

function delay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    signal.throwIfAborted()
    const onAbort = () => {
      window.clearTimeout(timer)
      reject(signal.reason)
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

async function requestWithRetry<T>(
  path: string, signal: AbortSignal, timeout: number, init: RequestInit = {}, onRetry?: () => void,
): Promise<T> {
  for (const backoff of [0, 750, 1750]) {
    if (backoff) await delay(backoff, signal)
    try {
      return await request<T>(path, { ...init, signal: AbortSignal.any([signal, AbortSignal.timeout(timeout)]) })
    } catch (error) {
      signal.throwIfAborted()
      if (error instanceof CaptureRequestError && error.status < 500) throw error
      if (backoff === 1750) throw new Error('The local capture service did not respond. Check the research terminal and start again.', { cause: error })
      onRetry?.()
    }
  }
  throw new Error('The local capture service did not respond.')
}

function close(capture: Capture, preview: HTMLVideoElement | null) {
  if (capture.keepalive !== undefined) window.clearInterval(capture.keepalive)
  capture.controller.abort()
  capture.stream?.getTracks().forEach((track) => track.stop())
  if (preview) preview.srcObject = null
  if (capture.audio && capture.audio.state !== 'closed') void capture.audio.close().catch(() => {})
}

function discard(path: string) {
  void request(path, { method: 'DELETE', keepalive: true }).catch(() => {})
}

export function useLiveCapture(modality: Modality) {
  const session = useRef<Capture | null>(null)
  const preview = useRef<HTMLVideoElement>(null)
  const paused = useRef<PausedCapture | null>(null)
  const [saved, setSaved] = useState(() => readCalibration(modality))
  const [storageStatus, setStorageStatus] = useState('')
  const [saving, setSaving] = useState(false)
  const [selectedFeature, setSelectedFeature] = useState('')
  const [snapshot, setSnapshot] = useState<Snapshot>({
    stage: 'idle', detail: modality === 'facial' ? 'Camera is off.' : 'Microphone is off.', windows: [], features: [], target: 0,
  })

  useEffect(() => {
    const end = () => {
      if (session.current) {
        close(session.current, null)
        discard(session.current.path)
        session.current = null
      }
      if (paused.current) discard(paused.current.path)
      paused.current = null
    }
    const onPageHide = () => {
      end()
      setSnapshot((state) => ({ ...state, stage: 'stopped', detail: 'Capture ended when the page closed.' }))
    }
    window.addEventListener('pagehide', onPageHide)
    return () => {
      window.removeEventListener('pagehide', onPageHide)
      end()
    }
  }, [])

  const pause = useCallback(() => {
    const capture = session.current
    if (!capture) return
    close(capture, preview.current)
    session.current = null
    if (!capture.ready) {
      if (paused.current?.path !== capture.path) discard(capture.path)
      setSnapshot((state) => ({
        ...state, stage: paused.current ? 'paused' : 'stopped', detail: 'Capture stopped. Devices released.',
      }))
      return
    }
    paused.current = {
      path: capture.path,
      device: capture.device,
      confirmed: request(capture.path + '/pause', {
        method: 'POST', keepalive: true, signal: AbortSignal.timeout(4500),
      }).then(() => true, () => false),
    }
    setSnapshot((state) => ({ ...state, stage: 'paused', detail: 'Capture paused. Devices released.' }))
  }, [])

  async function saveCalibration() {
    const checkpoint = paused.current
    if (!checkpoint?.device) {
      setStorageStatus('This browser could not identify the device for saving.')
      return
    }
    setSaving(true)
    try {
      await checkpoint.confirmed
      const { profile } = await request<{ profile: unknown }>(checkpoint.path + '/save', {
        method: 'POST', signal: AbortSignal.timeout(10_000),
      })
      const savedCalibration = { profile, device: checkpoint.device, savedAt: new Date().toISOString() }
      localStorage.setItem(storageKey(modality), JSON.stringify(savedCalibration))
      setSaved(savedCalibration)
      setStorageStatus('Calibration saved on this browser.')
    } catch (error) {
      setStorageStatus(error instanceof CaptureRequestError ? error.message : 'Calibration could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  function forgetCalibration() {
    try {
      localStorage.removeItem(storageKey(modality))
      setSaved(null)
      setStorageStatus('Saved calibration removed.')
    } catch {
      setStorageStatus('Saved calibration could not be removed.')
    }
  }

  async function start(mode: StartMode = 'new') {
    if (session.current || saving) return
    const checkpoint = mode === 'resume' ? paused.current : null
    if (mode === 'resume' && !checkpoint) return
    const stored = mode === 'saved' ? readCalibration(modality) : null
    if (mode === 'saved' && !stored) return
    const path = checkpoint?.path ?? '/research-api/' + modality + '/' + crypto.randomUUID()
    const capture: Capture = { path, controller: new AbortController() }
    session.current = capture
    const { signal } = capture.controller
    setStorageStatus('')
    const previousCapture = !checkpoint ? paused.current : null
    if (!checkpoint) {
      paused.current = null
    }
    setSnapshot((state) => ({
      ...(checkpoint || stored ? state : { windows: [], features: [], target: 0 }),
      stage: 'loading', detail: checkpoint ? 'Preparing to resume capture…' : 'Loading the local model…',
    }))

    const update = (detail: string, stage?: Stage) => setSnapshot((state) => ({
      ...state, detail, stage: stage ?? state.stage,
    }))

    let sequence = 1
    let lastReplyAt = performance.now()
    const send = async (body: ArrayBuffer, rate?: number) => {
      let retried = false
      const { window: result } = await requestWithRetry<{ window: FeatureWindow | null }>(path + '/sample', signal, 25_000, {
        method: 'POST',
        body,
        headers: {
          'Content-Type': 'application/octet-stream',
          'X-Astra-Sample-Sequence': String(sequence),
          ...(rate ? { 'X-Astra-Sample-Rate': String(rate) } : {}),
        },
      }, () => {
        retried = true
        update(modality === 'facial' ? 'Camera active · Reconnecting…' : 'Microphone active · Reconnecting…')
      })
      sequence++
      lastReplyAt = performance.now()
      if (signal.aborted) return
      if (retried && modality === 'facial') update('Camera active')
      if (result) {
        setSnapshot((state) => ({ ...state, windows: [...state.windows.slice(-119), result] }))
      }
    }

    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Open ASTRA in a local browser that supports device access.')
      // Resume within the click gesture. This context receives no microphone until permission succeeds.
      if (modality === 'speech') {
        capture.audio = new AudioContext()
        await Promise.race([
          capture.audio.resume(),
          delay(5000, signal).then(() => { throw new Error('The browser could not start audio capture.') }),
        ])
      }
      if (previousCapture) {
        await requestWithRetry(previousCapture.path, signal, 5000, { method: 'DELETE' })
      }
      if (checkpoint) {
        await checkpoint.confirmed
      } else {
        await requestWithRetry(path, signal, 5000, { method: 'POST' })
      }
      let ready: { status: string; target?: number; features?: string[] }
      const deadline = Date.now() + 85_000
      do {
        if (Date.now() >= deadline) throw new Error('The local model took too long to start.')
        ready = await requestWithRetry(path, signal, 5000)
        if (ready.status === 'unavailable') throw new Error('The local model could not start. Check the research terminal.')
        if (ready.status !== 'ready') await delay(500, signal)
      } while (ready.status !== 'ready')
      setSnapshot((state) => ({ ...state, target: ready.target ?? 0, features: ready.features ?? [] }))
      signal.throwIfAborted()
      let checking = false
      capture.keepalive = window.setInterval(() => {
        if (checking || performance.now() - lastReplyAt < 7000) return
        checking = true
        const checkStarted = performance.now()
        void requestWithRetry(path, signal, 3000).then(() => {
          lastReplyAt = performance.now()
        }).catch((error: unknown) => {
          if (signal.aborted || session.current !== capture) return
          // A recent sample response proves the same session is still running.
          if (!(error instanceof CaptureRequestError) && lastReplyAt > checkStarted) return
          close(capture, preview.current)
          discard(capture.path)
          if (paused.current?.path === path) paused.current = null
          session.current = null
          update(error instanceof Error ? error.message : 'The local capture service stopped.', 'error')
        }).finally(() => { checking = false })
      }, 8000)
      update('Allow access in your browser to begin capture.', 'permission')
      const stream = await navigator.mediaDevices.getUserMedia(modality === 'facial'
        ? { video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false }
        : { video: false, audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } })
      if (signal.aborted) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      capture.stream = stream
      capture.device = await captureDevice(stream.getTracks()[0])
      signal.throwIfAborted()
      const expectedDevice = checkpoint?.device ?? stored?.device
      if (expectedDevice && capture.device !== expectedDevice) {
        throw new Error('This device differs from the calibrated device. Reconnect it or start a new calibration.')
      }
      if (checkpoint) {
        const state = await requestWithRetry<{ sequence: number; window: FeatureWindow | null }>(path + '/resume', signal, 8000, { method: 'POST' })
        signal.throwIfAborted()
        sequence = state.sequence + 1
        const last = state.window
        if (last) setSnapshot((previous) => previous.windows.at(-1)?.t === last.t ? previous : ({
          ...previous, windows: [...previous.windows.slice(-119), last],
        }))
      } else if (stored) {
        await requestWithRetry(path + '/load', signal, 5000, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(stored.profile),
        })
        setSnapshot((state) => ({ ...state, windows: [] }))
        setStorageStatus('Saved calibration loaded. The next usable sample can be scored.')
      }
      paused.current = null
      capture.ready = true
      for (const track of stream.getTracks()) {
        track.addEventListener('ended', () => {
          if (session.current !== capture) return
          pause()
          update('The device disconnected. Reconnect it and resume capture.')
        }, { once: true })
      }
      update(modality === 'facial' ? 'Camera active' : 'Microphone active · Speak at a comfortable pace.', 'active')
      if (modality === 'facial') {
        const video = preview.current
        if (!video) throw new Error('Camera preview is unavailable.')
        video.srcObject = stream
        await video.play()
        const canvas = document.createElement('canvas')
        canvas.width = 320
        canvas.height = 240
        const drawing = canvas.getContext('2d', { willReadFrequently: true })
        if (!drawing) throw new Error('Camera frame processing is unavailable.')
        while (!signal.aborted) {
          const started = performance.now()
          // The browser can briefly stop supplying frames while switching tabs or cameras.
          if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth || !video.videoHeight) {
            await delay(frameInterval, signal)
            continue
          }
          const scale = Math.min(320 / video.videoWidth, 240 / video.videoHeight)
          const width = video.videoWidth * scale
          const height = video.videoHeight * scale
          drawing.fillStyle = 'black'
          drawing.fillRect(0, 0, 320, 240)
          drawing.drawImage(video, (320 - width) / 2, (240 - height) / 2, width, height)
          const { data } = drawing.getImageData(0, 0, 320, 240)
          await send(data.buffer)
          await delay(Math.max(0, frameInterval - (performance.now() - started)), signal)
        }
      } else {
        const audio = capture.audio!
        await audio.audioWorklet.addModule(new URL('./pcm-collector.js', import.meta.url))
        signal.throwIfAborted()
        const collector = new AudioWorkletNode(audio, 'astra-pcm-collector')
        audio.createMediaStreamSource(stream).connect(collector).connect(audio.destination)
        const length = audio.sampleRate * audioSeconds
        let buffer = new Float32Array(length)
        let offset = 0
        let busy = false
        let queued: ArrayBuffer | undefined
        await new Promise<void>((resolve, reject) => {
          if (signal.aborted) return resolve()
          signal.addEventListener('abort', () => {
            queued = undefined
            collector.port.onmessage = null
            collector.port.close()
            collector.disconnect()
            resolve()
          }, { once: true })

          const process = (windowBuffer: ArrayBuffer) => {
            busy = true
            update('Microphone active · Collecting while the previous sample is processed.')
            void send(windowBuffer, audio.sampleRate).then(() => {
              if (signal.aborted) return
              const next = queued
              queued = undefined
              if (next) process(next)
              else {
                busy = false
                update('Microphone active · Collecting the next sample.')
              }
            }, reject)
          }

          collector.port.onmessage = (event: MessageEvent<Float32Array>) => {
            if (signal.aborted) return
            const samples = event.data
            let cursor = 0
            while (cursor < samples.length) {
              const count = Math.min(length - offset, samples.length - cursor)
              buffer.set(samples.subarray(cursor, cursor + count), offset)
              cursor += count
              offset += count
              if (offset === length) {
                const completed = buffer.buffer
                buffer = new Float32Array(length)
                offset = 0
                if (!busy) process(completed)
                else if (!queued) queued = completed
              }
            }
          }
        })
      }
    } catch (error) {
      if (signal.aborted) return
      if (capture.ready) {
        pause()
      } else {
        close(capture, preview.current)
        if (!checkpoint || (error instanceof CaptureRequestError && error.status === 410)) {
          discard(capture.path)
          paused.current = null
        }
        session.current = null
      }
      const name = error instanceof Error ? error.name : ''
      update(name === 'NotAllowedError' ? 'Device access was denied. Allow it in the browser or Windows settings.'
        : name === 'NotFoundError' ? 'No matching device was found. Connect one and try again.'
        : name === 'NotReadableError' ? 'The device could not be opened. Close other apps using it and try again.'
        : error instanceof Error ? error.message : 'Capture could not start.', paused.current ? 'paused' : 'error')
    }
  }

  return {
    snapshot, preview, start, pause, selectedFeature, setSelectedFeature,
    saved, saveCalibration, forgetCalibration, storageStatus, saving,
  }
}
