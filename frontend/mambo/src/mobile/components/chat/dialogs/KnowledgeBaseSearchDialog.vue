<!-- KnowledgeBaseSearchDialog.vue — 移动端知识库搜索 -->
<template>
  <div class="kb-search">
    <!-- KB 选择 & 搜索 -->
    <div class="kb-toolbar">
      <div class="kb-picker" @click="showKbPicker = !showKbPicker">
        <el-icon :size="16"><Collection /></el-icon>
        <span class="kb-picker-label">{{ selectedKbName || '选择知识库' }}</span>
        <el-icon :size="14" class="picker-arrow"><ArrowDown /></el-icon>
        <Transition name="fade">
          <div v-if="showKbPicker" class="kb-picker-list">
            <button
              v-for="kb in kbList"
              :key="kb.id"
              class="kb-picker-item"
              :class="{ active: selectedKbId === kb.id }"
              @click.stop="selectedKbId = kb.id; showKbPicker = false"
            >{{ kb.name }}</button>
          </div>
        </Transition>
      </div>

      <div class="search-row">
        <div class="search-input-wrap">
          <el-icon :size="16" class="search-icon"><Search /></el-icon>
          <input
            v-model="queryText"
            :placeholder="$t('kb.search.inputPlaceholder')"
            class="search-input"
            @keyup.enter="handleSearch"
          />
        </div>
        <button class="search-btn" @click="handleSearch" :disabled="isSearching">
          <el-icon v-if="!isSearching" :size="18"><Search /></el-icon>
          <el-icon v-else :size="18" class="is-loading"><Loading /></el-icon>
        </button>
      </div>

      <div class="topk-row">
        <span class="topk-label">Top-K</span>
        <button class="topk-btn" @click="topK = Math.max(1, topK - 1)">−</button>
        <span class="topk-value">{{ topK }}</span>
        <button class="topk-btn" @click="topK = Math.min(20, topK + 1)">+</button>
      </div>
    </div>

    <!-- 结果 -->
    <div class="kb-results">
      <div v-if="isSearching" class="kb-searching">
        <el-icon :size="24" class="is-loading"><Loading /></el-icon>
        <span>搜索中...</span>
      </div>

      <div v-else-if="results.length > 0" class="results-list">
        <div
          v-for="item in results"
          :key="item.chunk_id"
          class="result-card"
          :class="{ selected: isSelected(item.chunk_id) }"
        >
          <div class="card-top">
            <button class="card-check-btn" @click.stop="toggleSelection(item)">
              <el-icon v-if="isSelected(item.chunk_id)" color="var(--el-color-primary)" :size="20"><Select /></el-icon>
              <div v-else class="check-empty"></div>
            </button>
            <div class="card-meta">
              <span class="card-file">{{ item.resource_name }}</span>
              <div class="card-sub">
                <span>{{ item.kb_name }}</span>
                <span class="card-score">Score {{ item.score.toFixed(3) }}</span>
                <span class="card-chunk">#{{ item.chunk_index }}</span>
              </div>
            </div>
            <button class="card-expand-btn" @click.stop="toggleExpand(item.chunk_id)">
              <el-icon :size="16"><ArrowDown v-if="!isExpanded(item.chunk_id)" /><ArrowUp v-else /></el-icon>
            </button>
          </div>

          <div class="card-body" v-if="isExpanded(item.chunk_id)" @click.stop>
            <p :class="{ clamped: !isExpanded(item.chunk_id) }">{{ item.chunk_content }}</p>
          </div>

          <div v-if="isExpanded(item.chunk_id)" class="card-nav">
            <button class="nav-btn" :disabled="item.chunk_index <= 0" @click="navigateContext(item, 'prev')">
              <el-icon :size="16"><ArrowLeft /></el-icon>
            </button>
            <span class="nav-index">#{{ item.chunk_index }}</span>
            <button class="nav-btn" @click="navigateContext(item, 'next')">
              <el-icon :size="16"><ArrowRight /></el-icon>
            </button>
            <button
              v-if="item.chunk_index !== item.original_index"
              class="nav-btn reset"
              @click="resetToOriginal(item)"
            >
              <el-icon :size="16"><RefreshLeft /></el-icon>
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="hasSearched" class="kb-empty">无搜索结果</div>
      <div v-else class="kb-placeholder">
        <el-icon :size="40"><Search /></el-icon>
        <p>输入关键词搜索知识库</p>
      </div>

      <div v-if="selectedItems.length > 0" class="kb-confirm-bar">
        <span class="confirm-count">已选 {{ selectedItems.length }} 条</span>
        <button class="confirm-btn" @click="emitConfirm">确认使用</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  Search,
  Collection,
  ArrowDown,
  ArrowUp,
  ArrowLeft,
  ArrowRight,
  Select,
  RefreshLeft,
  Loading,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { searchKnowledgeBase, getKBFileChunks } from '@/api/kbService'
