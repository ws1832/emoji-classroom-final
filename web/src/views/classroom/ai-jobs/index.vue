<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { NAlert, NButton, NPagination, NSelect, NSpace } from 'naive-ui'
import CommonPage from '@/components/page/CommonPage.vue'
import BrowserClassroomPanel from '@/components/ai/BrowserClassroomPanel.vue'
import api from '@/api'
import { captureSession, isCurrentSession } from '@/utils/auth/session'
import { formatDateTime } from '@/utils'
defineOptions({ name: '课堂采集管理' })
const options = ref([]), sessionId = ref(null), page = ref(1), total = ref(0)
const loading = ref(false), error = ref('')
let sequence = 0
async function load() {
  const ticket = ++sequence, snapshot = captureSession()
  const current = () => ticket === sequence && isCurrentSession(snapshot)
  loading.value = true; error.value = ''
  try {
    const result = await api.getSessions({ page: page.value, page_size: 100 })
    if (!current()) return
    options.value = (result.data || []).map((item) => ({
      value: item.id,
      label: `#${item.id} · 课程 #${item.course_id} · ${item.class_name || item.classroom || '未命名课堂'} · ${formatDateTime(item.start_time)}`,
    }))
    total.value = result.total || 0
    if (!options.value.some((item) => item.value === sessionId.value))
      sessionId.value = options.value[0]?.value ?? null
  } catch (err) {
    if (current()) { error.value = err?.message || '课堂列表加载失败'; options.value = []; sessionId.value = null }
  } finally { if (current()) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => { sequence++ })
</script>
<template>
  <CommonPage title="全部课堂 · 采集管理">
    <NSpace vertical :size="16">
      <NAlert v-if="error" type="error">{{ error }}</NAlert>
      <NSpace align="center">
        <NSelect v-model:value="sessionId" :options="options" :loading="loading" :disabled="loading" filterable placeholder="选择需要管理的课堂" style="width: min(560px, 70vw)" />
        <NButton :loading="loading" @click="load">刷新课堂</NButton>
        <NPagination v-if="total > 100" v-model:page="page" :page-size="100" :item-count="total" :disabled="loading" @update:page="load" />
      </NSpace>
      <BrowserClassroomPanel :session-id="sessionId" />
    </NSpace>
  </CommonPage>
</template>
