<!-- frontend/mambo/src/mobile/components/chat/dialogs/KnowledgeBaseSearchDialog.vue -->
<template>
  <div class="mobile-kb-search">
    <!-- 搜索工具栏 -->
    <div class="search-toolbar">
      <div class="kb-select-row">
        <el-select
          v-model="selectedKbId"
          :placeholder="$t('kb.search.selectKbPlaceholder')"
          clearable
          style="width: 100%"
        >
          <template #prefix>
            <el-icon><Collection /></el-icon>
          </template>
          <el-option v-for="kb in kbList" :key="kb.id" :label="kb.name" :value="kb.id" />
        </el-select>
      </div>

      <el-input
        v-model="queryText"
        :placeholder="$t('kb.search.inputPlaceholder')"
        clearable
        @keyup.enter="handleSearch"
      >
        <template #append>
          <el-button :icon="Search" @click="handleSearch" :loading="isSearching" />
        </template>
      </el-input>

      <div class="settings-row">
        <span class="label">{{ $t('kb.search.topKLabel') }}</span>
        <el-input-number
          v-model="topK"
          :min="1"
          :max="20"
          size="small"
          controls-position="right"
          style="width: 80px"
        />
      </div>
    </div>

    <!-- 结果列表 -->
    <div class="results-area" v-loading="isSearching">
      <el-scrollbar v-if="results.length > 0">
        <div class="results-list">
          <div
            v-for="item in results"
            :key="item.chunk_id"
            class="result-card"
            :class="{ 'is-active': isSelected(item.chunk_id) }"
          >
            <!-- 卡片头部：选中状态与元信息 -->
            <div class="card-header" @click="toggleSelection(item)">
              <el-checkbox :model-value="isSelected(item.chunk_id)" @click.stop size="large" />
              <div class="meta-info">
                <div class="meta-top">
                  <span class="file-name">{{ item.resource_name }}</span>
                  <el-tag size="small" type="info" effect="plain">
                    Score: {{ item.score.toFixed(3) }}
                  </el-tag>
                </div>
                <div class="meta-bottom">
                  <span class="kb-name">{{ item.kb_name }}</span>
                  <span class="chunk-badge">#{{ item.chunk_index }}</span>
                </div>
              </div>
            </div>

            <!-- 卡片内容 -->
            <div class="card-body" @click="toggleExpand(item.chunk_id)">
              <div class="content-text" :class="{ 'is-collapsed': !isExpanded(item.chunk_id) }">
                {{ item.chunk_content }}
              </div>
            </div>

            <!-- 操作区：展开/导航 -->
            <div class="card-actions">
              <el-button link type="primary" size="small" @click.stop="toggleExpand(item.chunk_id)">
                {{ isExpanded(item.chunk_id) ? $t('kb.search.collapse') : $t('kb.search.expand') }}
                <el-icon class="el-icon--right" v-if="!isExpanded(item.chunk_id)"
                  ><ArrowDown
                /></el-icon>
                <el-icon class="el-icon--right" v-else><ArrowUp /></el-icon>
              </el-button>

              <!-- 上下文导航：仅展开时显示 -->
              <div v-if="isExpanded(item.chunk_id)" class="context-nav">
                <el-button-group size="small">
                  <el-button
                    :icon="ArrowLeft"
                    :loading="isContextLoading(item.chunk_id, 'prev')"
                    :disabled="item.chunk_index <= 0"
                    @click.stop="navigateContext(item, 'prev')"
                  >
                    Prev
                  </el-button>

                  <el-button disabled size="small" class="index-display">
                    #{{ item.chunk_index }}
                  </el-button>

                  <el-button
                    :loading="isContextLoading(item.chunk_id, 'next')"
                    @click.stop="navigateContext(item, 'next')"
                  >
                    Next
                    <el-icon class="el-icon--right"><ArrowRight /></el-icon>
                  </el-button>
                </el-button-group>

                <!-- 回跳按钮 -->
                <el-button
                  v-if="item.chunk_index !== item.original_index"
                  size="small"
                  type="warning"
                  plain
                  style="margin-left: 8px"
                  :loading="isContextLoading(item.chunk_id, 'reset')"
                  @click.stop="resetToOriginal(item)"
                >
                  <el-icon><Aim /></el-icon>
                  Reset
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </el-scrollbar>

      <el-empty v-else-if="hasSearched" :description="$t('kb.search.noResult')" :image-size="80" />
      <div v-else class="placeholder-state">
        <el-icon :size="48"><Search /></el-icon>
        <p>{{ $t('kb.search.placeholder') }}</p>
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
  Aim,
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

// Computed
const kbList = computed(() => {
  return resourceStore.resources
    .filter((r) => r.resourceType === 'knowledge_base')
    .sort((a, b) => a.sortOrder - b.sortOrder)
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
</script>

<style scoped>
.mobile-kb-search {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--el-bg-color);
}

.search-toolbar {
  padding: 10px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.kb-select-row {
  margin-bottom: 10px;
}

.settings-row {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.results-area {
  flex: 1;
  overflow: hidden;
}

.results-list {
  padding: 10px;
}

.result-card {
  background-color: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
  transition: all 0.2s;
}

.result-card.is-active {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.card-header {
  display: flex;
  align-items: center;
  padding: 10px;
  gap: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
}

.meta-info {
  flex: 1;
  overflow: hidden;
}

.meta-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.file-name {
  font-weight: 500;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.meta-bottom {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.kb-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chunk-badge {
  background-color: var(--el-fill-color-dark);
  padding: 0 4px;
  border-radius: 4px;
  font-family: monospace;
}

.card-body {
  padding: 10px;
  cursor: pointer;
}

.content-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-all;
}

.content-text.is-collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-actions {
  padding: 8px 10px;
  border-top: 1px solid var(--el-border-color-lighter);
  background-color: var(--el-fill-color-lighter);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.context-nav {
  margin-top: 8px;
  display: flex;
  align-items: center;
  width: 100%;
  justify-content: center;
}

.index-display {
  font-family: monospace;
  pointer-events: none;
}

.placeholder-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
}
</style>
