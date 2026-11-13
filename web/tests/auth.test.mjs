// 功能测试：认证、注册、改密、角色导航、情绪提交、历史筛选与统计。
import assert from 'node:assert/strict'
import { formatDateTime } from '../src/utils/common/common.js'
import { test, beforeEach } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { state, resetFixture, route, useUserStore, lStorage } from './auth-fixtures.mjs'
import {
  getBusinessRoles,
  getDefaultPath,
  canAccessBusinessRoute,
  getSafeRedirect,
  filterBusinessMenus,
  isAdministrator,
} from '../src/utils/auth/business.js'
import { validEmail, samePassword, clearLegacyPassword } from '../src/utils/auth/forms.js'
import { studentRegistrationContract } from '../src/api/auth-contract.js'
const realRegistrationPasswordValidator = studentRegistrationContract.passwordValidator
import api from '../src/api/index.js'
import { reqResolve, resResolve, resReject } from '../src/utils/http/interceptors.js'
import { createAuthGuard } from '../src/router/guard/auth-guard.js'
import { usePermissionStore as useActualPermissionStore } from '../src/store/modules/permission/index.js'
import { initializeSessionAccess } from '../src/utils/auth/session.js'
import Login from '../src/views/login/index.vue'
import Register from '../src/views/register/index.vue'
import Profile from '../src/views/profile/index.vue'
import StudentClassroom from '../src/views/student/classroom/index.vue'
import TeacherDetail from '../src/views/teacher/classroom-detail/index.vue'
import StudentHistory from '../src/views/student/history/index.vue'
import { historyRange, normalizeStatistics } from '../src/utils/history.js'
import { studentClassroomContract } from '../src/api/auth-contract.js'
import { useBusinessList } from '../src/composables/useBusinessList.js'
import {
  manualEmojiPayload,
  parseSessionId,
  EMOTIONS,
  recordUserLabel,
} from '../src/utils/emoji.js'
import { canControlAI, teacherIds } from '../src/utils/ai.js'
import { routeBreadcrumbs, upsertRouteTag } from '../src/utils/tags.js'

test('empty child routes do not repeat the same breadcrumb title', () => {
  const matched = [
    { path: '/teacher/classroom', meta: { title: '我的课堂' } },
    { path: '/teacher/classroom', meta: { title: '我的课堂' } },
    { path: '/teacher/classroom/detail', meta: { title: '课堂历史' } },
    { path: '/untitled', meta: {} },
  ]
  assert.deepEqual(routeBreadcrumbs(matched), [matched[0], matched[2]])
})

test('route tabs refresh legacy internal labels without duplicates or input mutation', () => {
  const old = [{ path: '/teacher/classroom', name: 'TeacherClassroomHome', title: 'TeacherClassroomHome' }]
  const updated = upsertRouteTag(old, {
    path: '/teacher/classroom', name: 'TeacherClassroomHome', title: '我的课堂',
  })
  assert.equal(updated.length, 1)
  assert.equal(updated[0].title, '我的课堂')
  assert.equal(updated[0].name, 'TeacherClassroomHome')
  assert.equal(old[0].title, 'TeacherClassroomHome')
  assert.equal(upsertRouteTag(updated, { path: '/teacher/classroom' })[0].title, '我的课堂')
  assert.equal(upsertRouteTag(updated, { path: '/student/history', title: '个人历史' }).length, 2)
})

test('D AI actions require live revisions/preflight and grants parse strictly', async () => {
  const job = { id: 4, active: true, desired: 'ready', observed: 'prechecking', generation: 2 }
  assert.equal(canControlAI(job, 'start'), false)
  assert.equal(canControlAI({ ...job, observed: 'ready' }, 'start'), true)
  assert.equal(canControlAI({ ...job, desired: 'stopped', observed: 'ready' }, 'start'), false)
  assert.equal(canControlAI({ ...job, desired: 'running' }, 'pause'), true)
  assert.equal(canControlAI({ ...job, active: false }, 'stop'), false)
  assert.deepEqual(teacherIds('1, 3, 1'), [1, 3])
  for (const invalid of ['1,-2', '1,', '1.0', '9007199254740992'])
    assert.throws(() => teacherIds(invalid))
  await api.controlAIJob(job, 'stop')
  assert.equal(state.calls.at(-1).path, '/ai/jobs/4/actions')
  assert.deepEqual(state.calls.at(-1).data, { action: 'stop', revision: 2 })
})

function setup(component) {
  return component.setup({}, { expose() {} })
}
function formRef(page, validate = async () => {}) {
  const key = page.passwordFormRef ? 'passwordFormRef' : 'formRef'
  page[key].value = { validate, restoreValidation() {} }
}
beforeEach(() => {
  resetFixture()
  state.getWait = null
  state.getHandler = null
  studentClassroomContract.path = null
  state.postHandler = null
  state.tagError = false
  route.query = {}
  setActivePinia(createPinia())
  studentRegistrationContract.path = null
  studentRegistrationContract.passwordValidator = null
})

