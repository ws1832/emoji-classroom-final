import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { CameraRun, nextSlotDelay, safeUploadUrl } from '../src/utils/browser-camera.js'

test('late camera permission resolution releases all tracks', () => {
  const run = new CameraRun()
  const generation = run.begin()
  run.stop()
  let stopped = 0
  const stream = { getTracks: () => [{ stop: () => stopped++ }, { stop: () => stopped++ }] }
  assert.equal(run.attach(stream, generation), false)
  assert.equal(stopped, 2)
  assert.equal(run.stream, null)
})
test('stop aborts in-flight request, releases camera and drops in-memory token', () => {
  const run = new CameraRun()
  const generation = run.begin()
  let stopped = 0
  run.attach({ getTracks: () => [{ stop: () => stopped++ }] }, generation)
  const controller = new AbortController()
  run.controller = controller
  run.capture = { capture_id: 'id', capture_token: 'memory-only' }
  assert.equal(run.stop().capture_id, 'id')
  assert.equal(controller.signal.aborted, true)
  assert.equal(stopped, 1)
  assert.equal(run.capture, null)
  assert.equal(run.current(generation), false)
})
test('phase scheduler moves to next slot, never schedules catch-up samples', () => {
  for (let now = 0; now < 40000; now += 79) {
    const delay = nextSlotDelay(now, 10, 2300)
    assert.ok(delay > 100 && delay <= 10100)
    assert.equal(Math.round((now + delay - 2400) % 10000), 0)
  }
})
test('upload URL never contains tokens and remote endpoints require HTTPS', () => {
  assert.equal(safeUploadUrl('/ai-stream/frames', 'https://school.test'), 'https://school.test/ai-stream/frames')
  assert.equal(safeUploadUrl('http://localhost:9998/frames', 'http://localhost:3100'), 'http://localhost:9998/frames')
  for (const url of ['http://school.test/frames', 'https://user:pass@school.test/frames',
    'https://school.test/frames?token=x', 'https://school.test/frames#x', 'data:image/jpeg,x']) {
    assert.throws(() => safeUploadUrl(url, 'https://school.test'))
  }
})
test('production UI wires release guards and no persistent/raw upload storage', async () => {
  const source = await readFile(new URL('../src/components/ai/StudentCameraCapture.vue', import.meta.url), 'utf8')
  for (const required of ["getUserMedia", "audio: false", "visibilitychange", "pagehide",
    "onBeforeUnmount", "isCurrentSession", "credentials: 'omit'", "redirect: 'error'", "AbortController"]) {
    assert.ok(source.includes(required), required)
  }
  assert.ok(!/localStorage|sessionStorage|MediaRecorder|indexedDB/.test(source))
  assert.ok(source.includes("if (!current(g))"))
})
