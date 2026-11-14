<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  NButton,
  NCard,
  NDatePicker,
  NEmpty,
  NGrid,
  NGridItem,
  NInput,
  NProgress,
  NSelect,
  NStatistic,
} from 'naive-ui'

import CommonPage from '@/components/page/CommonPage.vue'
import api from '@/api'
import { useUserStore } from '@/store'
const userStore = useUserStore()

defineOptions({ name: '多维统计' })

const EMOJI_MAP = {
  HAPPY: '😊',
  SAD: '😢',
  ANGRY: '😠',
  SURPRISED: '😲',
  NEUTRAL: '😐',
}

const courseOptions = ref([])
const filters = ref({ course_id: null, class_name: '', from_time: null, to_time: null })
const statisticsData = ref(null)
const loading = ref(false)

async function loadCourses() {
  const res = await api.getCourses({ page: 1, page_size: 100 })
  courseOptions.value = (res.data || []).map((item) => ({ label: `#${item.id} ${item.name}`, value: item.id }))
}

async function loadStatistics() {
  loading.value = true
  try {
    const params = {}
    Object.entries(filters.value).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        params[key] = value
      }
    })
    const res = await api.getStatistics(params)
    statisticsData.value = res.data
  } catch (error) {
    statisticsData.value = null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadCourses()
  await loadStatistics()
})

const maxByCourse = computed(() => Math.max(1, ...(statisticsData.value?.by_course || []).map((i) => i.count)))
const maxByClass = computed(() => Math.max(1, ...(statisticsData.value?.by_class || []).map((i) => i.count)))
const maxByDay = computed(() => Math.max(1, ...(statisticsData.value?.by_day || []).map((i) => i.count)))
const maxByHour = computed(() => Math.max(1, ...(statisticsData.value?.by_hour || []).map((i) => i.count)))
</script>

<template>
  <CommonPage show-footer :title="userStore.isAdministrator ? '全部课程 · 多维统计' : '所授课程 · 多维统计'">
    <div mb-15 flex items-center gap-15 flex-wrap>
      <NSelect v-model:value="filters.course_id" clearable :options="courseOptions" placeholder="按课程筛选" style="width: 200px" />
      <NInput v-model:value="filters.class_name" clearable placeholder="按班级筛选" style="width: 160px" />
      <NDatePicker
        v-model:formatted-value="filters.from_time"
        type="datetime"
        value-format="yyyy-MM-dd'T'HH:mm:ss"
        clearable
        placeholder="开始时间"
        style="width: 200px"
      />
      <NDatePicker
        v-model:formatted-value="filters.to_time"
        type="datetime"
        value-format="yyyy-MM-dd'T'HH:mm:ss"
        clearable
        placeholder="结束时间"
        style="width: 200px"
      />
      <NButton type="primary" :loading="loading" @click="loadStatistics">查询</NButton>
    </div>

    <NEmpty v-if="!statisticsData" description="暂无统计数据" />

    <template v-else>
      <NGrid :cols="4" :x-gap="12" :y-gap="12">
        <NGridItem>
          <NCard size="small"><NStatistic label="总记录数" :value="statisticsData.overview.total_records" /></NCard>
        </NGridItem>
        <NGridItem>
          <NCard size="small"><NStatistic label="参与学生数" :value="statisticsData.overview.total_students" /></NCard>
        </NGridItem>
        <NGridItem>
          <NCard size="small"><NStatistic label="手动记录" :value="statisticsData.overview.manual_records" /></NCard>
        </NGridItem>
        <NGridItem>
          <NCard size="small"><NStatistic label="AI 记录" :value="statisticsData.overview.ai_records" /></NCard>
        </NGridItem>
      </NGrid>

      <NCard title="情绪类型分布" size="small" mt-15>
        <div v-for="item in statisticsData.by_type" :key="item.emoji_type" flex items-center gap-10 py-6>
          <span w-120>{{ EMOJI_MAP[item.emoji_type] || '' }} {{ item.emoji_type }}</span>
          <NProgress type="line" :percentage="item.percentage" :height="18" indicator-placement="inside" flex-1 />
          <span w-100 text-right>{{ item.count }} 条 ({{ item.percentage }}%)</span>
        </div>
      </NCard>

      <NGrid :cols="2" :x-gap="12" mt-15>
        <NGridItem>
          <NCard title="按课程统计" size="small">
            <div v-for="item in statisticsData.by_course" :key="item.course_id" flex items-center gap-10 py-6>
              <span w-180 ellipsis>{{ item.course_name }}</span>
              <div h-18 flex-1 rounded-4 bg="#f0f0f0" overflow-hidden>
                <div
                  :style="{ width: `${(item.count / maxByCourse) * 100}%` }"
                  h-full
                  rounded-4
                  bg="#18a058"
                ></div>
              </div>
              <span w-60 text-right>{{ item.count }}</span>
            </div>
          </NCard>
        </NGridItem>
        <NGridItem>
          <NCard title="按班级统计" size="small">
            <div v-for="item in statisticsData.by_class" :key="item.class_name" flex items-center gap-10 py-6>
              <span w-180 ellipsis>{{ item.class_name }}</span>
              <div h-18 flex-1 rounded-4 bg="#f0f0f0" overflow-hidden>
                <div
                  :style="{ width: `${(item.count / maxByClass) * 100}%` }"
                  h-full
                  rounded-4
                  bg="#f0a020"
                ></div>
              </div>
              <span w-60 text-right>{{ item.count }}</span>
            </div>
          </NCard>
        </NGridItem>
      </NGrid>

      <NCard title="记录来源分布" size="small" mt-15>
        <div v-for="item in statisticsData.by_source" :key="item.source" flex items-center gap-10 py-6>
          <span w-120>{{ item.source === 'AI' ? 'AI 推理' : '手动提交' }}</span>
          <NProgress type="line" :percentage="item.percentage" :height="18" indicator-placement="inside" flex-1 />
          <span w-100 text-right>{{ item.count }} 条 ({{ item.percentage }}%)</span>
        </div>
      </NCard>

      <NCard title="按天趋势" size="small" mt-15>
        <div flex items-end gap-4 h-120>
          <div v-for="item in statisticsData.by_day" :key="item.day" flex flex-col items-center flex-1>
            <span text-12>{{ item.count }}</span>
            <div :style="{ height: `${(item.count / maxByDay) * 80}px` }" w-full max-w-40 rounded-t-4 bg="#2080f0"></div>
            <span text-10 op-60 mt-4>{{ item.day.slice(5) }}</span>
          </div>
        </div>
      </NCard>

      <NCard title="按小时趋势" size="small" mt-15>
        <div flex items-end gap-4 h-120>
          <div v-for="item in statisticsData.by_hour" :key="item.hour" flex flex-col items-center flex-1>
            <span text-12>{{ item.count }}</span>
            <div
              :style="{ height: `${(item.count / maxByHour) * 80}px` }"
              w-full
              max-w-40
              rounded-t-4
              bg="#d03050"
            ></div>
            <span text-10 op-60 mt-4>{{ item.hour }}</span>
          </div>
        </div>
      </NCard>
    </template>
  </CommonPage>
</template>