test('Beijing display converts absolute timestamps and preserves business wall-clock time', () => {
  assert.equal(formatDateTime('2026-11-09T00:00:00Z'), '2026-11-09 08:00:00')
  assert.equal(formatDateTime('2026-11-09 08:00:00'), '2026-11-09 08:00:00')
  assert.equal(formatDateTime('2026-11-09T08:00:00+08:00'), '2026-11-09 08:00:00')
  assert.equal(formatDateTime(null), '—')
})

test('phase5 production registration password policy requires letters and digits', () => {
  for (const password of ['', 'a'.repeat(7), 'a'.repeat(129), null, 'a'.repeat(8), '12345678', '😀'.repeat(8)])
    assert.equal(realRegistrationPasswordValidator(password), false)
  for (const password of ['a1'.repeat(4), 'A1'.repeat(64), 'Passw0rd123'])
    assert.equal(realRegistrationPasswordValidator(password), true)
})

test('review business namespaces remain guarded without dynamic menu metadata', () => {
  for (const path of [
    '/student/history',
    '/student/history/detail',
    '/student',
    '/teacher/classroom/detail',
  ]) {
    assert.equal(canAccessBusinessRoute({ path }, {}), false)
    assert.equal(
      canAccessBusinessRoute(
        { path },
        { role_codes: [path.startsWith('/student') ? 'STUDENT' : 'TEACHER'] }
      ),
      true
    )
  }
  assert.equal(canAccessBusinessRoute({ path: '/student-tools' }, {}), true)
  assert.equal(filterBusinessMenus([{ path: '/student/history', name: 'dynamic' }], {}).length, 0)
})

test('review history rejects invalid calendar dates and malformed aggregate rows', () => {
  for (const value of [
    '2026-02-29 10:00:00',
    '2026-11-31 10:00:00',
    '2026-11-09 24:00:00',
    '0000-01-01 00:00:00',
  ])
    assert.throws(() => historyRange([value, value]), /history.invalidRange/)
  assert.deepEqual(historyRange(['2024-02-29 00:00:00', '2024-02-29 00:00:00']), {
    from_time: '2024-02-29 00:00:00',
    to_time: '2024-02-29 00:00:00',
  })
  assert.throws(() => normalizeStatistics([null]), /history.invalidResponse/)
})

test('role IDs, labels, absent or malformed codes never grant business access', () => {
  for (const user of [
    {},
    { roles: [{ id: 1, name: 'TEACHER' }] },
    { role_codes: 'STUDENT' },
    { role_codes: [null, {}, '__proto__'] },
  ]) {
    assert.deepEqual(getBusinessRoles(user), [])
    assert.equal(getDefaultPath(user), '/account')
  }
  assert.deepEqual(getBusinessRoles({ role_codes: ['TEACHER', 'STUDENT', 'TEACHER'] }), [
    'TEACHER',
    'STUDENT',
  ])
  assert.equal(getDefaultPath({ is_superuser: true }), '/classroom/dashboard')
})

test('single and dual role defaults and switching use only returned codes', () => {
  const user = useUserStore()
  user.setUserInfo({ id: 1, role_codes: ['STUDENT', 'TEACHER'] })
  assert.equal(user.defaultPath, '/student/classroom')
  assert.equal(user.switchBusinessRole('TEACHER'), true)
  assert.equal(user.defaultPath, '/teacher/classroom')
  assert.equal(user.switchBusinessRole('ADMIN'), false)
  assert.equal(user.defaultPath, '/teacher/classroom')
  assert.equal(
    canAccessBusinessRoute({ path: '/teacher/classroom' }, { role_codes: ['STUDENT'] }),
    false
  )
})

test('administrators use global workbench even with legacy teacher/student ownership', () => {
  for (const identity of [{ is_admin: true }, { is_superuser: true }]) {
    const data = { id: 1, role_codes: ['STUDENT', 'TEACHER'], ...identity }
    assert.equal(isAdministrator(data), true)
    assert.deepEqual(getBusinessRoles(data), [])
    assert.equal(getDefaultPath(data, 'TEACHER'), '/classroom/dashboard')
    assert.equal(canAccessBusinessRoute({ path: '/teacher/classroom' }, data), false)
    assert.equal(canAccessBusinessRoute({ path: '/student/classroom' }, data), false)
    assert.deepEqual(filterBusinessMenus([
      { path: '/teacher/classroom', name: '我的课堂' },
      { path: '/student/classroom', name: '学生反馈' },
      { path: '/classroom', name: '课堂管理', children: [{ path: 'dashboard', name: '实时看板' }] },
    ], data).map((item) => item.path), ['/classroom'])
    const store = useUserStore()
    store.setUserInfo(data)
    assert.equal(store.isAdministrator, true)
    assert.equal(store.switchBusinessRole('TEACHER'), false)
    assert.equal(store.defaultPath, '/classroom/dashboard')
  }
  assert.equal(isAdministrator({ roles: [{ name: 'ADMIN' }], role_codes: ['ADMIN'], is_admin: 'true' }), false)
})

