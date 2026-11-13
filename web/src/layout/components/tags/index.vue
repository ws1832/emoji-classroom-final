<template>
  <ScrollX ref="scrollXRef" class="bg-white dark:bg-dark!">
    <n-tag
      v-for="tag in tagsStore.tags"
      ref="tabRefs"
      :key="tag.path"
      class="mx-5 cursor-pointer rounded-4 px-15 hover:color-primary"
      :type="tagsStore.activeTag === tag.path ? 'primary' : 'default'"
      :closable="tagsStore.tags.length > 1"
      @click="handleTagClick(tag.path)"
      @close.stop="tagsStore.removeTag(tag.path)"
      @contextmenu.prevent="handleContextMenu($event, tag)"
    >
      {{ tag.title }}
    </n-tag>
    <ContextMenu
      v-if="contextMenuOption.show"
      v-model:show="contextMenuOption.show"
      :current-path="contextMenuOption.currentPath"
      :x="contextMenuOption.x"
      :y="contextMenuOption.y"
    />
  </ScrollX>
</template>

<script setup>
import ContextMenu from './ContextMenu.vue'
import { useTagsStore, useUserStore } from '@/store'
import { filterBusinessMenus } from '@/utils/auth/business'
import ScrollX from '@/components/common/ScrollX.vue'

const route = useRoute()
const router = useRouter()
const tagsStore = useTagsStore()
const userStore = useUserStore()
const tabRefs = ref([])
const scrollXRef = ref(null)

const contextMenuOption = reactive({
  show: false,
  x: 0,
  y: 0,
  currentPath: '',
})

// 更新后的身份不能继续显示旧门户标签（例如管理员曾是课程教师）。
watch(
  () => userStore.userInfo,
  (user) => {
    const allowed = filterBusinessMenus(tagsStore.tags, user)
    if (allowed.length !== tagsStore.tags.length) tagsStore.setTags(allowed)
  },
  { immediate: true },
)

watch(
  () => route.path,
  () => {
    const { name, fullPath: path } = route
    const title = route.meta?.title
    tagsStore.addTag({ name, path, title })
  },
  { immediate: true },
)

watch(
  () => tagsStore.activeIndex,
  async (activeIndex) => {
    await nextTick()
    const activeTabElement = tabRefs.value[activeIndex]?.$el
    if (!activeTabElement) return
    const { offsetLeft: x, offsetWidth: width } = activeTabElement
    scrollXRef.value?.handleScroll(x + width, width)
  },
  { immediate: true },
)

const handleTagClick = (path) => {
  tagsStore.setActiveTag(path)
  router.push(path)
}

function showContextMenu() {
  contextMenuOption.show = true
}
function hideContextMenu() {
  contextMenuOption.show = false
}
function setContextMenu(x, y, currentPath) {
  Object.assign(contextMenuOption, { x, y, currentPath })
}

// 右击菜单
async function handleContextMenu(e, tagItem) {
  const { clientX, clientY } = e
  hideContextMenu()
  setContextMenu(clientX, clientY, tagItem.path)
  await nextTick()
  showContextMenu()
}
</script>

<style>
.n-tag__close {
  box-sizing: content-box;
  border-radius: 50%;
  font-size: 12px;
  padding: 2px;
  transform: scale(0.9);
  transform: translateX(5px);
  transition: all 0.3s;
}
</style>
