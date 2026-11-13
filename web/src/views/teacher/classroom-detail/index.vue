<template>
  <CommonPage :title="t('history.teacherTitle')">
    <n-space vertical :size="18">
      <n-button :loading="loading || history.loading || statisticsLoading" @click="load">{{
        t('history.refresh')
      }}</n-button>
      <n-alert v-if="error" type="error">{{ error }}</n-alert>
      <n-descriptions v-if="classroom" :column="1" bordered>
        <n-descriptions-item :label="t('history.course')">{{
          classroom.course_name
        }}</n-descriptions-item>
        <n-descriptions-item :label="t('history.classAndRoom')"
          >{{ classroom.class_name || '—' }} / {{ classroom.classroom || '—' }}</n-descriptions-item
        >
        <n-descriptions-item :label="t('history.time')"
          >{{ classroom.start_time }} — {{ classroom.end_time }}</n-descriptions-item
        >
      </n-descriptions>
      <BrowserClassroomPanel v-if="classroom" :key="classroom.id" :session-id="classroom.id" />
      <HistoryFilters v-model="draft" teacher @apply="apply" @reset="reset" />
      <n-alert v-if="filterError" type="error">{{ filterError }}</n-alert>
      <template v-if="classroom && !filterError">
        <h3>{{ t('history.statistics') }}</h3>
        <EmotionSummary
          :summary="summary"
          :loading="statisticsLoading"
          :error="statisticsError"
          :source="applied.source"
        />
        <h3>{{ t('history.records') }}</h3>
        <EmojiHistory
          :rows="history.rows"
          :loading="history.loading"
          :error="history.error"
          :filtered="filtered"
          show-user
        />
        <n-pagination
          v-if="history.total"
          v-model:page="page"
          :item-count="history.total"
          :page-size="20"
          @update:page="loadPage"
        />
      </template>
    </n-space>
  </CommonPage>
</template>
<script setup>
import { useI18n } from 'vue-i18n'
import CommonPage from '@/components/page/CommonPage.vue'
import EmojiHistory from '@/components/classroom/EmojiHistory.vue'
import HistoryFilters from '@/components/classroom/HistoryFilters.vue'
import EmotionSummary from '@/components/classroom/EmotionSummary.vue'
import BrowserClassroomPanel from '@/components/ai/BrowserClassroomPanel.vue'
import { parseSessionId } from '@/utils/emoji'
import { historyRange, normalizeStatistics } from '@/utils/history'
import { useBusinessList } from '@/composables/useBusinessList'
import { captureSession, isCurrentSession } from '@/utils/auth/session'
import api from '@/api'
const { t } = useI18n()
const route = useRoute()
const page = ref(1)
const classroom = ref(null)
const loading = ref(false)
const error = ref('')
const draft = ref({ range: null, user_id: null, source: null })
const applied = ref({})
const filterError = ref('')
const summary = ref(null)
const statisticsLoading = ref(false)
const statisticsError = ref('')
const history = reactive(useBusinessList(api.getEmojiList))
const filtered = computed(() => Object.keys(applied.value).length > 0)
let sequence = 0
onBeforeUnmount(() => {
  sequence++
})
function loadPage() {
  if (!classroom.value || filterError.value) return
  return history.load({
    ...applied.value,
    session_id: classroom.value.id,
    page: page.value,
    page_size: 20,
  })
}
async function load() {
  const request = ++sequence
  const session = captureSession()
  const current = () => request === sequence && isCurrentSession(session)
  const id = parseSessionId(route.query.session_id)
  const scope = { ...applied.value, session_id: id }
  classroom.value = null
  error.value = ''
  summary.value = null
  statisticsError.value = ''
  statisticsLoading.value = false
  loading.value = false
  history.clear()
  if (filterError.value) return
  if (!id) {
    error.value = t('history.invalidClassroom')
    return
  }
  loading.value = true
  try {
    // Check ownership before requesting records, including empty classrooms.
    const { data } = await api.getRealtimeDashboard({ session_id: id })
    if (!current()) return
    if (data?.session?.id !== id || data.forbidden || !data.found)
      throw new Error(t('history.invalidClassroom'))
    classroom.value = data.session
    statisticsLoading.value = true
    const aggregate = (async () => {
      try {
        const result = await api.getClassroomStatistics(scope)
        if (current()) summary.value = normalizeStatistics(result.data)
      } catch (err) {
        if (current())
          statisticsError.value = err?.message?.startsWith('history.')
            ? t(err.message)
            : err?.message || t('history.loadFailed')
      } finally {
        if (current()) statisticsLoading.value = false
      }
    })()
    await Promise.all([history.load({ ...scope, page: page.value, page_size: 20 }), aggregate])
  } catch (err) {
    if (current()) error.value = err?.message || t('history.loadFailed')
  } finally {
    if (current()) loading.value = false
  }
}
function apply() {
  ++sequence
  history.clear()
  summary.value = null
  statisticsLoading.value = false
  loading.value = false
  filterError.value = ''
  try {
    const range = historyRange(draft.value.range)
    const user = draft.value.user_id
    if (user != null && (!Number.isSafeInteger(user) || user <= 0))
      throw new Error('history.invalidStudent')
    if (draft.value.source != null && !['MANUAL', 'AI'].includes(draft.value.source))
      throw new Error('history.invalidResponse')
    applied.value = {
      ...range,
      ...(user != null ? { user_id: user } : {}),
      ...(draft.value.source ? { source: draft.value.source } : {}),
    }
    page.value = 1
    return load()
  } catch (err) {
    filterError.value = t(err.message)
  }
}
function reset() {
  draft.value = { range: null, user_id: null, source: null }
  return apply()
}
watch(
  () => route.query.session_id,
  () => {
    reset()
  },
  { immediate: true }
)
</script>