test('userinfo errors propagate instead of returning an Error as successful user data', async () => {
  state.failUser = true
  await assert.rejects(useUserStore().getUserInfo(), /offline/)
  assert.equal(useUserStore().userId, undefined)
})

test('restoring a fresh store gets business roles from userinfo rather than browser role storage', async () => {
  state.token = 'existing-jwt'
  state.userInfo.role_codes = ['TEACHER']
  const user = useUserStore()
  assert.equal(user.userId, undefined)
  await user.getUserInfo()
  assert.equal(user.defaultPath, '/teacher/classroom')
  assert.equal(state.token, 'existing-jwt')
})

test('existing menu trees keep backend entries while filtering unauthorized business children', () => {
  const tree = [
    { path: '/teacher', children: [{ path: 'classroom', name: 'Teacher' }] },
    { path: '/student/classroom', name: 'Student', meta: { businessRole: 'STUDENT' } },
    { path: '/backend-authorized-report', name: 'Report' },
  ]
  assert.deepEqual(
    filterBusinessMenus(tree, { role_codes: ['STUDENT'] }).map((item) => item.path),
    ['/student/classroom', '/backend-authorized-report']
  )
  assert.equal(filterBusinessMenus(tree, { role_codes: ['STUDENT', 'TEACHER'] }).length, 3)
  assert.equal(tree[0].children.length, 1)
})

test('disabled users are not accepted by frontend session initialization', async () => {
  state.userInfo.is_active = false
  await assert.rejects(useUserStore().getUserInfo(), /USER_INFO_UNAVAILABLE/)
})

test('logout removes token, user, active role, menus, tags and dynamic routes', async () => {
  state.token = 'old'
  const user = useUserStore()
  user.setUserInfo({ id: 1, role_codes: ['TEACHER'] })
  user.switchBusinessRole('TEACHER')
  await user.logout()
  assert.equal(state.token, '')
  assert.equal(user.userId, undefined)
  assert.equal(user.activeBusinessRole, '')
  assert.equal(state.resetCount, 1)
  assert.equal(state.menuResetCount, 1)
  assert.equal(state.tagResetCount, 1)
  assert.deepEqual(state.navigation, ['/login'])
})

test('redirects reject external paths, unknown routes and unauthorized business entries', () => {
  const memory = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/profile', component: {} },
      { path: '/student/classroom', component: {}, meta: { businessRole: 'STUDENT' } },
      { path: '/teacher/classroom', component: {}, meta: { businessRole: 'TEACHER' } },
    ],
  })
  const user = { role_codes: ['STUDENT'] }
  for (const value of [
    'https://evil.test',
    '//evil.test',
    '/\\evil.test',
    '/%2f%2fevil',
    '/teacher/classroom',
    '/missing',
    ['/profile'],
  ]) {
    assert.equal(getSafeRedirect(value, memory, user), null)
  }
  assert.equal(getSafeRedirect('/profile?tab=password', memory, user), '/profile?tab=password')
})

test('real auth guard allows public registration, preserves queries, forbids teacher URLs for students', async () => {
  const memory = createRouter({
    history: createMemoryHistory(),
    routes: [
      '/login',
      '/register',
      '/403',
      '/profile',
      '/teacher/classroom',
      '/student/classroom',
      '/account',
    ].map((path) => ({ path, component: {} })),
  })
  createAuthGuard(memory)
  await memory.push('/register')
  assert.equal(memory.currentRoute.value.path, '/register')
  await memory.push('/profile?tab=password')
  assert.equal(memory.currentRoute.value.path, '/login')
  assert.equal(memory.currentRoute.value.query.redirect, '/profile?tab=password')
  state.token = 'valid'
  useUserStore().setUserInfo({ id: 1, role_codes: ['STUDENT'] })
  await memory.push('/teacher/classroom')
  assert.equal(memory.currentRoute.value.path, '/403')
  await memory.push('/login')
  assert.equal(memory.currentRoute.value.path, '/student/classroom')
  useUserStore().setUserInfo({ id: 1, role_codes: ['STUDENT', 'TEACHER'] })
  await memory.push('/teacher/classroom')
  assert.equal(useUserStore().defaultPath, '/teacher/classroom')
})

test('email and password matching keep exact passwords and validate confirmation', () => {
  assert.equal(validEmail(' student@example.com '), true)
  for (const email of ['', 'abc', 'a@b', 'a b@example.com']) assert.equal(validEmail(email), false)
  assert.equal(samePassword(' x ', ' x '), true)
  assert.equal(samePassword('x', 'x '), false)
  assert.equal(samePassword('', ''), false)
})

test('legacy storage is reduced to username without persisting the password', () => {
  state.values.set('loginInfo', {
    username: 'student',
    password: 'secret',
    anotherPassword: 'secret',
  })
  clearLegacyPassword(lStorage)
  assert.deepEqual(state.values.get('loginInfo'), { username: 'student' })
})

