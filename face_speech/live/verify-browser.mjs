// Windows browser integration check. Synthetic device sources; no personal recording.
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

const chrome = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const profile = await mkdtemp(join(tmpdir(), 'astra-live-browser-'))
const [cameraSample, speechSample, trainedProfiles] = process.argv.slice(2)
const browser = spawn(chrome, [
  '--headless', '--no-first-run', '--disable-extensions', '--remote-debugging-port=0',
  '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
  ...(cameraSample ? ['--use-file-for-fake-video-capture=' + cameraSample] : []),
  ...(speechSample ? ['--use-file-for-fake-audio-capture=' + speechSample] : []),
  '--user-data-dir=' + profile, 'about:blank',
], { windowsHide: true, stdio: 'ignore' })
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function until(fn, timeout = 50_000) {
  const deadline = Date.now() + timeout
  do {
    const value = await fn()
    if (value) return value
    await sleep(250)
  } while (Date.now() < deadline)
  throw new Error('Browser state timed out')
}

const testSessions = new Set()
let socket
try {
  const { webSocketDebuggerUrl } = await until(async () => {
    const port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8').catch(() => '')).split(/\r?\n/)[0]
    if (!port) return null
    return (await (await fetch('http://127.0.0.1:' + port + '/json/list')).json())[0]
  }, 10_000)
  socket = new WebSocket(webSocketDebuggerUrl)
  await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }))
  let sequence = 0
  const pending = new Map()
  const browserErrors = []
  socket.addEventListener('message', ({ data }) => {
    const reply = JSON.parse(data)
    if (reply.method === 'Network.requestWillBeSent') {
      const { url, method } = reply.params.request
      if (method === 'POST' && /^http:\/\/127\.0\.0\.1:5180\/research-api\/(?:facial|speech)\/[0-9a-f-]{36}$/.test(url)) {
        testSessions.add(url)
      }
    }
    if (reply.method === 'Runtime.exceptionThrown') browserErrors.push(reply.params.exceptionDetails.text)
    if (pending.has(reply.id)) {
      pending.get(reply.id)(reply)
      pending.delete(reply.id)
    }
  })

  async function cdp(method, params = {}) {
    const id = ++sequence
    const result = await new Promise((resolve) => {
      pending.set(id, resolve)
      socket.send(JSON.stringify({ id, method, params }))
    })
    if (result.error) throw new Error(result.error.message)
    return result.result
  }

  async function page(expression) {
    const reply = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (reply.exceptionDetails) throw new Error(reply.exceptionDetails.exception?.description ?? reply.exceptionDetails.text)
    return reply.result.value
  }

  async function click(label, panel = '') {
    const point = await page(JSON.stringify([label, panel]) + '.map(String)' + `
      .reduce((_, value, index, [label, panel]) => {
        if (index === 0) return null
        const root = panel ? document.querySelector(panel) : document
        const button = [...root.querySelectorAll('button')].find((el) => el.textContent.trim() === label)
        if (!button || button.disabled) return null
        button.scrollIntoView({ block: 'center', behavior: 'instant' })
        const rect = button.getBoundingClientRect()
        return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
      }, null)`)
    if (!point) return false
    for (const type of ['mousePressed', 'mouseReleased']) {
      await cdp('Input.dispatchMouseEvent', { ...point, type, button: 'left', clickCount: 1 })
    }
    return true
  }

  async function readout(panel) {
    return await page(`document.querySelector(${JSON.stringify(panel)})?.innerText`)
  }

  await cdp('Runtime.enable')
  await cdp('Network.enable')
  await cdp('Page.navigate', { url: 'http://127.0.0.1:5180/research-prototypes' })
  await until(() => page('!!document.querySelector(".research-live button:not(:disabled)")'))
  for (const width of [1440, 768, 390]) {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false })
    assert.equal(await page('document.documentElement.scrollWidth <= innerWidth'), true)
  }
  await cdp('Emulation.clearDeviceMetricsOverride')
  assert.equal(await page('document.querySelector("video").srcObject === null'), true)

  assert.equal(await page('document.querySelector(".research-live button:not(:disabled)").click(), true'), true)
  await until(async () => {
    const panel = await readout('.research-panel:first-child')
    if (/already has a session|Check the research terminal|could not start/i.test(panel)) throw new Error(panel)
    return page('!!document.querySelector("video")?.srcObject')
  })
  await page('window.captureTracks = document.querySelector("video").srcObject.getTracks(); window.testCameraDevice = window.captureTracks[0].getSettings().deviceId')
  await until(async () => (await readout('.research-panel:first-child')).includes('Calibration ·'))
  const face = await readout('.research-panel:first-child')
  if (cameraSample) {
    assert.match(face, /Calibration · 1\/40/)
    await page(`(() => {
      const original = window.fetch.bind(window)
      window.fetch = async (resource, init) => {
        const path = String(resource)
        const sequence = new Headers(init?.headers).get('X-Astra-Sample-Sequence')
        if (!path.includes('/facial/') || !path.endsWith('/sample')) return original(resource, init)
        if (sequence === '25' && !window.unreachedRequest) {
          window.unreachedRequest = true
          throw new TypeError('Simulated dropped request')
        }
        const response = await original(resource, init)
        if (sequence === '40' && !window.lostResponse) {
          if (!response.ok) throw new Error('Expected a real sample result before simulating loss')
          window.lostResponse = true
          throw new TypeError('Simulated lost response')
        }
        if (sequence === '40') window.retriedWindow = (await response.clone().json()).window?.baseline.n
        return response
      }
    })()`)
    await until(() => page('window.lostResponse && document.querySelector("#facial-live-calibration").value >= 3'), 65_000)
    assert.equal(await page('window.unreachedRequest && window.lostResponse && window.captureTracks.every((track) => track.readyState === "live")'), true)
    assert.equal(await page('window.retriedWindow === 2'), true)
    console.log('Camera retained calibration through two interrupted requests and at least three valid windows')

    for (const width of [1413, 768, 390]) {
      await cdp('Emulation.setDeviceMetricsOverride', { width, height: 871, deviceScaleFactor: 1, mobile: false })
      assert.equal(await page('document.documentElement.scrollWidth <= innerWidth'), true)
      await until(() => page('document.querySelector(".research-live .research-series svg.recharts-surface").getBoundingClientRect().width > 0'))
      assert.equal(await page(`(() => {
        const series = document.querySelector('.research-live .research-series')
        const select = series.querySelector('select').getBoundingClientRect()
        const chart = series.querySelector('.research-chart').getBoundingClientRect()
        return chart.top - select.bottom >= 10 && chart.right <= innerWidth
      })()`), true)
    }
    await cdp('Emulation.clearDeviceMetricsOverride')
    console.log('Selector and chart have separate bounds at desktop, tablet and phone widths')
  }
  assert.equal(await click('Pause capture', '.research-panel:first-child'), true)
  assert.equal(await page('window.captureTracks.every((track) => track.readyState === "ended")'), true)
  console.log('Camera: model/session, preview, feature window, and track release verified')
  console.log(face.split('\n').filter((line) => /Calibration|quality|^\d+%$/.test(line)).join(' | '))

  // Chrome's fake mic can supply a tone. For the voiced case use the local
  // speech fixture as a browser MediaStream at the same input boundary.
  const encodedSpeech = speechSample ? (await readFile(speechSample)).toString('base64') : null
  await page(`(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    navigator.mediaDevices.getUserMedia = async (options) => {
      const encoded = ${JSON.stringify(encodedSpeech)}
      let stream
      if (encoded && options.audio) {
        const context = new AudioContext()
        const binary = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0))
        const audio = await context.decodeAudioData(binary.buffer)
        const source = context.createBufferSource()
        source.buffer = audio
        source.loop = true
        const destination = context.createMediaStreamDestination()
        source.connect(destination)
        source.start()
        await context.resume()
        stream = destination.stream
      } else stream = await original(options)
      window.micTracks = stream.getAudioTracks()
      return stream
    }
  })()`)
  assert.equal(await click('Start microphone'), true)
  await until(async () => (await readout('.research-panel:last-child')).includes('Microphone active'))
  await until(async () => {
    const panel = await readout('.research-panel:last-child')
    if (panel.includes("Capture stopped") || panel.includes("Local capture service is unavailable")) throw new Error(panel)
    return speechSample ? /Calibration · [1-9][0-9]*\/20/.test(panel) : panel.includes("Calibration ·")
  }, 75_000)
  const speech = await readout('.research-panel:last-child')
  if (speechSample) assert.match(speech, /Calibration · [1-9][0-9]*\/20/)
  if (speechSample) {
    const speechWindowTime = () => page('document.querySelector("#speech-live time")?.dateTime')
    const firstTime = await speechWindowTime()
    const secondTime = await until(async () => {
      const time = await speechWindowTime()
      return time !== firstTime ? time : null
    }, 35_000)
    const interval = (Date.parse(secondTime) - Date.parse(firstTime)) / 1000
    assert.ok(interval < 18.5, 'Voice processing should not add to the sample interval: ' + interval)
    console.log('Consecutive voice window results were ' + interval.toFixed(2) + ' seconds apart')
  }
  assert.equal(await click('Pause capture', '.research-panel:last-child'), true)
  assert.equal(await page('window.micTracks.every((track) => track.readyState === "ended")'), true)
  console.log('Microphone: model/session, PCM worklet, feature window, and track release verified')
  console.log(speech.split('\n').filter((line) => /Calibration|quality|^\d+%$/.test(line)).join(' | '))

  assert.equal(await page('document.querySelector("#speech-sample summary").click(), true'), true)
  assert.equal(await click('Play sample', '#speech-sample'), true)
  await until(() => page('document.querySelector("#speech-calibration")?.value === 20'))
  await sleep(1200)
  assert.equal(await click('Stop', '#speech-sample'), true)
  await page('(() => { const select = document.querySelector("#speech-sample .research-series select"); select.value = "pause_ratio"; select.dispatchEvent(new Event("change", { bubbles: true })); })()')
  const sampleTime = await page('document.querySelector("#speech-sample time")?.dateTime')
  const sampleWindow = await page('document.querySelector("#speech-sample .research-series + p")?.textContent')
  assert.equal(await click('Show result on dashboards', '#speech-sample'), true)

  const beforeNavigation = await page('document.querySelector("#facial-live-calibration")?.value')
  assert.equal(await click('Resume capture', '#facial-live'), true)
  await until(async () => {
    const panel = await readout('.research-panel:first-child')
    if (/already has a session|Check the research terminal|could not start/i.test(panel)) throw new Error(panel)
    return page('!!document.querySelector("video")?.srcObject')
  })
  await page('window.captureTracks = document.querySelector("video").srcObject.getTracks(); window.testCameraDevice = window.captureTracks[0].getSettings().deviceId')
  assert.equal(await page('document.querySelector("a[href=\'/crew-health\']").click(), true'), true)
  await until(() => page('window.captureTracks.every((track) => track.readyState === "ended")'))
  await until(() => page('document.querySelector("main h1")?.textContent === "Crew Health"'))
  await until(() => page('!!document.querySelector("a.return-link[href*=research-prototypes]")'))
  assert.equal(await page('document.querySelector("a.return-link[href*=research-prototypes]").click(), true'), true)
  await until(() => page('document.querySelector("#speech-sample")?.open'))
  assert.equal(await page('location.hash'), '#speech-sample')
  assert.equal(await page('document.querySelector("#speech-sample time").dateTime'), sampleTime)
  assert.equal(await page('document.querySelector("#speech-sample .research-series + p").textContent'), sampleWindow)
  assert.equal(await page('document.querySelector("#speech-sample .research-series select").value'), 'pause_ratio')
  assert.equal(await page('document.querySelector("video").srcObject === null'), true)
  assert.ok(await page('document.querySelector("#facial-live-calibration").value') >= beforeNavigation)
  console.log('Dashboard opened the exact voice demo result while preserving paused live camera progress')
  // Simulate a lost research service at the browser boundary.
  await cdp('Network.setBlockedURLs', { urls: ['*/research-api/*'] })
  await cdp('Page.navigate', { url: 'http://127.0.0.1:5180/research-prototypes' })
  await until(() => page('document.body.innerText.includes("Live capture unavailable")'))
  assert.equal(await page('[...document.querySelectorAll(".research-live button")].every((button) => button.disabled)'), true)
  assert.equal(await page('document.body.innerText.includes("Backend connected")'), true)
  await cdp('Network.setBlockedURLs', { urls: [] })
  await until(() => page('!!document.querySelector(".research-live button:not(:disabled)")'))
  assert.equal(await page('document.querySelector(".research-live button:not(:disabled)").click(), true'), true)
  await until(async () => {
    const panel = await readout('.research-panel:first-child')
    if (/already has a session|Check the research terminal|could not start/i.test(panel)) throw new Error(panel)
    return page('!!document.querySelector("video")?.srcObject')
  })
  await page('window.captureTracks = document.querySelector("video").srcObject.getTracks(); window.testCameraDevice = window.captureTracks[0].getSettings().deviceId')
  await cdp('Network.setBlockedURLs', { urls: ['*/research-api/*'] })
  await until(() => page('window.captureTracks.every((track) => track.readyState === "ended")'))
  assert.equal(await page('document.body.innerText.includes("Backend connected")'), true)
  await cdp('Network.setBlockedURLs', { urls: [] })
  await until(() => page('!!document.querySelector(".research-live button:not(:disabled)")'))
  console.log('Losing the research connection during capture released the camera track')
  if (trainedProfiles && cameraSample) {
    const { facial } = JSON.parse(await readFile(trainedProfiles, 'utf8'))
    const device = await page('window.testCameraDevice')
    assert.ok(device)
    const hash = Buffer.from(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(device))).toString('hex')
    const key = 'astra-research-calibration-v1:facial'
    const persisted = { profile: facial, device: hash, savedAt: new Date().toISOString() }
    await page('localStorage.setItem(' + JSON.stringify(key) + ', ' + JSON.stringify(JSON.stringify(persisted)) + ')')
    await Promise.all([...testSessions].map((url) => fetch(url, {
      method: 'DELETE', headers: { 'X-Astra-Research': 'local-capture' },
    })))
    await cdp('Page.reload')
    await until(() => page('document.querySelector("#facial-live")?.innerText.includes("Use saved calibration")'))
    await until(() => click('Use saved calibration', '#facial-live'))
    await until(() => page('document.querySelector("#facial-live-calibration")?.value === 40'), 50_000)
    assert.match(await readout('#facial-live'), /Saved calibration loaded/)
    assert.equal(await click('Pause capture', '#facial-live'), true)
    assert.equal(await click('Replace saved calibration', '#facial-live'), true)
    await until(() => page('document.querySelector("#facial-live").innerText.includes("Calibration saved on this browser")'))
    assert.equal(await click('Remove saved calibration', '#facial-live'), true)
    assert.equal(await page('localStorage.getItem(' + JSON.stringify(key) + ')'), null)
    console.log('Saved calibration loaded after reload, scored, saved through the UI, and removed')
    const liveTime = await page('document.querySelector("#facial-live time").dateTime')
    assert.equal(await click('Show result on dashboards', '#facial-live'), true)
    assert.equal(await page('document.querySelector("#primary-nav a").click(), true'), true)
    await until(() => page('document.querySelector("main h1")?.textContent === "Mission Overview"'))
    await until(() => page('!!document.querySelector("a.return-link[href*=research-prototypes]")'))
    assert.equal(await page('document.querySelector("a.return-link[href*=research-prototypes]").click(), true'), true)
    await until(() => page('document.querySelector("#facial-live time")?.dateTime'))
    assert.equal(await page('location.hash'), '#facial-live')
    assert.equal(await page('document.querySelector("#facial-live time").dateTime'), liveTime)
    assert.equal(await page('document.querySelector("#facial-live").innerText.includes("Result shown on the dashboard")'), true)
    assert.equal(await page('document.querySelector("video").srcObject === null'), true)
    console.log('Dashboard opened the exact live camera result with the camera still off')
  }
  assert.deepEqual(browserErrors, [])
  console.log('Research connection loss and automatic recovery verified, Core stayed connected')
  console.log('Navigation released the camera; responsive layout and runtime checks passed')
} finally {
  await Promise.allSettled([...testSessions].map((url) => fetch(url, {
    method: 'DELETE',
    headers: { 'X-Astra-Research': 'local-capture' },
    signal: AbortSignal.timeout(2500),
  })))
  socket?.close()
  browser.kill()
  await new Promise((resolve) => browser.exitCode !== null ? resolve() : browser.once('exit', resolve))
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(() => {})
}
