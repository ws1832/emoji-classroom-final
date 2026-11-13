import { defineStore } from 'pinia'
import { resetRouter } from '@/router'
import { useTagsStore, usePermissionStore } from '@/store'
import { removeToken, toLogin } from '@/utils'
import api from '@/api'
import { getBusinessRoles, getDefaultPath, isAdministrator } from '@/utils/auth/business'
import { captureSession, assertCurrentSession, invalidateSession } from '@/utils/auth/session'

export const useUserStore = defineStore('user', {
  state() {
    return {
      userInfo: {},
      activeBusinessRole: '',
    }
  },
  getters: {
    userId() {
      return this.userInfo?.id
    },
    name() {
      return this.userInfo?.username
    },
    email() {
      return this.userInfo?.email
    },
    avatar() {
      return this.userInfo?.avatar
    },
    role() {
      return this.userInfo?.roles || []
    },
    businessRoles() {
      return getBusinessRoles(this.userInfo)
    },
    defaultPath() {
      return getDefaultPath(this.userInfo, this.activeBusinessRole)
    },
    isSuperUser() {
      return this.userInfo?.is_superuser
    },
    isAdministrator() {
      return isAdministrator(this.userInfo)
    },
    isActive() {
      return this.userInfo?.is_active
    },
  },
  actions: {
    async getUserInfo() {
      const session = captureSession()
      const { data } = await api.getUserInfo()
      assertCurrentSession(session)
      if (!data?.id || data.is_active === false) throw new Error('USER_INFO_UNAVAILABLE')
      const { id, username, email, avatar, roles, role_codes, is_superuser, is_active, is_admin } = data
      this.userInfo = { id, username, email, avatar, roles, role_codes, is_superuser, is_active, is_admin }
      if (!this.businessRoles.includes(this.activeBusinessRole)) this.activeBusinessRole = ''
      return this.userInfo
    },
    async logout({ redirect = true } = {}) {
      invalidateSession()
      const { resetTags } = useTagsStore()
      const { resetPermission } = usePermissionStore()
      removeToken()
      try {
        resetTags()
      } finally {
        resetPermission()
        resetRouter()
        this.$reset()
        if (redirect) await toLogin()
      }
    },
    switchBusinessRole(role) {
      if (!this.businessRoles.includes(role)) return false
      this.activeBusinessRole = role
      return true
    },
    setUserInfo(userInfo = {}) {
      this.userInfo = { ...this.userInfo, ...userInfo }
    },
  },
})