test('registration is locally blocked while the public contract is absent', async () => {
  await assert.rejects(
    api.registerStudent({ username: 'a', email: 'a@b.com', password: 'x' }),
    /REGISTRATION_PENDING/
  )
  const page = setup(Register)
  assert.equal(page.ready.value, false)
  await page.handleRegister()
  assert.equal(state.calls.length, 0)
  assert.equal(page.errorMessage.value, 'auth.registrationPending')
})

test('registration with a test-only confirmed contract strips roles and confirmation', async () => {
  studentRegistrationContract.path = '/base/register'
  studentRegistrationContract.passwordValidator = () => true
  await api.registerStudent({
    username: ' student ',
    email: ' a@b.com ',
    password: ' secret ',
    confirmation: ' secret ',
    role_ids: [1],
    is_superuser: true,
  })
  assert.deepEqual(state.calls[0].data, {
    username: 'student',
    email: 'a@b.com',
    password: ' secret ',
  })
  assert.deepEqual(state.calls[0].config, { noNeedToken: true })
})

test('registration conflict keeps inputs and restores submit state; success only carries username', async () => {
  studentRegistrationContract.path = '/base/register'
  studentRegistrationContract.passwordValidator = () => true
  const page = setup(Register)
  formRef(page)
  Object.assign(page.form, {
    username: 'student',
    email: 'a@b.com',
    password: 'secret',
    confirmation: 'secret',
  })
  state.postError = { code: 409, message: 'Email already exists' }
  await page.handleRegister()
  assert.equal(page.errorMessage.value, 'Email already exists')
  assert.equal(page.form.email, 'a@b.com')
  assert.equal(page.loading.value, false)
  state.postError = null
  await page.handleRegister()
  assert.deepEqual(state.navigation.at(-1), { path: '/login', query: { username: 'student' } })
  assert.equal(page.form.password, '')
  assert.equal(state.values.has('loginInfo'), false)
})

test('login initialization waits for userinfo and sends no extra credentials fields', async () => {
  state.userInfo.role_codes = ['TEACHER']
  const page = setup(Login)
  formRef(page)
  Object.assign(page.form, { username: ' teacher ', password: 'secret' })
  await page.handleLogin()
  assert.equal(state.token, 'test-jwt')
  assert.equal(useUserStore().userId, 1)
  assert.deepEqual(
    state.calls.map((call) => call.path),
    ['/base/access_token', '/base/userinfo']
  )
  assert.deepEqual(state.calls[0].data, { username: 'teacher', password: 'secret' })
  assert.equal(state.navigation.at(-1), '/teacher/classroom')
  assert.equal(page.form.password, '')
})

test('failed menu initialization clears the new token and never reports login success', async () => {
  state.failInit = true
  const page = setup(Login)
  formRef(page)
  Object.assign(page.form, { username: 'student', password: 'secret' })
  await page.handleLogin()
  assert.equal(state.token, '')
  assert.equal(useUserStore().userId, undefined)
  assert.equal(page.loading.value, false)
  assert.equal(page.errorMessage.value, 'menu offline')
  assert.equal(state.messages.includes('views.login.message_login_success'), false)
})

test('wrong password and network failures restore login inputs and submit state', async () => {
  for (const error of [{ message: '密码错误!' }, new Error('Network Error')]) {
    const page = setup(Login)
    formRef(page)
    Object.assign(page.form, { username: 'student', password: 'secret' })
    state.postError = error
    await page.handleLogin()
    assert.equal(page.loading.value, false)
    assert.equal(page.form.username, 'student')
    assert.equal(page.errorMessage.value, error.message)
    assert.equal(state.token, '')
  }
})

test('form validation failures restore loading and do not send requests', async () => {
  const page = setup(Profile)
  formRef(page, async () => {
    throw [{ message: 'required' }]
  })
  await page.updatePassword()
  assert.equal(page.loading.value, false)
  assert.equal(state.calls.length, 0)
})

test('password change only posts old/new password, logs out and resets fields', async () => {
  state.token = 'valid'
  const page = setup(Profile)
  formRef(page)
  Object.assign(page.passwordForm, {
    old_password: 'old',
    new_password: 'new',
    confirm_password: 'new',
  })
  await page.updatePassword()
  assert.equal(state.calls[0].path, '/base/update_password')
  assert.deepEqual(state.calls[0].data, { old_password: 'old', new_password: 'new' })
  assert.equal(state.token, '')
  assert.equal(page.passwordForm.new_password, '')
  assert.equal(page.loading.value, false)
})

test('failed password change preserves inputs and always restores submit state', async () => {
  state.postError = { message: '旧密码验证错误！' }
  const page = setup(Profile)
  formRef(page)
  page.passwordForm.old_password = 'wrong'
  await page.updatePassword()
  assert.equal(page.errorMessage.value, '旧密码验证错误！')
  assert.equal(page.passwordForm.old_password, 'wrong')
  assert.equal(page.loading.value, false)
})

test('repeated login and password submits while pending send only one POST', async () => {
  for (const component of [Login, Profile]) {
    state.calls = []
    let release
    state.postWait = new Promise((resolve) => {
      release = resolve
    })
    const page = setup(component)
    formRef(page)
    const submit = page.handleLogin || page.updatePassword
    const pending = submit()
    await nextTick()
    await submit()
    assert.equal(state.calls.filter((call) => call.method === 'post').length, 1)
    release()
    await pending
    state.postWait = null
  }
})

