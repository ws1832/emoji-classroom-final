<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NInputNumber, NSelect, NSpace, NTag } from 'naive-ui'
import api from '@/api'
import { captureSession, isCurrentSession } from '@/utils/auth/session'
const props = defineProps({ sessionId: { type: Number, default: null } })
const policy = ref(null), interval = ref(10), threshold = ref(0.7)
const loading = ref(false), pending = ref(false), error = ref('')
const canConfigure = computed(() => policy.value?.can_configure === true)
let sequence = 0, timer
const options = [5, 10, 15, 30].map((value) => ({ value, label: `${value} 秒` }))
async function load() {
  if (!props.sessionId || loading.value || pending.value) return
  const id = props.sessionId, ticket = ++sequence, session = captureSession()
  loading.value = true
  try {
    const result = await api.getBrowserManagement(id)
    if (ticket !== sequence || !isCurrentSession(session)) return
    const previous = policy.value
    policy.value = result.data
    if (!previous || previous.revision !== result.data.revision) {
      interval.value = result.data.sample_interval; threshold.value = result.data.threshold
    }
    error.value = ''
  } catch (err) {
    if (ticket === sequence && isCurrentSession(session)) error.value = err?.message || '采集配置加载失败'
  } finally { if (ticket === sequence) loading.value = false }
}
async function configure(enabled) {
  if (pending.value || !policy.value || !canConfigure.value) return
  const id = props.sessionId, session = captureSession(), ticket = sequence
  pending.value = true; error.value = ''
  try {
    const result = await api.setBrowserManagement(id, {
      enabled, revision: policy.value.revision, sample_interval: interval.value, threshold: threshold.value,
    })
    if (ticket === sequence && isCurrentSession(session)) policy.value = result.data
  } catch (err) {
    if (ticket === sequence && isCurrentSession(session)) error.value = err?.message || '操作失败，请刷新配置'
  } finally {
    if (ticket === sequence) { pending.value = false; await load() }
  }
}
watch(() => props.sessionId, () => {
  sequence++; policy.value = null; loading.value = pending.value = false
  error.value = ''; clearInterval(timer); load(); timer = setInterval(load, 5000)
}, { immediate: true })
onBeforeUnmount(() => { sequence++; clearInterval(timer) })
</script>
<template>
  <NCard :title="canConfigure ? '课堂摄像头采集管理' : '课堂匿名采集状态'" size="small">
    <NSpace vertical>
      <span>学生从自己的课堂网页主动开启普通摄像头；结果强制匿名，不展示个人表情或画面。</span>
      <span v-if="policy && !canConfigure">采集由管理员统一配置和启停；教师仅查看所授课堂状态与匿名汇总。</span>
      <NAlert v-if="error" type="error">{{ error }}</NAlert>
      <span v-if="!sessionId">请在课堂详情或实时看板中选择课堂后配置。</span>
      <NSpace v-if="policy" align="center">
        <NTag :type="policy.enabled ? 'success' : 'default'">{{ policy.enabled ? '课堂采集中' : '课堂采集未开启' }}</NTag>
        <NTag :type="policy.service_ready ? 'info' : 'warning'">{{ policy.service_ready ? 'AI服务在线' : 'AI服务未就绪' }}</NTag>
        <span>采样间隔 {{ !canConfigure ? policy.sample_interval + ' 秒' : '' }}</span>
        <NSelect v-if="canConfigure" v-model:value="interval" :options="options" :disabled="pending" style="width:100px" />
        <NButton v-if="canConfigure" type="primary" :loading="pending" :disabled="!policy.service_ready || loading || pending" @click="configure(true)">
          {{ policy.enabled ? '应用配置' : '开启课堂采集' }}
        </NButton>
        <NButton v-if="canConfigure" :disabled="!policy.enabled || pending" @click="configure(false)">停止课堂采集</NButton>
      </NSpace>
      <NSpace v-if="policy" wrap>
        <span>活动采集页 {{ policy.active_captures || 0 }}</span>
        <span>采样 {{ policy.metrics?.sampled || 0 }}</span>
        <span>匿名入库 {{ policy.metrics?.published || 0 }}</span>
        <span>无脸 {{ policy.metrics?.no_face || 0 }}</span>
        <span>多人 {{ policy.metrics?.multi_face || 0 }}</span>
        <span>过滤 {{ policy.metrics?.filtered || 0 }}</span>
      </NSpace>
      <NCollapse v-if="canConfigure">
        <NCollapseItem title="高级配置与采样说明" name="advanced">
          <NSpace vertical>
            <NSpace align="center"><span>表情置信度阈值</span><NInputNumber v-model:value="threshold" :min="0" :max="1" :step="0.05" :disabled="pending" style="width:120px" /></NSpace>
            <span>默认10秒：45分钟每端最多270次，90分钟540次；无脸、多人、低分不入库。统计的是观测条数，不是学生人数。</span>
            <span>当前模型 {{ policy?.profile || 'edge' }}。应用配置会撤销原采集授权，学生需重新开启。服务部署与接入步骤见 docs/AI_BROWSER_CAPTURE.md。</span>
          </NSpace>
        </NCollapseItem>
      </NCollapse>
      <NButton :loading="loading" :disabled="pending || !sessionId" @click="load">刷新状态</NButton>
    </NSpace>
  </NCard>
</template>
