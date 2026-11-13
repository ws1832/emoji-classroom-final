<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NSpace, NTag } from 'naive-ui'
import api from '@/api'
import { captureSession, isCurrentSession } from '@/utils/auth/session'
import { CameraRun, nextSlotDelay, safeUploadUrl } from '@/utils/browser-camera'

const props = defineProps({ sessionId: { type: Number, required: true } })
const video = ref(null)
const policy = ref(null)
const starting = ref(false)
const running = ref(false)
const status = ref('尚未开启')
const error = ref('')
const sampled = ref(0)
const accepted = ref(0)
const run = new CameraRun()
let sampleTimer, renewTimer, policyTimer, guardTimer
let clockOffset = 0
let owner = null
let disposed = false
let pollSequence = 0
let polling = false
let activeEnd = 0
const messages = {
  accepted: '本次匿名结果已入库', queued: '匿名结果等待短期重试',
  filtered: '本次置信度不足，未记录', no_face: '未检测到人脸，未记录',
  multi_face: '检测到多人，请只让自己入镜；本次未记录',
  invalid_image: '本次画面无效，未记录', model_failed: '模型推理失败，未记录',
  waiting: '上一请求仍未完成，本次不重复推理', ready: '推理完成，尚未确认入库',
}

function current(g) {
  return !disposed && run.current(g) && owner && isCurrentSession(owner)
}
function stop(message = '已停止，摄像头已释放') {
  const snapshot = owner
  clearTimeout(sampleTimer); clearTimeout(renewTimer); clearTimeout(guardTimer)
  const capture = run.stop()
  running.value = starting.value = false
  if (video.value) video.value.srcObject = null
  status.value = message
  owner = null
  // 换账号后绝不拿新账号凭证发旧会话请求；后端TTL仍是最终兜底。
  if (capture && snapshot && isCurrentSession(snapshot)) {
    api.stopBrowserCapture(capture.capture_id).catch(() => {})
  }
}
async function refreshPolicy() {
  if (polling || disposed) return
  const sequence = ++pollSequence
  const session = captureSession()
  const id = props.sessionId
  polling = true
  try {
    const result = await api.getBrowserPolicy(id)
    if (disposed || sequence !== pollSequence || props.sessionId !== id || !isCurrentSession(session)) return
    policy.value = result.data
    if ((running.value || starting.value) && (!result.data.enabled || !result.data.service_ready)) stop('课堂采集或AI服务已停止')
    if (running.value && result.data.revision !== run.capture?.revision) stop('管理员调整了配置，请重新开启')
  } catch (err) {
    if (!disposed && sequence === pollSequence && isCurrentSession(session)) {
      policy.value = null
      if (running.value) stop('无法确认课堂授权，摄像头已停止')
      error.value = err?.message || '课堂摄像头配置加载失败'
    }
  } finally {
    if (sequence === pollSequence) polling = false
  }
}
async function start() {
  if (starting.value || running.value || !policy.value?.enabled || !policy.value?.service_ready) return
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    error.value = '请通过HTTPS或本机localhost打开，并使用支持摄像头的浏览器'
    return
  }
  const g = run.begin()
  const snapshot = captureSession()
  owner = snapshot
  const id = props.sessionId
  starting.value = true
  error.value = ''
  status.value = '等待摄像头授权'
  guard(g)
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false, video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
    })
    if (!current(g)) { stream.getTracks().forEach((track) => track.stop()); return }
    if (!run.attach(stream, g)) return
    await nextTick()
    if (!current(g)) return
    video.value.srcObject = stream
    await video.value.play()
    if (!current(g)) return
    const opened = await api.openBrowserCapture(id)
    if (!current(g)) {
      if (isCurrentSession(snapshot)) api.stopBrowserCapture(opened.data.capture_id).catch(() => {})
      return
    }
    run.capture = { ...opened.data, revision: policy.value.revision }
    run.capture.upload_url = safeUploadUrl(opened.data.upload_url, window.location.origin)
    clockOffset = Date.parse(opened.data.server_time) - Date.now()
    activeEnd = Date.parse(policy.value.session_end)
    stream.getTracks().forEach((track) => track.addEventListener('ended', () => {
      if (current(g)) stop('摄像头已断开')
    }, { once: true }))
    running.value = true
    sampled.value = accepted.value = 0
    status.value = '采集中，只上传定时单帧'
    scheduleSample(g)
    renewTimer = setTimeout(() => renew(g), 20000)
  } catch (err) {
    if (current(g)) {
      stop('未开启采集')
      error.value = ({
        NotAllowedError: '摄像头权限未允许，可在浏览器地址栏重新授权',
        NotFoundError: '未找到摄像头，请连接内置或USB摄像头',
        NotReadableError: '摄像头无法读取，请关闭其他占用摄像头的软件',
      })[err?.name] || err?.message || '摄像头开启失败'
    }
  } finally {
    if (run.current(g)) starting.value = false
  }
}
function guard(g) {
  if (!current(g)) { if (run.current(g)) stop(); return }
  if (!run.capture) { guardTimer = setTimeout(() => guard(g), 500); return }
  const now = Date.now() + clockOffset
  if (now >= Date.parse(run.capture.expires_at) || now >= activeEnd) {
    stop('课堂或采集授权已到期'); return
  }
  guardTimer = setTimeout(() => guard(g), 500)
}
async function renew(g) {
  if (!current(g)) return
  try {
    const result = await api.renewBrowserCapture(run.capture.capture_id)
    if (!current(g)) return
    run.capture.expires_at = result.data.expires_at
    clockOffset = Date.parse(result.data.server_time) - Date.now()
    renewTimer = setTimeout(() => renew(g), 20000)
  } catch (err) {
    if (current(g)) { stop('采集授权续期失败'); error.value = err?.message || '请重新开启' }
  }
}
function scheduleSample(g) {
  if (!current(g)) return
  sampleTimer = setTimeout(() => sample(g), nextSlotDelay(
    Date.now() + clockOffset, run.capture.sample_interval, run.capture.phase_ms,
  ))
}
async function sample(g) {
  if (!current(g)) return
  if (document.hidden) { stop('页面进入后台，已停止摄像头'); return }
  const canvas = document.createElement('canvas')
  const v = video.value
  let timeout
  try {
    if (!v?.videoWidth || v.readyState < 2) { status.value = '等待摄像头画面'; return }
    const scale = Math.min(640 / v.videoWidth, 480 / v.videoHeight, 1)
    canvas.width = Math.max(1, Math.round(v.videoWidth * scale))
    canvas.height = Math.max(1, Math.round(v.videoHeight * scale))
    canvas.getContext('2d').drawImage(v, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.75))
    if (!current(g)) return
    if (!blob || blob.size > 256 * 1024) { status.value = '本次画面编码失败或超限，已跳过'; return }
    const controller = new AbortController()
    run.controller = controller
    timeout = setTimeout(() => controller.abort(), 20000)
    sampled.value++
    // 不使用带学生JWT的Axios实例；短期授权只发送给独立AI服务。
    const response = await fetch(run.capture.upload_url, {
      method: 'POST', headers: {
        'Content-Type': 'image/jpeg',
        Authorization: 'Bearer ' + run.capture.capture_token,
        'X-Frame-ID': crypto.randomUUID(),
      }, body: blob, signal: controller.signal, credentials: 'omit', redirect: 'error',
    })
    if (!current(g)) return
    if ([401, 403, 409, 410].includes(response.status)) { stop('采集授权已失效，请重新开启'); return }
    if (!response.ok) { status.value = '服务繁忙或网络异常，本次跳过；下个时槽继续'; return }
    const result = await response.json()
    if (!current(g)) return
    status.value = messages[result.status] || '本次未确认入库'
    if (result.status === 'accepted' && !result.duplicate) accepted.value++
  } catch {
    if (current(g)) status.value = '网络中断或超时，本次跳过，不补传历史画面'
  } finally {
    clearTimeout(timeout)
    canvas.width = canvas.height = 0
    if (current(g)) { run.controller = null; scheduleSample(g) }
  }
}
function hidden() { if (document.hidden) stop('页面进入后台，已停止摄像头') }
function leaving() { stop() }
document.addEventListener('visibilitychange', hidden)
window.addEventListener('pagehide', leaving)
watch(() => props.sessionId, () => {
  stop()
  pollSequence++; polling = false
  policy.value = null; error.value = ''
  refreshPolicy()
  clearInterval(policyTimer)
  policyTimer = setInterval(refreshPolicy, 5000)
}, { immediate: true })
onBeforeUnmount(() => {
  stop(); disposed = true; pollSequence++
  clearInterval(policyTimer)
  document.removeEventListener('visibilitychange', hidden)
  window.removeEventListener('pagehide', leaving)
})
</script>