test('Axios keeps the unified response and injects the existing token header only when needed', async () => {
  state.token = 'valid'
  assert.equal(reqResolve({ headers: {} }).headers.token, 'valid')
  assert.deepEqual(reqResolve({ noNeedToken: true, headers: {} }).headers, {})
  const body = { code: 200, data: [], total: 7 }
  assert.equal(await resResolve({ data: body, status: 200 }), body)
})

test('HTTP 401 and 2xx business 401 reject and clear the current session', async () => {
  for (const reject of [
    () => resResolve({ status: 200, data: { code: 401, msg: 'expired' }, config: {} }),
    () => resReject({ response: { status: 401, data: { detail: 'expired' } }, config: {} }),
  ]) {
    state.token = 'valid'
    await assert.rejects(reject())
    assert.equal(state.token, '')
  }
})

test('stale-token and public login failures never clear a newer authenticated session', async () => {
  state.token = 'new'
  await assert.rejects(
    resReject({ response: { status: 401, data: {} }, config: { headers: { token: 'old' } } })
  )
  assert.equal(state.token, 'new')
  await assert.rejects(
    resReject({ response: { status: 401, data: {} }, config: { noNeedToken: true } })
  )
  assert.equal(state.token, 'new')
})

test('network/backend errors reject with useful messages without retaining password configs', async () => {
  await assert.rejects(
    resReject({
      response: { status: 409, data: { code: 409, msg: 'Duplicate email' } },
      config: { data: 'password=secret' },
    }),
    (error) => error.message === 'Duplicate email' && !('error' in error) && !('config' in error)
  )
  await assert.rejects(
    resReject(new Error('Network Error')),
    (error) => error.message === 'Network Error'
  )
})

test('download responses preserve Blob payloads alongside normal JSON business responses', async () => {
  const blob = new Blob(['emoji_type,count\nHAPPY,2'], { type: 'text/csv' })
  assert.equal(
    await resResolve({ status: 200, data: blob, config: { responseType: 'blob' } }),
    blob
  )
  assert.equal(await resResolve({ status: 200, data: blob, config: {} }), blob)
  const body = { code: 200, data: [], total: 3 }
  assert.equal(await resResolve({ status: 200, data: body, config: {} }), body)
})

test('an unauthorized blob download still rejects and clears the current session', async () => {
  state.token = 'valid'
  await assert.rejects(
    resReject({
      response: { status: 401, data: new Blob(['Unauthorized']) },
      config: { responseType: 'blob', headers: { token: 'valid' } },
    })
  )
  assert.equal(state.token, '')
})

test('late userinfo cannot repopulate user state after logout or account replacement', async () => {
  state.token = 'old'
  state.userInfo = { id: 11, role_codes: ['TEACHER'], is_active: true }
  let release
  state.getWait = new Promise((resolve) => {
    release = resolve
  })
  const user = useUserStore()
  const pending = user.getUserInfo()
  await user.logout({ redirect: false })
  state.token = 'new'
  user.setUserInfo({ id: 22, role_codes: ['STUDENT'] })
  release()
  await assert.rejects(pending, /SESSION_CHANGED/)
  assert.equal(user.userId, 22)
  assert.equal(user.defaultPath, '/student/classroom')
})

test('late menu and permission responses cannot refill cleared access state', async () => {
  for (const action of ['generateRoutes', 'getAccessApis']) {
    state.token = 'old'
    let release
    state.getWait = new Promise((resolve) => {
      release = resolve
    })
    const permission = useActualPermissionStore()
    const pending = permission[action]()
    await useUserStore().logout({ redirect: false })
    state.token = 'new'
    release()
    await assert.rejects(pending, /SESSION_CHANGED/)
    assert.deepEqual(permission.accessRoutes, [])
    assert.deepEqual(permission.accessApis, [])
  }
})

test('production initialization does not install stale routes or log out a newer account', async () => {
  for (const fails of [false, true]) {
    state.token = 'old'
    let release
    let installed = false
    let signalMenuStarted
    const menuStarted = new Promise((resolve) => {
      signalMenuStarted = resolve
    })
    const wait = new Promise((resolve) => {
      release = resolve
    })
    const user = useUserStore()
    const pending = initializeSessionAccess(
      user,
      {
        async generateRoutes() {
          signalMenuStarted()
          await wait
          if (fails) throw new Error('late menu failure')
          return [{ path: '/old-user' }]
        },
        async getAccessApis() {},
      },
      () => {
        installed = true
      }
    )
    await menuStarted
    await user.logout({ redirect: false })
    state.token = 'new'
    user.setUserInfo({ id: 22 })
    release()
    await assert.rejects(pending)
    assert.equal(installed, false)
    assert.equal(state.token, 'new')
    assert.equal(user.userId, 22)
  }
})