import { useResourceStore } from '@/stores/resourceStore'
import type { KBSearchResultItem } from '@/api/types'

// 扩展类型用于追踪原始索引
type ExtendedSearchResultItem = KBSearchResultItem & { original_index: number }

const emit = defineEmits<{
  (e: 'selection-change', items: KBSearchResultItem[]): void
  (e: 'confirm', items: KBSearchResultItem[]): void
}>()

const resourceStore = useResourceStore()
const { t } = useI18n()

// State
const queryText = ref('')
const topK = ref(5)
const selectedKbId = ref<string | null>(null)
const isSearching = ref(false)
const hasSearched = ref(false)
const results = ref<ExtendedSearchResultItem[]>([])
const selectedItems = ref<KBSearchResultItem[]>([])
const expandedItems = ref<Set<string>>(new Set())
const contextLoadingMap = ref<Map<string, boolean>>(new Map())
const showKbPicker = ref(false)

// Computed
const kbList = computed(() => {
  return resourceStore.resources
    .filter((r) => r.resourceType === 'knowledge_base')
    .sort((a, b) => a.sortOrder - b.sortOrder)
})

const selectedKbName = computed(() => {
  const kb = kbList.value.find(k => k.id === selectedKbId.value)
  return kb?.name ?? null
})

// Watchers
watch(
  kbList,
  (list) => {
    if (!selectedKbId.value && list.length > 0) {
      selectedKbId.value = list[0].id
    }
  },
  { immediate: true },
)

// 监听选中项变化，实时通知父组件
watch(
  selectedItems,
  (newVal) => {
    emit('selection-change', newVal)
  },
  { deep: true },
)

// Methods
const isSelected = (chunkId: string) =>
  selectedItems.value.some((item) => item.chunk_id === chunkId)

const toggleSelection = (item: KBSearchResultItem) => {
  const index = selectedItems.value.findIndex((i) => i.chunk_id === item.chunk_id)
  if (index > -1) {
    selectedItems.value.splice(index, 1)
  } else {
    selectedItems.value.push(item)
  }
}

const isExpanded = (chunkId: string) => expandedItems.value.has(chunkId)

const toggleExpand = (chunkId: string) => {
  if (expandedItems.value.has(chunkId)) {
    expandedItems.value.delete(chunkId)
  } else {
    expandedItems.value.add(chunkId)
  }
}

const handleSearch = async () => {
  if (!queryText.value.trim()) {
    ElMessage.warning(t('kb.search.msg.inputRequired'))
    return
  }

  isSearching.value = true
  hasSearched.value = true
  selectedItems.value = []
  expandedItems.value.clear()

  try {
    const res = await searchKnowledgeBase({
      query_text: queryText.value.trim(),
      top_k: topK.value,
      kb_id: selectedKbId.value,
    })

    results.value = res.items.map((item) => ({
      ...item,
      original_index: item.chunk_index,
    }))
  } catch (error) {
    console.error('Vector search failed', error)
    ElMessage.error(t('kb.search.msg.searchFailed'))
    results.value = []
  } finally {
    isSearching.value = false
  }
}

const isContextLoading = (chunkId: string, action: 'prev' | 'next' | 'reset') => {
  return contextLoadingMap.value.get(`${chunkId}-${action}`) || false
}

const updateChunkContent = async (
  item: ExtendedSearchResultItem,
  targetIndex: number,
  action: 'prev' | 'next' | 'reset',
) => {
  const loadingKey = `${item.chunk_id}-${action}`
  contextLoadingMap.value.set(loadingKey, true)

  try {
    const res = await getKBFileChunks(item.resource_id, {
      min_index: targetIndex,
      max_index: targetIndex,
      page: 1,
      page_size: 1,
    })

    if (res.items && res.items.length > 0) {
      const newChunk = res.items[0]
      const newItem: ExtendedSearchResultItem = {
        ...item,
        chunk_id: newChunk.id,
        chunk_content: newChunk.content,
        chunk_index: newChunk.chunk_index,
        original_index: item.original_index,
      }

      const index = results.value.findIndex((r) => r.chunk_id === item.chunk_id)
      if (index !== -1) {
        // 如果旧项被选中，需要从选中列表移除（因为ID变了）
        const selIndex = selectedItems.value.findIndex((i) => i.chunk_id === item.chunk_id)
        if (selIndex > -1) selectedItems.value.splice(selIndex, 1)

        results.value.splice(index, 1, newItem)

        // 保持展开状态
        expandedItems.value.delete(item.chunk_id)
        expandedItems.value.add(newItem.chunk_id)
      }
    } else {
      ElMessage.info(t('kb.search.msg.noMore'))
    }
  } catch (error) {
    console.error('Failed to fetch context chunk', error)
    ElMessage.error(t('kb.search.msg.fetchFailed'))
  } finally {
    contextLoadingMap.value.delete(loadingKey)
  }
}

