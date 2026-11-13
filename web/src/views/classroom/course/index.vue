<script setup>
import { h, onMounted, ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, NInputNumber, NPopconfirm } from 'naive-ui'

import CommonPage from '@/components/page/CommonPage.vue'
import QueryBarItem from '@/components/query-bar/QueryBarItem.vue'
import CrudModal from '@/components/table/CrudModal.vue'
import CrudTable from '@/components/table/CrudTable.vue'
import TheIcon from '@/components/icon/TheIcon.vue'

import { formatDate, renderIcon } from '@/utils'
import { useCRUD } from '@/composables'
import api from '@/api'
import { useUserStore } from '@/store'

defineOptions({ name: '课程管理' })

const $table = ref(null)
const userStore = useUserStore()
const queryItems = ref({})

const {
  modalVisible,
  modalTitle,
  modalLoading,
  handleSave,
  modalForm,
  modalFormRef,
  handleEdit,
  handleDelete,
  handleAdd,
} = useCRUD({
  name: '课程',
  initForm: { name: '', teacher_id: null, description: '' },
  doCreate: api.createCourse,
  doUpdate: api.updateCourse,
  doDelete: api.deleteCourse,
  refresh: () => $table.value?.handleSearch(),
})

onMounted(() => {
  $table.value?.handleSearch()
})

const columns = [
  { title: 'ID', key: 'id', width: 60, align: 'center' },
  { title: '课程名称', key: 'name', align: 'center', ellipsis: { tooltip: true } },
  { title: '教师ID', key: 'teacher_id', width: 80, align: 'center' },
  { title: '课程描述', key: 'description', align: 'center', ellipsis: { tooltip: true } },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    align: 'center',
    render(row) {
      return formatDate(row.created_at)
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    align: 'center',
    fixed: 'right',
    render(row) {
      return [
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
        userStore.isAdministrator
          ? h(
              NPopconfirm,
              { onPositiveClick: () => handleDelete({ course_id: row.id }) },
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
                default: () => h('div', {}, '确定删除该课程吗?'),
              }
            )
          : null,
      ].filter(Boolean)
    },
  },
]

const rules = {
  name: [{ required: true, message: '请输入课程名称', trigger: ['input', 'blur'] }],
  teacher_id: [
    { required: true, type: 'number', message: '请输入教师ID', trigger: ['input', 'blur'] },
  ],
}
</script>

<template>
  <CommonPage show-footer title="课程管理">
    <template #action>
      <NButton type="primary" @click="handleAdd">
        <TheIcon icon="material-symbols:add" :size="18" class="mr-5" />新建课程
      </NButton>
    </template>

    <CrudTable
      ref="$table"
      v-model:query-items="queryItems"
      :columns="columns"
      :get-data="api.getCourses"
    >
      <template #queryBar>
        <QueryBarItem label="课程名称" :label-width="70">
          <NInput
            v-model:value="queryItems.keyword"
            clearable
            placeholder="请输入课程名称"
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
        <NFormItem label="课程名称" path="name">
          <NInput v-model:value="modalForm.name" clearable placeholder="请输入课程名称" />
        </NFormItem>
        <NFormItem label="教师ID" path="teacher_id">
          <NInputNumber v-model:value="modalForm.teacher_id" clearable placeholder="请输入教师ID" />
        </NFormItem>
        <NFormItem label="课程描述" path="description">
          <NInput
            v-model:value="modalForm.description"
            type="textarea"
            placeholder="请输入课程描述"
          />
        </NFormItem>
      </NForm>
    </CrudModal>
  </CommonPage>
</template>
