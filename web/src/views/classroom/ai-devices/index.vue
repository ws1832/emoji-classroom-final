<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NInput, NModal, NSpace, NTag, NPopconfirm } from 'naive-ui'
import CommonPage from '@/components/page/CommonPage.vue'
import { captureSession, isCurrentSession } from '@/utils/auth/session'
import { aiState } from '@/utils/ai'
import api from '@/api'
defineOptions({ name: 'AI服务身份' })
const devices = ref([])
const name = ref('')
const alias = ref('')
const loading = ref(false)
const error = ref('')
const secret = ref('')
const secretVisible = ref(false)
let sequence = 0
onBeforeUnmount(() => { sequence++; secret.value = ''; secretVisible.value = false })

async function operation(fn) {
  if (loading.value) return
  const ticket = ++sequence
  const session = captureSession()
  const current = () => ticket === sequence && isCurrentSession(session)
  loading.value = true
  error.value = ''
  secret.value = ''
  secretVisible.value = false
  try {
    const result = fn ? await fn() : null
    if (!current()) return
    if (result?.data?.token) {
      secret.value = result.data.token
      secretVisible.value = true
    }
    const response = await api.getAIDevices()
    if (!current()) return
    devices.value = response.data || []
  } catch (err) {
    if (current()) error.value = err.message || '设备操作失败'
  } finally {
    if (current()) loading.value = false
  }
}
function create() {
  return operation(() => {
    if (!name.value.trim() || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(alias.value))
      throw new Error('设备名称必填，source alias 仅允许字母、数字、点、下划线、连字符')
    return api.createAIDevice({ name: name.value.trim(), source_alias: alias.value, teacher_ids: [] })
  })
}
function save(device, enabled = device.enabled) {
  return operation(() => api.updateAIDevice(device.id, { enabled, teacher_ids: device.teacher_ids || [] }))
}
onMounted(() => operation())
</script>
<template>
  <CommonPage title="AI 服务身份">
    <NSpace vertical :size="16">
      <NAlert type="info">此页仅供管理员注册服务器上的独立AI服务，不是公共摄像头入口。学生在自己的课堂网页开启摄像头，无需安装程序或领取永久凭证。接入步骤见 docs/AI_BROWSER_CAPTURE.md。</NAlert>
      <NAlert v-if="error" type="error">{{ error }}</NAlert>
      <NCard title="注册服务身份" size="small">
        <NSpace>
          <NInput v-model:value="name" placeholder="服务名称" :maxlength="80" :disabled="loading" />
          <NInput v-model:value="alias" placeholder="来源别名，例如 student-browser" :maxlength="64" :disabled="loading" />
          <NButton type="primary" :loading="loading" @click="create">注册</NButton>
          <NButton :disabled="loading" @click="operation()">刷新</NButton>
        </NSpace>
      </NCard>
      <NCard v-for="device in devices" :key="device.id" :title="`#${device.id} ${device.name} · ${device.source_alias}`" size="small">
        <NSpace vertical>
          <NSpace>
            <NTag :type="device.online ? 'success' : 'warning'">{{ device.online ? '在线' : '离线' }} · {{ device.enabled ? '启用' : '禁用' }}</NTag>
            <span>{{ aiState[device.health] || device.health }} · {{ device.profiles.join(', ') || '模型未准备' }} · {{ device.last_seen || '未连接' }}</span>
          </NSpace>
          <NSpace>
            <NPopconfirm @positive-click="save(device, !device.enabled)">
              <template #trigger><NButton :disabled="loading">{{ device.enabled ? '禁用' : '启用' }}</NButton></template>
              禁用服务会终止所有相关课堂的活动采集，确认修改？
            </NPopconfirm>
            <NPopconfirm @positive-click="operation(() => api.issueAICredential(device.id))">
              <template #trigger><NButton type="primary" :disabled="loading || !device.enabled">签发 / 轮换凭证</NButton></template>
              原凭证与活动任务会失效，新凭证仅显示一次，确认？
            </NPopconfirm>
            <NPopconfirm @positive-click="operation(() => api.revokeAICredential(device.id))">
              <template #trigger><NButton type="error" :disabled="loading">撤销凭证</NButton></template>
              所有凭证与活动租约立即失效，确认撤销？
            </NPopconfirm>
          </NSpace>
        </NSpace>
      </NCard>
    </NSpace>
    <NModal v-model:show="secretVisible" preset="card" title="一次性设备凭证" style="width: min(640px, 95vw)" @update:show="secret = ''">
      <NAlert type="info">仅此一次显示。保存到服务器受限 secret 文件；不要发给学生。关闭后无法再次读取，丢失请轮换。</NAlert>
      <pre style="white-space: pre-wrap; overflow-wrap: anywhere" data-testid="device-secret">{{ secret }}</pre>
      <NButton @click="secretVisible = false; secret = ''">已保存，关闭并清除</NButton>
    </NModal>
  </CommonPage>
</template>
