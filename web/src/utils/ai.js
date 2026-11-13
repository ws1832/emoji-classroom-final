export function canControlAI(job, action) {
  if (!job?.active || job.desired === 'stopped') return false
  if (action === 'stop') return true
  if (action === 'pause') return job.desired === 'running'
  return (
    action === 'start' &&
    ['ready', 'paused'].includes(job.desired) &&
    ['ready', 'paused'].includes(job.observed)
  )
}

export function teacherIds(text) {
  if (!text.trim()) return []
  const values = text.split(',').map((id) => id.trim())
  if (values.length > 100 || values.some((id) => !/^[1-9]\d*$/.test(id)))
    throw new Error('教师 ID 应为最多 100 个逗号分隔的正整数')
  const result = values.map(Number)
  if (result.some((id) => !Number.isSafeInteger(id))) throw new Error('教师 ID 超出范围')
  return [...new Set(result)]
}

export const aiState = {
  ready: '预检就绪', running: '采集中', paused: '已暂停', stopped: '已停止',
  failed: '失败', prechecking: '等待预检', waiting: '等待任务', no_frame: '无画面',
  no_face: '无人脸', model_failed: '模型失败', buffering: '离线缓冲',
  degraded: '异常 / 租约到期', eof: '视频已结束', credential_revoked: '凭证已撤销',
}
