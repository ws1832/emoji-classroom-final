<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NCard, NEmpty, NGrid, NGridItem, NProgress, NSelect, NSpace, NStatistic, NSwitch, NButton } from 'naive-ui'

import CommonPage from '@/components/page/CommonPage.vue'
import api from '@/api'
import BrowserClassroomPanel from '@/components/ai/BrowserClassroomPanel.vue'
import { captureSession, isCurrentSession } from '@/utils/auth/session'
import { useUserStore } from '@/store'
const userStore = useUserStore()

defineOptions({ name: '实时看板' })

const sessionOptions = ref([])
const sessionId = ref(null)
const dashboardData = ref(null)
const loading = ref(false)
const autoRefresh = ref(false)
let timer = null
let sequence = 0

const EMOJI_MAP = {
  HAPPY: '😊',
  SAD: '😢',
  ANGRY: '😠',
  SURPRISED: '😲',
  NEUTRAL: '😐',
}

const maxTimeline = computed(() => {
  const timeline = dashboardData.value?.timeline || []
  return Math.max(1, ...timeline.map((item) => item.count))
})

async function loadSessions() {
  const res = await api.getSessions({ page: 1, page_size: 100 })
  sessionOptions.value = (res.data || []).map((item) => ({
    label: `#${item.id} ${item.class_name || ''} ${item.classroom || ''} (${item.start_time?.slice(0, 16)})`,
    value: item.id,
  }))
}

async function loadDashboard() {
  const ticket = ++sequence
  const id = sessionId.value
  const snapshot = captureSession()
  const current = () => ticket === sequence && id === sessionId.value && isCurrentSession(snapshot)
  if (!sessionId.value) {
    dashboardData.value = null
    return
  }
  loading.value = true
  try {
    const res = await api.getRealtimeDashboard({ session_id: sessionId.value })
    if (current()) dashboardData.value = res.data
  } catch (error) {
    if (current()) dashboardData.value = null
  } finally {
    if (current()) loading.value = false
  }
}

onMounted(async () => {
  await loadSessions()
  if (sessionOptions.value.length) {
    sessionId.value = sessionOptions.value[0].value
    await loadDashboard()
  }
})

onBeforeUnmount(() => {
  sequence++
  if (timer) clearInterval(timer)
})

function onAutoRefreshChange(value) {
  autoRefresh.value = value
  if (timer) clearInterval(timer)
  if (value) {
    timer = setInterval(loadDashboard, 10000)
  }
}
</script>

<template>
  <CommonPage show-footer :title="userStore.isAdministrator ? '课堂管理 · 实时情绪看板' : '所授课堂 · 实时情绪看板'">
    <div mb-15 flex items-center gap-15>
      <NSelect
        v-model:value="sessionId"
        :options="sessionOptions"
        placeholder="选择课堂"
        style="width: 360px"
        @update:value="loadDashboard"
      />
      <NButton type="primary" :loading="loading" @click="loadDashboard">刷新</NButton>
      <NSpace align="center">
        <span>自动刷新</span>
        <NSwitch :value="autoRefresh" @update:value="onAutoRefreshChange" />
      </NSpace>
    </div>

    <NEmpty v-if="!dashboardData" description="请选择课堂查看实时看板" />

    <template v-else>
      <BrowserClassroomPanel :key="sessionId" :session-id="sessionId" />
      <NGrid :cols="4" :x-gap="12" :y-gap="12">
        <NGridItem>
          <NCard size="small">
            <NStatistic label="总记录数" :value="dashboardData.total_count" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard size="small">
            <NStatistic label="参与学生数" :value="dashboardData.student_count" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard size="small">
            <NStatistic label="手动记录" :value="dashboardData.manual_count" />
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard size="small">
            <NStatistic label="AI 记录" :value="dashboardData.ai_count" />
          </NCard>
        </NGridItem>
      </NGrid>

      <NCard title="课堂信息" size="small" mt-15>
        <NSpace wrap :size="[24, 8]">
          <span>课程：{{ dashboardData.session.course_name }}</span>
          <span>班级：{{ dashboardData.session.class_name || '-' }}</span>
          <span>教室：{{ dashboardData.session.classroom || '-' }}</span>
          <span>时间：{{ dashboardData.session.start_time }} ~ {{ dashboardData.session.end_time }}</span>
        </NSpace>
      </NCard>

      <NCard title="情绪分布" size="small" mt-15>
        <div v-for="item in dashboardData.summary" :key="item.emoji_type" flex items-center gap-10 py-6>
          <span w-120>{{ EMOJI_MAP[item.emoji_type] || '' }} {{ item.emoji_type }}</span>
          <NProgress
            type="line"
            :percentage="item.percentage"
            :height="18"
            indicator-placement="inside"
            flex-1
          />
          <span w-100 text-right>{{ item.count }} 条 ({{ item.percentage }}%)</span>
        </div>
      </NCard>

      <NCard title="情绪时间线" size="small" mt-15>
        <div flex items-end gap-4 h-120>
          <div v-for="item in dashboardData.timeline" :key="item.time" flex flex-col items-center flex-1>
            <span text-12>{{ item.count }}</span>
            <div
              :style="{ height: `${(item.count / maxTimeline) * 80}px` }"
              w-full
              max-w-40
              rounded-t-4
              bg="#2080f0"
            ></div>
            <span text-10 op-60 mt-4>{{ item.time.slice(11) }}</span>
          </div>
        </div>
      </NCard>
    </template>
  </CommonPage>
</template>
