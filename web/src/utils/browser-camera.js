// 可独立测试的资源生命周期；短期上传授权只存在内存中。
export function nextSlotDelay(now, interval, phase) {
  const width = interval * 1000
  return width - (((now - phase) % width + width) % width) + 100
}

export function releaseStream(stream) {
  stream?.getTracks().forEach((track) => track.stop())
}

export function safeUploadUrl(value, origin) {
  const url = new URL(value, origin)
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    (url.protocol !== 'https:' && !local) ||
    url.username || url.password || url.search || url.hash
  ) throw new Error('AI上传地址配置无效')
  return url.href
}

export class CameraRun {
  constructor() {
    this.generation = 0
    this.stream = null
    this.controller = null
    this.capture = null
  }
  begin() { this.stop(); return this.generation }
  current(generation) { return generation === this.generation }
  attach(stream, generation) {
    if (!this.current(generation)) { releaseStream(stream); return false }
    this.stream = stream
    return true
  }
  stop() {
    this.generation++
    this.controller?.abort()
    this.controller = null
    releaseStream(this.stream)
    this.stream = null
    const capture = this.capture
    this.capture = null
    return capture
  }
}