<template>
  <NCard title="摄像头匿名反馈（可选）" size="small">
    <NSpace vertical>
      <p>点击开启即允许定时上传单帧至课堂AI服务。仅记录匿名表情结果，不保存照片或视频；请只让自己入镜。手动反馈仍可正常使用。</p>
      <NAlert v-if="error" type="error">{{ error }}</NAlert>
      <span v-if="policy && !policy.enabled">管理员尚未开启本课堂的自动采集，或已到课堂结束时间。</span>
      <span v-else-if="policy && !policy.service_ready">AI服务暂未就绪，可先使用手动反馈。</span>
      <NSpace align="center">
        <NButton type="primary" :disabled="starting || running || !policy?.enabled || !policy?.service_ready" @click="start">开启摄像头</NButton>
        <NButton :disabled="!starting && !running" @click="stop()">停止摄像头</NButton>
        <NTag>{{ status }}</NTag>
        <span v-if="policy">每 {{ policy.sample_interval }} 秒采样一次</span>
      </NSpace>
      <video ref="video" v-show="starting || running" autoplay muted playsinline
             style="width:100%;max-width:480px;max-height:300px;border-radius:8px;transform:scaleX(-1)" />
      <span v-if="running">本页已尝试 {{ sampled }} 次 · 已确认匿名入库 {{ accepted }} 条</span>
    </NSpace>
  </NCard>
</template>