test('a pending login cannot overwrite or clear a newer session', async () => {
  const page = setup(Login)
  formRef(page)
  page.form.username = 'old-user'
  page.form.password = 'secret'
  let release
  state.postWait = new Promise((resolve) => {
    release = resolve
  })
  const pending = page.handleLogin()
  await nextTick()
  await useUserStore().logout({ redirect: false })
  state.token = 'new'
  useUserStore().setUserInfo({ id: 22 })
  release()
  await pending
  assert.equal(state.token, 'new')
  assert.equal(useUserStore().userId, 22)
  assert.equal(page.loading.value, false)
  assert.equal(state.messages.includes('views.login.message_login_success'), false)
})

test('legacy secret removal survives storage write failures without crashing startup', () => {
  const values = new Map([['loginInfo', { username: 'student', password: 'secret' }]])
  clearLegacyPassword({
    get: (key) => values.get(key),
    remove: (key) => values.delete(key),
    set() {
      throw new Error('QuotaExceededError')
    },
  })
  assert.equal(values.has('loginInfo'), false)
  assert.doesNotThrow(() =>
    clearLegacyPassword({
      get() {
        throw new Error('SecurityError')
      },
      remove() {
        throw new Error('SecurityError')
      },
    })
  )
})

test('tag persistence failure cannot retain user, roles, menus or routes during logout', async () => {
  state.token = 'old'
  state.tagError = true
  const user = useUserStore()
  user.setUserInfo({ id: 11, role_codes: ['TEACHER'] })
  await assert.rejects(user.logout(), /QuotaExceededError/)
  assert.equal(state.token, '')
  assert.equal(user.userId, undefined)
  assert.equal(state.menuResetCount, 1)
  assert.equal(state.resetCount, 1)
  assert.equal(state.navigation.at(-1), '/login')
})

test('phase3 fixed emotion mapping and manual payload reject invalid IDs and AI values', async () => {
  assert.equal(EMOTIONS.length, 5)
  assert.deepEqual(manualEmojiPayload(12, 'HAPPY'), {
    session_id: 12,
    emoji_type: 'HAPPY',
    source: 'MANUAL',
  })
  for (const id of [null, -1, 0, 1.5, NaN]) assert.throws(() => manualEmojiPayload(id, 'HAPPY'))
  assert.throws(() => manualEmojiPayload(12, 'FAKE'))
  for (const value of [undefined, ['12'], '0', '-1', '1.5', '9007199254740993'])
    assert.equal(parseSessionId(value), null)
  assert.equal(parseSessionId('12'), 12)
  await api.submitManualEmoji(12, 'SAD')
  assert.deepEqual(state.calls[0].data, { session_id: 12, emoji_type: 'SAD', source: 'MANUAL' })
})

test('phase3 missing schedule capability makes no HTTP call or write', async () => {
  await assert.rejects(
    api.getMySessions({ user_id: 999 }),
    (error) => error.code === 'SCHEDULE_PENDING'
  )
  const page = setup(StudentClassroom)
  await page.submit()
  assert.equal(state.calls.length, 0)
})

test('phase3 current-user schedule and personal history never forward arbitrary user IDs', async () => {
  studentClassroomContract.path = '/fixture/current-sessions'
  let actual
  state.getHandler = async (path, config) => {
    actual = { path, ...config }
    return { data: [], total: 0 }
  }
  await api.getMySessions({ user_id: 999, page: 2 })
  assert.deepEqual(actual.params, { page: 2, page_size: 20 })
  await api.getMyEmojiHistory({ user_id: 999, session_id: 12 })
  assert.deepEqual(actual.params, {
    session_id: 12,
    from_time: undefined,
    to_time: undefined,
    page: 1,
    page_size: 20,
  })
})

test('phase3 remote lists distinguish empty/error and reject stale responses', async () => {
  let release
  const list = useBusinessList(async ({ id }) =>
    id === 1
      ? new Promise((resolve) => {
          release = resolve
        })
      : { data: [{ id }], total: 1 }
  )
  const pending = list.load({ id: 1 })
  await list.load({ id: 2 })
  release({ data: [{ id: 1 }], total: 1 })
  await pending
  assert.equal(list.rows.value[0].id, 2)
  list.clear()
  assert.deepEqual(list.rows.value, [])
  const empty = useBusinessList(async () => ({ data: [], total: 0 }))
  await empty.load()
  assert.equal(empty.error.value, '')
  const failed = useBusinessList(async () => {
    throw { code: 403, message: 'Forbidden' }
  })
  await failed.load()
  assert.equal(failed.error.value, 'Forbidden')
  assert.equal(failed.loading.value, false)
})

function studentFixture() {
  studentClassroomContract.path = '/fixture/current-sessions'
  const page = setup(StudentClassroom)
  page.list.rows = [{ id: 12, course_id: 4 }]
  page.sessionId.value = 12
  page.emoji.value = 'HAPPY'
  return page
}

