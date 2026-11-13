<script setup>
import { h, onMounted, ref } from 'vue'
import {
  NButton,
  NDatePicker,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NTag,
} from 'naive-ui'

import CommonPage from '@/components/page/CommonPage.vue'
import QueryBarItem from '@/components/query-bar/QueryBarItem.vue'
import CrudModal from '@/components/table/CrudModal.vue'
import CrudTable from '@/components/table/CrudTable.vue'
import TheIcon from '@/components/icon/TheIcon.vue'
import { useUserStore } from '@/store'

import { formatDate, formatDateTime, renderIcon } from '@/utils'
import { useCRUD } from '@/composables'
import api from '@/api'
import BrowserClassroomPanel from '@/components/ai/BrowserClassroomPanel.vue'

defineOptions({ name: '课堂会话' })

const $table = ref(null)
const userStore = useUserStore()
const queryItems = ref({})
const aiSessionId = ref(null)
const aiVisible = ref(false)

const {
  modalVisible,
  modalTitle,
  modalAction,
  modalLoading,
  handleSave,
  modalForm,
  modalFormRef,
  handleDelete,
  handleAdd,
} = useCRUD({
  name: '课堂',
  initForm: { course_id: null, start_time: null, end_time: null, classroom: '', class_name: '' },
  doCreate: api.createSession,
  doUpdate: api.updateSession,
  doDelete: api.deleteSession,
  refresh: () => $table.value?.handleSearch(),
})

// 编辑时把数据库返回的时间（空格分隔）转换为 NDatePicker 需要的 ISO 格式。
function handleEdit(row) {
  modalAction.value = 'edit'
  modalVisible.value = true
  modalForm.value = {
    ...row,
    start_time: row.start_time ? row.start_time.replace(' ', 'T') : null,
    end_time: row.end_time ? row.end_time.replace(' ', 'T') : null,
  }
}

onMounted(() => {
  $table.value?.handleSearch()
})

const columns = [
  { title: 'ID', key: 'id', width: 60, align: 'center' },
  { title: '课程ID', key: 'course_id', width: 80, align: 'center' },
  {
    title: '开始时间',
    key: 'start_time',
    width: 180,
    align: 'center',
    render: (row) => formatDateTime(row.start_time),
  },
  {
    title: '结束时间',
    key: 'end_time',
    width: 180,
    align: 'center',
    render: (row) => formatDateTime(row.end_time),
  },
  { title: '教室', key: 'classroom', width: 100, align: 'center', ellipsis: { tooltip: true } },
  { title: '班级', key: 'class_name', width: 120, align: 'center', ellipsis: { tooltip: true } },
  {
    title: '操作',
    key: 'actions',
    width: 220,
    align: 'center',
    fixed: 'right',
    render(row) {
      return [
        h(NButton, {
          size: 'small', style: 'margin-right: 8px;',
          onClick: () => { aiSessionId.value = row.id; aiVisible.value = true },
        }, { default: () => 'AI采集' }),
        h(
          NButton,
          {
            size: 'small',
            type: 'primary',
            style: 'margin-right: 8px;',
            onClick: () => handleEdit(row),
          },
          { default: () => '编辑', icon: renderIcon('material-symbols:edit', { size: 16 }) }
        ),
        h(
          NButton,
          {
            size: 'small',
            type: 'info',
            style: 'margin-right: 8px;',
            onClick: () => openSchedule(row),
          },
          { default: () => '排课', icon: renderIcon('carbon:calendar', { size: 16 }) }
        ),
        userStore.isAdministrator
          ? h(
              NPopconfirm,
              { onPositiveClick: () => handleDelete({ session_id: row.id }) },
              {
                trigger: () =>
                  h(
                    NButton,
                    { size: 'small', type: 'error' },
                    {
                      default: () => '删除',
                      icon: renderIcon('material-symbols:delete-outline', { size: 16 }),
                    }
                  ),
                default: () => h('div', {}, '确定删除该课堂会话吗?'),
              }
            )
          : null,
      ].filter(Boolean)
    },
  },
]

const rules = {
  course_id: [
    { required: true, type: 'number', message: '请输入课程ID', trigger: ['input', 'blur'] },
  ],
  start_time: [{ required: true, message: '请选择开始时间', trigger: ['blur', 'change'] }],
  end_time: [{ required: true, message: '请选择结束时间', trigger: ['blur', 'change'] }],
}

// 排课弹窗
const scheduleVisible = ref(false)
const scheduleLoading = ref(false)
const currentSessionId = ref(null)
const scheduledUsers = ref([])
const newUserId = ref(null)

