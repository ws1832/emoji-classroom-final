import i18n from '~/i18n'
import { useUserStore } from '@/store/modules/user'
import Layout from '@/layout/index.vue'
const { t } = i18n.global

export const basicRoutes = [
  {
    name: 'Account',
    path: '/account',
    component: Layout,
    isHidden: true,
    children: [
      {
        path: '',
        name: 'AccountHome',
        component: () => import('@/views/account/index.vue'),
        meta: { title: t('auth.account') },
      },
    ],
  },
  {
    name: 'StudentSend',
    path: '/student/classroom',
    component: Layout,
    meta: {
      title: t('auth.studentSend'),
      businessRole: 'STUDENT',
      icon: 'mdi:emoticon-happy-outline',
      order: 2,
    },
    children: [
      {
        path: '',
        name: 'StudentSendHome',
        component: () => import('@/views/student/classroom/index.vue'),
        meta: { title: t('auth.studentSend'), businessRole: 'STUDENT' },
      },
    ],
  },
  {
    name: 'StudentHistory',
    path: '/student/history',
    component: Layout,
    meta: {
      title: t('auth.studentHistory'),
      businessRole: 'STUDENT',
      icon: 'mdi:history',
      order: 3,
    },
    children: [
      {
        path: '',
        name: 'StudentHistoryHome',
        component: () => import('@/views/student/history/index.vue'),
        meta: { title: t('auth.studentHistory'), businessRole: 'STUDENT' },
      },
    ],
  },
  {
    name: 'TeacherClassroom',
    path: '/teacher/classroom',
    component: Layout,
    meta: {
      title: t('auth.teacherClassroom'),
      businessRole: 'TEACHER',
      icon: 'mdi:school-outline',
      order: 2,
    },
    children: [
      {
        path: '',
        name: 'TeacherClassroomHome',
        component: () => import('@/views/teacher/classroom/index.vue'),
        meta: { title: t('auth.teacherClassroom'), businessRole: 'TEACHER' },
      },
    ],
  },
  {
    name: 'TeacherClassroomDetailLayout',
    path: '/teacher/classroom/detail',
    component: Layout,
    isHidden: true,
    meta: { businessRole: 'TEACHER' },
    children: [
      {
        path: '',
        name: 'TeacherClassroomDetail',
        component: () => import('@/views/teacher/classroom-detail/index.vue'),
        meta: { title: t('history.teacherTitle'), businessRole: 'TEACHER' },
      },
    ],
  },
  {
    path: '/',
    redirect: () => useUserStore().defaultPath,
    meta: { order: 0 },
  },
  {
    name: t('views.profile.label_profile'),
    path: '/profile',
    component: Layout,
    isHidden: true,
    children: [
      {
        path: '',
        component: () => import('@/views/profile/index.vue'),
        name: `${t('views.profile.label_profile')}Default`,
        meta: {
          title: t('views.profile.label_profile'),
          icon: 'user',
          affix: true,
        },
      },
    ],
    meta: { order: 99 },
  },
  {
    name: 'ErrorPage',
    path: '/error-page',
    component: Layout,
    redirect: '/error-page/404',
    isHidden: true,
    meta: {
      title: t('views.errors.label_error'),
      icon: 'mdi:alert-circle-outline',
      order: 99,
    },
    children: [
      {
        name: 'ERROR-401',
        path: '401',
        component: () => import('@/views/error-page/401.vue'),
        meta: {
          title: '401',
          icon: 'material-symbols:authenticator',
        },
      },
      {
        name: 'ERROR-403',
        path: '403',
        component: () => import('@/views/error-page/403.vue'),
        meta: {
          title: '403',
          icon: 'solar:forbidden-circle-line-duotone',
        },
      },
      {
        name: 'ERROR-404',
        path: '404',
        component: () => import('@/views/error-page/404.vue'),
        meta: {
          title: '404',
          icon: 'tabler:error-404',
        },
      },
      {
        name: 'ERROR-500',
        path: '500',
        component: () => import('@/views/error-page/500.vue'),
        meta: {
          title: '500',
          icon: 'clarity:rack-server-outline-alerted',
        },
      },
    ],
  },
  {
    name: '403',
    path: '/403',
    component: () => import('@/views/error-page/403.vue'),
    isHidden: true,
  },
  {
    name: '404',
    path: '/404',
    component: () => import('@/views/error-page/404.vue'),
    isHidden: true,
  },
  {
    name: 'Login',
    path: '/login',
    component: () => import('@/views/login/index.vue'),
    isHidden: true,
    meta: {
      title: '登录页',
    },
  },
  {
    name: 'Register',
    path: '/register',
    component: () => import('@/views/register/index.vue'),
    isHidden: true,
    meta: { title: t('auth.register') },
  },
]

export const NOT_FOUND_ROUTE = {
  name: 'NotFound',
  path: '/:pathMatch(.*)*',
  redirect: '/404',
  isHidden: true,
}

export const EMPTY_ROUTE = {
  name: 'Empty',
  path: '/:pathMatch(.*)*',
  component: null,
}

const modules = import.meta.glob('@/views/**/route.js', { eager: true })
const asyncRoutes = []
Object.keys(modules).forEach((key) => {
  asyncRoutes.push(modules[key].default)
})

// 加载 views 下每个模块的 index.vue 文件
const vueModules = import.meta.glob('@/views/**/index.vue')

export { asyncRoutes, vueModules }