test('phase3 student submits once while pending and reports controlled response success', async () => {
  const page = studentFixture()
  let release
  state.postHandler = () =>
    new Promise((resolve) => {
      release = resolve
    })
  const pending = page.submit()
  await page.submit()
  assert.equal(state.calls.filter((call) => call.method === 'post').length, 1)
  release({ code: 200, data: { id: 7 } })
  await pending
  assert.equal(page.success.value, true)
  assert.equal(page.submitting.value, false)
})

test('phase3 uncertain write preserves choices and never auto retries', async () => {
  const page = studentFixture()
  state.postHandler = async () => {
    throw { code: 'ECONNABORTED', message: 'timeout' }
  }
  await page.submit()
  await page.submit()
  assert.equal(page.uncertain.value, true)
  assert.equal(page.sessionId.value, 12)
  assert.equal(page.emoji.value, 'HAPPY')
  assert.equal(state.calls.filter((call) => call.method === 'post').length, 1)
})

test('phase3 removed schedule refreshes authorized list and clears selection', async () => {
  const page = studentFixture()
  state.postHandler = async () => {
    throw { code: 403, message: 'cancelled' }
  }
  state.getHandler = async () => ({ data: [], total: 0 })
  await page.submit()
  assert.equal(page.sessionId.value, null)
  assert.equal(page.list.rows.length, 0)
  assert.equal(page.submitting.value, false)
  assert.equal(page.uncertain.value, false)
  assert.ok(state.calls.some((call) => call.path === '/fixture/current-sessions'))
})

test('phase3 teacher direct detail checks ownership before requesting history', async () => {
  route.query = { session_id: '12' }
  state.getHandler = async (path) => {
    if (path === '/dashboard/realtime') throw { code: 403, message: 'Forbidden classroom' }
    throw new Error('must not query unauthorized history')
  }
  const page = setup(TeacherDetail)
  await page.load()
  assert.equal(page.classroom.value, null)
  assert.equal(page.error.value, 'Forbidden classroom')
  assert.equal(
    state.calls.some((call) => call.path === '/emoji'),
    false
  )
})

test('phase3 teacher direct detail loads allowed metadata and empty history without page cache', async () => {
  route.query = { session_id: '12' }
  state.getHandler = async (path, { params }) => {
    assert.equal(params.session_id, 12)
    if (path === '/dashboard/realtime')
      return {
        data: { found: true, forbidden: false, session: { id: 12, course_name: 'Fixture course' } },
      }
    if (path === '/emoji') return { data: [], total: 0 }
    if (path === '/emoji/statistics') return { data: [] }
    throw new Error('unexpected API')
  }
  const page = setup(TeacherDetail)
  await page.load()
  assert.equal(page.classroom.value.id, 12)
  assert.deepEqual(page.history.rows, [])
  assert.equal(page.history.error, '')
  assert.equal(page.statisticsError.value, '')
  assert.equal(page.loading.value, false)
})

test('phase3 history user labels preserve allowed username and explicitly mark anonymous AI', () => {
  assert.equal(recordUserLabel({ user_id: null, source: 'AI' }), '匿名')
  assert.equal(recordUserLabel({ user_id: 101, username: 'student' }), 'student')
  assert.equal(recordUserLabel({ user_id: 101 }), '用户 #101')
})

test('phase4 ranges retain Shanghai wall-clock endpoints and reject reversed ranges', () => {
  assert.deepEqual(historyRange(null), {})
  assert.deepEqual(historyRange(['2026-11-09 00:00:00', '2026-11-09 23:59:59']), {
    from_time: '2026-11-09 00:00:00',
    to_time: '2026-11-09 23:59:59',
  })
  for (const range of [
    [],
    ['2026-11-09', '2026-11-10'],
    ['2026-11-10 00:00:00', '2026-11-09 00:00:00'],
    ['2026-11-09T00:00:00Z', '2026-11-10T00:00:00Z'],
  ])
    assert.throws(() => historyRange(range))
})

test('phase4 server aggregate counts determine fixed-order zero-filled percentages', () => {
  const summary = normalizeStatistics([
    { emoji_type: 'SAD', count: 1, percentage: 99 },
    { emoji_type: 'HAPPY', count: 2 },
  ])
  assert.equal(summary.total, 3)
  assert.deepEqual(
    summary.rows.map((row) => row.value),
    EMOTIONS.map((row) => row.value)
  )
  assert.deepEqual(
    summary.rows.map((row) => row.percentage),
    [66.67, 33.33, 0, 0, 0]
  )
  assert.ok(normalizeStatistics([]).rows.every((row) => row.count === 0 && row.percentage === 0))
  for (const rows of [
    null,
    [{ emoji_type: 'HAPPY', count: -1 }],
    [{ emoji_type: 'HAPPY', count: 1.5 }],
    [{ emoji_type: 'FAKE', count: 1 }],
    [
      { emoji_type: 'SAD', count: 1 },
      { emoji_type: 'SAD', count: 2 },
    ],
  ])
    assert.throws(() => normalizeStatistics(rows))
})