const navigateContext = async (item: ExtendedSearchResultItem, direction: 'prev' | 'next') => {
  const targetIndex = direction === 'prev' ? item.chunk_index - 1 : item.chunk_index + 1
  if (targetIndex < 0) return
  await updateChunkContent(item, targetIndex, direction)
}

const resetToOriginal = async (item: ExtendedSearchResultItem) => {
  if (item.chunk_index === item.original_index) return
  await updateChunkContent(item, item.original_index, 'reset')
}

onMounted(() => {
  if (!selectedKbId.value && kbList.value.length > 0) {
    selectedKbId.value = kbList.value[0].id
  }
})

function emitConfirm() {
  emit('confirm', selectedItems.value)
  emit('selection-change', selectedItems.value)
}
</script>

<style scoped>
.kb-search {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.kb-toolbar {
  padding: 0 0 10px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kb-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  color: var(--el-text-color-primary);
  -webkit-tap-highlight-color: transparent;
  position: relative;
}

.kb-picker:active {
  background: var(--el-fill-color);
}

.kb-picker-label {
  flex: 1;
}

.picker-arrow {
  color: var(--el-text-color-placeholder);
  transition: transform 0.2s;
}

.search-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.search-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 10px;
}

.search-icon {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 15px;
  color: var(--el-text-color-primary);
  outline: none;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--el-text-color-placeholder);
}

.search-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: var(--el-color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}

.search-btn:active {
  transform: scale(0.92);
}

.search-btn:disabled {
  opacity: 0.6;
}

.is-loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.topk-row {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}

.topk-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.topk-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
  font-size: 18px;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-family: inherit;
}

.topk-btn:active {
  background: var(--el-fill-color);
}

.topk-value {
  font-size: 15px;
  font-weight: 600;
  min-width: 20px;
  text-align: center;
}

/* KB picker dropdown */
.kb-picker-list {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  margin-top: 4px;
  max-height: 180px;
  overflow-y: auto;
  background: var(--color-background);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.kb-picker-item {
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 14px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: background 0.15s;
}

.kb-picker-item:active {
  background: var(--el-fill-color-light);
}

.kb-picker-item.active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

/* Results */
.kb-results {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  display: flex;
  flex-direction: column;
}

.kb-searching {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 12px;
}

.result-card {
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s;
}

.result-card.selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.card-top {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
}

.card-check-btn {
  display: flex;
  align-items: center;
  padding: 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  flex-shrink: 0;
  -webkit-tap-highlight-color: transparent;
}

.check-empty {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid var(--el-border-color);
}

.card-expand-btn {
  display: flex;
  align-items: center;
  padding: 6px;
  border: none;
  background: transparent;
  color: var(--el-text-color-placeholder);
  cursor: pointer;
  flex-shrink: 0;
  -webkit-tap-highlight-color: transparent;
}

.check-empty {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid var(--el-border-color);
}

.card-meta {
  flex: 1;
  min-width: 0;
}

.card-file {
  font-size: 14px;
  font-weight: 600;
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.card-sub {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.card-score {
  font-family: monospace;
}

.card-chunk {
  background: var(--el-fill-color);
  padding: 0 5px;
  border-radius: 3px;
  font-family: monospace;
}

.card-body {
  padding: 0 12px 10px;
  cursor: pointer;
}

.card-body p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}

.card-body p.clamped {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
}

.nav-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid var(--el-border-color);
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--el-text-color-regular);
}

.nav-btn:active {
  background: var(--el-fill-color-light);
}

.nav-btn:disabled {
  opacity: 0.3;
}

.nav-btn.reset {
  margin-left: 6px;
}

.nav-index {
  font-family: monospace;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  min-width: 30px;
  text-align: center;
}

.kb-empty,
.kb-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}

.kb-confirm-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  margin-top: auto;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--color-background);
}

.confirm-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.confirm-btn {
  padding: 10px 24px;
  border: none;
  border-radius: 12px;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.confirm-btn:active {
  transform: scale(0.96);
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
