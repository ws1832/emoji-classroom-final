<template>
  <CommonPage :title="t('auth.account')">
    <n-alert
      v-if="!userStore.businessRoles.length && !userStore.isAdministrator"
      type="info"
      mb-20
      :title="t('auth.pendingTitle')"
    >
      {{ t('auth.rolesPending') }}
    </n-alert>
    <n-space vertical :size="20">
      <p>{{ t('auth.welcome', { username: userStore.name }) }}</p>
      <n-space>
        <n-button
          v-for="role in userStore.businessRoles"
          :key="role"
          type="primary"
          @click="enter(role)"
        >
          {{ t(role === 'STUDENT' ? 'auth.studentEntry' : 'auth.teacherEntry') }}
        </n-button>
        <n-button v-if="userStore.isAdministrator" @click="router.push('/classroom/dashboard')">管理工作台</n-button>
        <n-button @click="router.push('/profile')">{{
          t('views.profile.label_change_password')
        }}</n-button>
      </n-space>
    </n-space>
  </CommonPage>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import CommonPage from '@/components/page/CommonPage.vue'
import { useUserStore } from '@/store'
import { BUSINESS_HOMES } from '@/utils/auth/business'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()
async function enter(role) {
  try {
    if (userStore.switchBusinessRole(role)) await router.push(BUSINESS_HOMES[role])
  } catch {
    $message.error(t('auth.requestFailed'))
  }
}
</script>