test('phase4 student history filters reset page and never submit another user ID', async () => {
  let params
  state.getHandler = async (path, config) => {
    if (path === '/emoji/history') params = config.params
    return { data: [], total: 0 }
  }
  const page = setup(StudentHistory)
  page.page.value = 8
  page.selectedClass.value = 12
  page.draft.value.range = ['2026-11-09 10:00:00', '2026-11-09 11:00:00']
  await page.apply()
  assert.equal(page.page.value, 1)
  assert.deepEqual(params, {
    session_id: 12,
    from_time: '2026-11-09 10:00:00',
    to_time: '2026-11-09 11:00:00',
    page: 1,
    page_size: 20,
  })
  page.page.value = 2
  await page.load()
  assert.equal(params.page, 2)
  await page.reset()
  assert.equal(params.session_id, undefined)
  assert.equal(params.from_time, undefined)
  assert.equal(page.filtered.value, false)
  page.draft.value.range = ['bad', 'bad']
  const calls = state.calls.length
  await page.apply()
  assert.equal(state.calls.length, calls)
  assert.equal(page.filterError.value, 'history.invalidRange')
})

function teacherHistoryFixture(handler) {
  route.query = { session_id: '12' }
  state.getHandler = async (path, config) => {
    if (path === '/dashboard/realtime')
      return { data: { found: true, session: { id: config.params.session_id } } }
    return handler(path, config.params)
  }
  return setup(TeacherDetail)
}

test('phase4 teacher history and aggregate share filters while pagination only fetches history', async () => {
  const calls = []
  const page = teacherHistoryFixture(async (path, params) => {
    calls.push({ path, params })
    if (path === '/emoji/statistics') return { data: [{ emoji_type: 'HAPPY', count: 45 }] }
    return { data: [{ id: params.page, emoji_type: 'SAD' }], total: 45 }
  })
  await page.load()
  calls.length = 0
  page.page.value = 9
  page.draft.value = {
    range: ['2026-11-09 10:00:00', '2026-11-09 11:00:00'],
    user_id: 101,
    source: 'AI',
  }
  await page.apply()
  assert.equal(page.page.value, 1)
  const aggregate = calls.find((call) => call.path === '/emoji/statistics').params
  const history = calls.find((call) => call.path === '/emoji').params
  assert.deepEqual(aggregate, {
    session_id: 12,
    user_id: 101,
    source: 'AI',
    from_time: '2026-11-09 10:00:00',
    to_time: '2026-11-09 11:00:00',
  })
  assert.deepEqual(history, { ...aggregate, page: 1, page_size: 20 })
  assert.equal(page.summary.value.total, 45)
  assert.equal(page.summary.value.rows[0].percentage, 100)
  calls.length = 0
  page.page.value = 2
  await page.loadPage()
  assert.deepEqual(
    calls.map((call) => call.path),
    ['/emoji']
  )
  assert.equal(calls[0].params.page, 2)
  assert.equal(page.summary.value.total, 45)
})

test('phase4 late history and statistics cannot overwrite a newer filter or classroom', async () => {
  let releaseHistory, releaseStatistics
  let ready
  const started = new Promise((resolve) => {
    ready = resolve
  })
  const page = teacherHistoryFixture(async (path, params) => {
    if (params.source === 'MANUAL')
      return new Promise((resolve) => {
        if (path === '/emoji') releaseHistory = resolve
        else releaseStatistics = resolve
        if (releaseHistory && releaseStatistics) ready()
      })
    return path === '/emoji'
      ? { data: [{ id: 22 }], total: 1 }
      : { data: [{ emoji_type: 'SAD', count: 8 }] }
  })
  await page.load()
  page.draft.value.source = 'MANUAL'
  const pending = page.apply()
  await started
  assert.ok(releaseHistory && releaseStatistics)
  route.query = { session_id: '13' }
  page.draft.value.source = 'AI'
  await page.apply()
  releaseHistory({ data: [{ id: 11 }], total: 1 })
  releaseStatistics({ data: [{ emoji_type: 'HAPPY', count: 1000 }] })
  await pending
  assert.equal(page.classroom.value.id, 13)
  assert.equal(page.history.rows[0].id, 22)
  assert.equal(page.summary.value.total, 8)
  assert.equal(page.summary.value.rows[0].count, 0)
  assert.equal(page.statisticsLoading.value, false)
})

test('phase4 aggregate errors recover on refresh without hiding successful history', async () => {
  let fail = true
  const page = teacherHistoryFixture(async (path) => {
    if (path === '/emoji/statistics') {
      if (fail) throw { code: 403, message: 'Forbidden statistics' }
      return { data: [] }
    }
    return { data: [], total: 0 }
  })
  await page.load()
  assert.equal(page.statisticsError.value, 'Forbidden statistics')
  assert.equal(page.history.error, '')
  assert.equal(page.statisticsLoading.value, false)
  assert.equal(page.loading.value, false)
  fail = false
  await page.load()
  assert.equal(page.statisticsError.value, '')
  assert.equal(page.summary.value.total, 0)
  page.draft.value.user_id = 0
  await page.apply()
  assert.equal(page.filterError.value, 'history.invalidStudent')
  assert.equal(page.summary.value, null)
  assert.deepEqual(page.history.rows, [])
})
