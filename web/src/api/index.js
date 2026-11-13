import { request } from '@/utils'
import {
  registrationReady,
  studentRegistrationContract,
  studentClassroomContract,
  teacherRegistrationContract,
  teacherRegistrationReady,
} from './auth-contract'
import { manualEmojiPayload } from '@/utils/emoji'
import { passwordPayload, studentRegistrationPayload } from '@/utils/auth/forms'

// 页面只调用这里的语义化方法，不直接拼接 Axios 请求。
export default {
  login: (data) => request.post('/base/access_token', data, { noNeedToken: true }),
  registerStudent: (data) => {
    if (!registrationReady()) return Promise.reject(new Error('REGISTRATION_PENDING'))
    return request.post(studentRegistrationContract.path, studentRegistrationPayload(data), {
      noNeedToken: true,
    })
  },
  registerTeacher: (data) => {
    if (!teacherRegistrationReady()) return Promise.reject(new Error('REGISTRATION_PENDING'))
    return request.post(teacherRegistrationContract.path, studentRegistrationPayload(data), {
      noNeedToken: true,
    })
  },
  getUserInfo: () => request.get('/base/userinfo'),
  getMySessions: ({ page = 1, page_size = 20 } = {}) => {
    if (!studentClassroomContract.path) {
      return Promise.reject({
        code: 'SCHEDULE_PENDING',
        message: '本人排课接口尚未提供，暂时无法加载或提交。',
      })
    }
    return request.get(studentClassroomContract.path, { params: { page, page_size } })
  },
  submitManualEmoji: (sessionId, emojiType) =>
    request.post('/emoji', manualEmojiPayload(sessionId, emojiType)),
  getMyEmojiHistory: ({ session_id, from_time, to_time, page = 1, page_size = 20 } = {}) =>
    request.get('/emoji/history', { params: { session_id, from_time, to_time, page, page_size } }),
  getClassroomStatistics: ({ session_id, user_id, from_time, to_time, source } = {}) =>
    request.get('/emoji/statistics', {
      params: { session_id, user_id, from_time, to_time, source },
    }),
  getUserMenu: () => request.get('/base/usermenu'),
  getUserApi: () => request.get('/base/userapi'),
  // profile
  updatePassword: (data = {}) => request.post('/base/update_password', passwordPayload(data)),
  // users
  getUserList: (params = {}) => request.get('/user/list', { params }),
  getUserById: (params = {}) => request.get('/user/get', { params }),
  createUser: (data = {}) => request.post('/user/create', data),
  updateUser: (data = {}) => request.post('/user/update', data),
  deleteUser: (params = {}) => request.delete(`/user/delete`, { params }),
  resetPassword: (data = {}) => request.post(`/user/reset_password`, data),
  // role
  getRoleList: (params = {}) => request.get('/role/list', { params }),
  createRole: (data = {}) => request.post('/role/create', data),
  updateRole: (data = {}) => request.post('/role/update', data),
  deleteRole: (params = {}) => request.delete('/role/delete', { params }),
  // auditlog
  getAuditLogList: (params = {}) => request.get('/auditlog/list', { params }),
  // classroom - courses
  getCourses: (params = {}) => request.get('/courses', { params }),
  createCourse: (data = {}) => request.post('/courses', data),
  updateCourse: (data = {}) => request.put(`/courses/${data.id}`, data),
  deleteCourse: (params = {}) => request.delete(`/courses/${params.course_id}`),
  // classroom - sessions
  getSessions: (params = {}) => request.get('/sessions', { params }),
  createSession: (data = {}) => request.post('/sessions', data),
  updateSession: (data = {}) => request.put(`/sessions/${data.id}`, data),
  deleteSession: (params = {}) => request.delete(`/sessions/${params.session_id}`),
  scheduleUser: (sessionId, data = {}) => request.post(`/sessions/${sessionId}/schedule`, data),
  unscheduleUser: (sessionId, userId) =>
    request.delete(`/sessions/${sessionId}/schedule/${userId}`),
  getScheduledUsers: (sessionId, params = {}) =>
    request.get(`/sessions/${sessionId}/schedule`, { params }),
  // classroom - emoji
  getEmojiList: (params = {}) => request.get('/emoji', { params }),
  exportEmoji: (params = {}) => request.get('/emoji/export', { params, responseType: 'blob' }),
  // classroom - dashboard & statistics
  getRealtimeDashboard: (params = {}) => request.get('/dashboard/realtime', { params }),
  getStatistics: (params = {}) => request.get('/statistics', { params }),
  // D controls reuse the existing user session; device secrets never enter this client.
  getAIProfiles: () => request.get('/ai/model-profiles'),
  getBrowserPolicy: (id) => request.get(`/ai/browser/classrooms/${id}`),
  getBrowserManagement: (id) => request.get(`/ai/browser/manage/${id}`),
  setBrowserManagement: (id, data) => request.put(`/ai/browser/manage/${id}`, data),
  openBrowserCapture: (id) => request.post(`/ai/browser/classrooms/${id}/captures`, { consent: true }),
  renewBrowserCapture: (id) => request.post(`/ai/browser/captures/${id}/renew`, {}),
  stopBrowserCapture: (id) => request.post(`/ai/browser/captures/${id}/stop`, {}),
  getAIDevices: () => request.get('/ai/devices'),
  createAIDevice: (data) => request.post('/ai/devices', data),
  updateAIDevice: (id, data) => request.put(`/ai/devices/${id}`, data),
  issueAICredential: (id) => request.post(`/ai/devices/${id}/credentials`, {}),
  revokeAICredential: (id) => request.delete(`/ai/devices/${id}/credentials`),
  getAIJobs: (sessionId) => request.get('/ai/jobs', { params: { session_id: sessionId } }),
  createAIJob: (data) => request.post('/ai/jobs', data),
  controlAIJob: (job, action) =>
    request.post(`/ai/jobs/${job.id}/actions`, { action, revision: job.generation }),
}
