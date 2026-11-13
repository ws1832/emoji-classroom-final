<template>
  <CommonPage :title="t('classroom.studentTitle')">
    <n-space vertical :size="18">
      <n-alert v-if="!scheduleAvailable" type="info" :title="t('classroom.pending')">{{
        t('classroom.missing')
      }}</n-alert>
      <n-button :loading="list.loading" :disabled="submitting" @click="load">{{
        t('classroom.refresh')
      }}</n-button>
      <n-alert v-if="list.error" type="error">{{ list.error }}</n-alert>
      <n-empty v-else-if="!list.loading && !list.rows.length" :description="t('classroom.empty')" />
      <n-spin :show="list.loading">
        <n-select
          v-model:value="sessionId"
          :options="options"
          :placeholder="t('classroom.choose')"
          :disabled="submitting || list.loading || !scheduleAvailable"
        />
      </n-spin>
      <n-pagination
        v-if="list.total"
        v-model:page="page"
        :item-count="list.total"
        :page-size="20"
        :disabled="submitting"
        @update:page="load"
      />
      <n-descriptions v-if="selected" :column="1" bordered>
        <n-descriptions-item :label="t('classroom.course')">{{
          selected.course_name || t('classroom.coursePrefix') + selected.course_id
        }}</n-descriptions-item>
        <n-descriptions-item :label="t('classroom.room')"
          >{{ selected.class_name || '—' }} / {{ selected.classroom || '—' }}</n-descriptions-item
        >
        <n-descriptions-item :label="t('classroom.time')"
          >{{ selected.start_time }} — {{ selected.end_time }}</n-descriptions-item
        >
      </n-descriptions>
      <StudentCameraCapture v-if="selected" :key="selected.id" :session-id="selected.id" />
      <EmojiPicker v-model="emoji" :disabled="submitting" />
      <n-alert v-if="submitError" type="error">{{ submitError }}</n-alert>
      <n-alert v-if="uncertain" type="warning">{{ t('classroom.uncertain') }}</n-alert>
      <n-alert v-if="success" type="success">{{ t('classroom.success') }}</n-alert>
      <n-space>
        <n-button
          type="primary"
          :loading="submitting"
          :disabled="
            !selected || !emoji || list.loading || submitting || uncertain || !scheduleAvailable
          "
          @click="submit"
          >{{ t('classroom.submit') }}</n-button
        >
        <n-button
          @click="
            router.push({
              path: '/student/history',
              query: sessionId ? { session_id: String(sessionId) } : {},
            })
          "
          >{{ t('classroom.history') }}</n-button
        >
        <n-button v-if="uncertain" :disabled="submitting" @click="uncertain = false">{{
          t('classroom.ack')
        }}</n-button>
      </n-space>
    </n-space>
  </CommonPage>
</template>
<script setup>
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import CommonPage from '@/components/page/CommonPage.vue'
import EmojiPicker from '@/components/classroom/EmojiPicker.vue'
import StudentCameraCapture from '@/components/ai/StudentCameraCapture.vue'
import { useBusinessList } from '@/composables/useBusinessList'
import { studentClassroomContract } from '@/api/auth-contract'
import { captureSession, isCurrentSession } from '@/utils/auth/session'
import api from '@/api'

const router = useRouter()
const scheduleAvailable = Boolean(studentClassroomContract.path)
const list = reactive(useBusinessList(api.getMySessions))
const page = ref(1)
const sessionId = ref(null)
const emoji = ref('')
const submitting = ref(false)
const submitError = ref('')
const success = ref(false)
const uncertain = ref(false)
const selected = computed(() => list.rows.find((item) => item.id === sessionId.value))
const options = computed(() =>
  list.rows.map((item) => ({
    value: item.id,
    label:
      (item.course_name || t('classroom.coursePrefix') + item.course_id) +
      ' / ' +
      (item.class_name || '—') +
      ' / ' +
      item.start_time,
  }))
)
async function load() {
  if (submitting.value) return
  await list.load({ page: page.value })
  if (!selected.value) sessionId.value = null
}
async function submit() {
  if (submitting.value || uncertain.value || !scheduleAvailable || !selected.value || !emoji.value)
    return
  const session = captureSession()
  submitting.value = true
  submitError.value = ''
  success.value = false
  let refresh = false
  try {
    await api.submitManualEmoji(sessionId.value, emoji.value)
    if (isCurrentSession(session)) success.value = true
  } catch (error) {
    if (!isCurrentSession(session)) return
    submitError.value = error?.message || t('classroom.failed')
    if ([403, 404].includes(error?.code)) {
      submitError.value = t('classroom.denied')
      sessionId.value = null
      refresh = true
    } else if (![400, 401, 409, 422].includes(error?.code)) {
      uncertain.value = true
    }
  } finally {
    submitting.value = false
  }
  if (refresh) await load()
}
onMounted(load)
</script>
