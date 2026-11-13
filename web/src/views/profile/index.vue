<script setup>
import { useI18n } from 'vue-i18n'
import CommonPage from '@/components/page/CommonPage.vue'
import { useUserStore } from '@/store'
import api from '@/api'
import { samePassword } from '@/utils/auth/forms'

const { t } = useI18n()
const userStore = useUserStore()
const loading = ref(false)
const errorMessage = ref('')
const passwordFormRef = ref(null)
const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const rules = computed(() => ({
  old_password: { required: true, message: t('auth.required'), trigger: ['blur', 'input'] },
  new_password: { required: true, message: t('auth.required'), trigger: ['blur', 'input'] },
  confirm_password: [
    { required: true, message: t('auth.required'), trigger: ['blur', 'input'] },
    {
      validator: (_, value) => samePassword(passwordForm.new_password, value),
      message: t('auth.passwordMismatch'),
      trigger: ['blur', 'input'],
    },
  ],
}))
watch(
  () => passwordForm.new_password,
  () => passwordFormRef.value?.restoreValidation()
)

async function updatePassword() {
  if (loading.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    await passwordFormRef.value.validate()
    const res = await api.updatePassword(passwordForm)
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
    passwordFormRef.value.restoreValidation()
    $message.success(res.msg || t('auth.passwordChanged'))
    await userStore.logout()
  } catch (error) {
    if (!Array.isArray(error)) errorMessage.value = error?.message || t('auth.requestFailed')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <CommonPage :title="t('auth.account')">
    <n-tabs type="line" animated default-value="password">
      <n-tab-pane name="password" :tab="t('views.profile.label_change_password')">
        <n-form
          ref="passwordFormRef"
          class="max-w-500 py-15"
          :model="passwordForm"
          :rules="rules"
          :disabled="loading"
          @submit.prevent="updatePassword"
        >
          <n-form-item :label="t('views.profile.label_old_password')" path="old_password">
            <n-input
              v-model:value="passwordForm.old_password"
              type="password"
              autocomplete="current-password"
              show-password-on="click"
            />
          </n-form-item>
          <n-form-item :label="t('views.profile.label_new_password')" path="new_password">
            <n-input
              v-model:value="passwordForm.new_password"
              type="password"
              autocomplete="new-password"
              show-password-on="click"
            />
          </n-form-item>
          <n-form-item :label="t('views.profile.label_confirm_password')" path="confirm_password">
            <n-input
              v-model:value="passwordForm.confirm_password"
              type="password"
              autocomplete="new-password"
              show-password-on="click"
            />
          </n-form-item>
          <p mb-15 op-60>{{ t('auth.passwordPolicy') }}</p>
          <n-alert v-if="errorMessage" type="error" mb-15>{{ errorMessage }}</n-alert>
          <n-button attr-type="submit" type="primary" :loading="loading" :disabled="loading">{{
            t('common.buttons.update')
          }}</n-button>
        </n-form>
      </n-tab-pane>
      <n-tab-pane name="info" :tab="t('header.label_profile')">
        <n-descriptions :column="1" label-placement="left" bordered>
          <n-descriptions-item :label="t('auth.username')">{{
            userStore.name
          }}</n-descriptions-item>
          <n-descriptions-item :label="t('auth.email')">{{ userStore.email }}</n-descriptions-item>
        </n-descriptions>
      </n-tab-pane>
    </n-tabs>
  </CommonPage>
</template>