async function openSchedule(row) {
  currentSessionId.value = row.id
  scheduleVisible.value = true
  newUserId.value = null
  await loadScheduledUsers()
}

async function loadScheduledUsers() {
  scheduleLoading.value = true
  try {
    const res = await api.getScheduledUsers(currentSessionId.value)
    scheduledUsers.value = res.data || []
  } catch (error) {
    scheduledUsers.value = []
  } finally {
    scheduleLoading.value = false
  }
}

async function handleAddSchedule() {
  if (!newUserId.value) {
    $message.warning('请输入学生用户ID（教师不可排课）')
    return
  }
  try {
    await api.scheduleUser(currentSessionId.value, { user_id: newUserId.value })
    $message.success('安排成功')
    newUserId.value = null
    await loadScheduledUsers()
  } catch (error) {
    $message.error(error.message || '安排失败')
  }
}

async function handleRemoveSchedule(userId) {
  try {
    await api.unscheduleUser(currentSessionId.value, userId)
    $message.success('已取消安排')
    await loadScheduledUsers()
  } catch (error) {
    $message.error(error.message || '取消失败')
  }
}
</script>

<template>
  <CommonPage show-footer title="课堂会话">
    <template #action>
      <NButton type="primary" @click="handleAdd">
        <TheIcon icon="material-symbols:add" :size="18" class="mr-5" />新建课堂
      </NButton>
    </template>

    <CrudTable
      ref="$table"
      v-model:query-items="queryItems"
      :columns="columns"
      :get-data="api.getSessions"
    >
      <template #queryBar>
        <QueryBarItem label="课程ID" :label-width="70">
          <NInputNumber
            v-model:value="queryItems.course_id"
            clearable
            placeholder="按课程ID筛选"
            @keypress.enter="$table?.handleSearch()"
          />
        </QueryBarItem>
      </template>
    </CrudTable>

    <CrudModal
      v-model:visible="modalVisible"
      :title="modalTitle"
      :loading="modalLoading"
      @save="handleSave"
    >
      <NForm
        ref="modalFormRef"
        label-placement="left"
        :label-width="80"
        :model="modalForm"
        :rules="rules"
      >
        <NFormItem label="课程ID" path="course_id">
          <NInputNumber v-model:value="modalForm.course_id" clearable placeholder="请输入课程ID" />
        </NFormItem>
        <NFormItem label="开始时间" path="start_time">
          <NDatePicker
            v-model:formatted-value="modalForm.start_time"
            type="datetime"
            value-format="yyyy-MM-dd'T'HH:mm:ss"
            clearable
            placeholder="请选择开始时间"
          />
        </NFormItem>
        <NFormItem label="结束时间" path="end_time">
          <NDatePicker
            v-model:formatted-value="modalForm.end_time"
            type="datetime"
            value-format="yyyy-MM-dd'T'HH:mm:ss"
            clearable
            placeholder="请选择结束时间"
          />
        </NFormItem>
        <NFormItem label="教室" path="classroom">
          <NInput v-model:value="modalForm.classroom" clearable placeholder="请输入教室" />
        </NFormItem>
        <NFormItem label="班级" path="class_name">
          <NInput v-model:value="modalForm.class_name" clearable placeholder="请输入班级" />
        </NFormItem>
      </NForm>
    </CrudModal>

    <NModal v-model:show="scheduleVisible" preset="card" title="课堂排课" style="width: 600px">
      <div mb-15 flex items-center gap-10>
        <NInputNumber
          v-model:value="newUserId"
          clearable
          placeholder="输入要安排的用户ID"
          style="width: 200px"
        />
        <NButton type="primary" @click="handleAddSchedule">安排用户</NButton>
      </div>
      <div v-if="scheduleLoading">加载中...</div>
      <div v-else-if="scheduledUsers.length === 0">暂无已安排用户</div>
      <div v-else>
        <div v-for="item in scheduledUsers" :key="item.id" flex items-center justify-between py-5>
          <NTag type="info">#{{ item.user_id }} {{ item.username || '匿名用户' }}</NTag>
          <span text-12 op-60>{{ formatDate(item.scheduled_at) }}</span>
          <NButton size="tiny" type="error" @click="handleRemoveSchedule(item.user_id)"
            >移除</NButton
          >
        </div>
      </div>
    </NModal>
    <NModal v-model:show="aiVisible" preset="card" title="课堂 AI 采集" style="width: min(1100px, 95vw)">
      <BrowserClassroomPanel v-if="aiVisible" :key="aiSessionId" :session-id="aiSessionId" />
    </NModal>
  </CommonPage>
</template>
