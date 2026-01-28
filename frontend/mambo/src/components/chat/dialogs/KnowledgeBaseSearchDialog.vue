<!-- frontend/mambo/src/components/chat/dialogs/KnowledgeBaseSearchDialog.vue -->
<template>
  <div class="kb-search-container">
    <!-- 搜索工具栏 -->
    <div class="search-toolbar">
      <div class="kb-select-container">
        <el-select
          v-model="selectedKbId"
          placeholder="选择知识库范围"
          clearable
          style="width: 100%"
        >
          <template #prefix>
            <el-icon><Collection /></el-icon>
          </template>
          <el-option
            v-for="kb in kbList"
            :key="kb.id"
            :label="kb.name"
            :value="kb.id"
          />
        </el-select>
      </div>

      <el-input
        v-model="queryText"
        placeholder="输入问题或关键词进行向量检索..."
        class="search-input"
        @keyup.enter="handleSearch"
        clearable
      >
        <template #append>
          <el-button :icon="Search" @click="handleSearch" :loading="isSearching" />
        </template>
      </el-input>

      <div class="settings-row">
        <span class="setting-label">匹配数量 (Top K):</span>
        <el-input-number
          v-model="topK"
          :min="1"
          :max="20"
          size="small"
          class="top-k-input"
        />
        <el-divider direction="vertical" />
        <span class="result-count" v-if="hasSearched">
          找到 {{ results.length }} 个相关切片
        </span>
      </div>
    </div>

    <!-- 结果列表 -->
    <div class="results-area" v-loading="isSearching">
      <el-scrollbar v-if="results.length > 0" class="custom-scrollbar">
        <div class="results-list">
          <div
            v-for="item in results"
            :key="item.chunk_id"
            class="result-item"
            :class="{ 'is-selected': isSelected(item.chunk_id) }"
          >
            <div class="item-header" @click="toggleSelection(item)">
              <div class="item-source">
                <el-icon><Collection /></el-icon>
                <span class="kb-name">{{ item.kb_name }}</span>
                <el-divider direction="vertical" />
                <el-icon><Document /></el-icon>
                <span class="file-name" :title="item.resource_name">{{ item.resource_name }}</span>
                <span class="chunk-index-badge">#{{ item.chunk_index }}</span>
              </div>
              <div class="item-score">
                <el-tag size="small" type="info" effect="plain" title="距离分数 (越小越相似)">
                  Score: {{ item.score.toFixed(4) }}
                </el-tag>
                <el-checkbox
                  :model-value="isSelected(item.chunk_id)"
                  @click.stop="toggleSelection(item)"
                  class="item-checkbox"
                />
              </div>
            </div>

            <div class="item-body">
              <div 
                class="item-content" 
                :class="{ 'is-collapsed': !isExpanded(item.chunk_id) }"
                @click="toggleExpand(item.chunk_id)"
              >
                {{ item.chunk_content }}
              </div>
              
              <div class="item-actions">
                <el-button 
                  link 
                  type="primary" 
                  size="small" 
                  @click="toggleExpand(item.chunk_id)"
                >
                  {{ isExpanded(item.chunk_id) ? '收起内容' : '展开查看' }}
                  <el-icon class="el-icon--right">
                    <ArrowUp v-if="isExpanded(item.chunk_id)" />
                    <ArrowDown v-else />
                  </el-icon>
                </el-button>
              </div>

              <!-- 上下文导航栏 (仅展开时显示) -->
              <div v-if="isExpanded(item.chunk_id)" class="context-nav">
                <el-button-group size="small">
                  <el-button 
                    :icon="ArrowLeft" 
                    :loading="isContextLoading(item.chunk_id, 'prev')"
                    :disabled="item.chunk_index <= 0"
                    @click="navigateContext(item, 'prev')"
                  >
                    上一片段
                  </el-button>
                  
                  <el-button disabled class="context-label">
                    当前: {{ item.chunk_index }}
                  </el-button>

                  <!-- 回跳按钮：仅当当前索引不等于原始索引时显示 -->
                  <el-tooltip 
                    v-if="item.chunk_index !== item.original_index"
                    content="点击跳回最初检索命中的切片位置"
                    placement="top"
                  >
                    <el-button 
                      type="primary" 
                      plain
                      :loading="isContextLoading(item.chunk_id, 'reset')"
                      @click="resetToOriginal(item)"
                    >
                      <el-icon><Aim /></el-icon>
                      命中: {{ item.original_index }}
                    </el-button>
                  </el-tooltip>

                  <el-button 
                    :loading="isContextLoading(item.chunk_id, 'next')"
                    @click="navigateContext(item, 'next')"
                  >
                    下一片段
                    <el-icon class="el-icon--right"><ArrowRight /></el-icon>
                  </el-button>
                </el-button-group>
              </div>
            </div>
          </div>
        </div>
      </el-scrollbar>

      <el-empty
        v-else-if="hasSearched"
        description="未找到匹配的知识库切片"
        :image-size="100"
      />
      <div v-else class="placeholder-state">
        <el-icon class="placeholder-icon"><Search /></el-icon>
        <p>输入关键词开始语义搜索</p>
      </div>
    </div>

    <!-- 底部操作栏 -->
    <div class="dialog-footer">
      <div class="selection-info">
        已选择 {{ selectedItems.length }} 个切片
      </div>
      <div class="footer-buttons">
        <el-button @click="$emit('cancel')">取消</el-button>
        <el-button
          type="primary"
          @click="handleConfirm"
          :disabled="selectedItems.length === 0"
        >
          确认使用 ({{ selectedItems.length }})
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { 
  Search, 
  Document, 
  Collection, 
  ArrowDown, 
  ArrowUp, 
  ArrowLeft, 
  ArrowRight,
  Aim
} from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { searchKnowledgeBase, getKBFileChunks } from '@/api/kbService';
import { useResourceStore } from '@/stores/resourceStore';
import type { KBSearchResultItem } from '@/api/types';

// --- Types ---
// 扩展基础类型，增加原始索引字段，用于回跳功能
type ExtendedSearchResultItem = KBSearchResultItem & { original_index: number };

// --- Emits ---
const emit = defineEmits<{
  (e: 'cancel'): void;
  (e: 'confirm', items: KBSearchResultItem[]): void;
}>();

// --- Store ---
const resourceStore = useResourceStore();

// --- State ---
const queryText = ref('');
const topK = ref(5);
const selectedKbId = ref<string | null>(null);
const isSearching = ref(false);
const hasSearched = ref(false);
const results = ref<ExtendedSearchResultItem[]>([]);
const selectedItems = ref<KBSearchResultItem[]>([]);
const expandedItems = ref<Set<string>>(new Set());
const contextLoadingMap = ref<Map<string, boolean>>(new Map());

// --- Computed ---
const kbList = computed(() => {
  return resourceStore.resources
    .filter(r => r.resourceType === 'knowledge_base')
    .sort((a, b) => a.sortOrder - b.sortOrder);
});

// --- Watchers ---
watch(kbList, (list) => {
  if (!selectedKbId.value && list.length > 0) {
    selectedKbId.value = list[0].id;
  }
}, { immediate: true });

// --- Methods ---

const isSelected = (chunkId: string) => {
  return selectedItems.value.some(item => item.chunk_id === chunkId);
};

const toggleSelection = (item: KBSearchResultItem) => {
  const index = selectedItems.value.findIndex(i => i.chunk_id === item.chunk_id);
  if (index > -1) {
    selectedItems.value.splice(index, 1);
  } else {
    selectedItems.value.push(item);
  }
};

const isExpanded = (chunkId: string) => {
  return expandedItems.value.has(chunkId);
};

const toggleExpand = (chunkId: string) => {
  if (expandedItems.value.has(chunkId)) {
    expandedItems.value.delete(chunkId);
  } else {
    expandedItems.value.add(chunkId);
  }
};

const handleSearch = async () => {
  if (!queryText.value.trim()) {
    ElMessage.warning('请输入搜索内容');
    return;
  }

  isSearching.value = true;
  hasSearched.value = true;
  selectedItems.value = [];
  expandedItems.value.clear();

  try {
    const res = await searchKnowledgeBase({
      query_text: queryText.value.trim(),
      top_k: topK.value,
      kb_id: selectedKbId.value
    });
    
    // 初始化时，记录原始索引
    results.value = res.items.map(item => ({
      ...item,
      original_index: item.chunk_index
    }));
  } catch (error) {
    console.error('Vector search failed', error);
    ElMessage.error('检索失败，请稍后重试');
    results.value = [];
  } finally {
    isSearching.value = false;
  }
};

const isContextLoading = (chunkId: string, action: 'prev' | 'next' | 'reset') => {
  return contextLoadingMap.value.get(`${chunkId}-${action}`) || false;
};

/**
 * 核心方法：获取指定索引的切片并替换当前列表项
 */
const updateChunkContent = async (
  item: ExtendedSearchResultItem, 
  targetIndex: number, 
  action: 'prev' | 'next' | 'reset'
) => {
  const loadingKey = `${item.chunk_id}-${action}`;
  contextLoadingMap.value.set(loadingKey, true);

  try {
    const res = await getKBFileChunks(item.resource_id, {
      min_index: targetIndex,
      max_index: targetIndex,
      page: 1,
      page_size: 1
    });

    if (res.items && res.items.length > 0) {
      const newChunk = res.items[0];
      
      // 构造新对象，务必保留 original_index
      const newItem: ExtendedSearchResultItem = {
        ...item,
        chunk_id: newChunk.id,
        chunk_content: newChunk.content,
        chunk_index: newChunk.chunk_index,
        original_index: item.original_index 
      };

      // 在结果列表中原地替换
      const index = results.value.findIndex(r => r.chunk_id === item.chunk_id);
      if (index !== -1) {
        // 如果旧项被选中，取消选中（因为内容变了，ID也变了）
        const selIndex = selectedItems.value.findIndex(i => i.chunk_id === item.chunk_id);
        if (selIndex > -1) {
          selectedItems.value.splice(selIndex, 1);
        }

        results.value.splice(index, 1, newItem);

        // 更新展开状态：移除旧ID，添加新ID，保持展开
        expandedItems.value.delete(item.chunk_id);
        expandedItems.value.add(newItem.chunk_id);
      }
    } else {
      ElMessage.info('没有更多切片了');
    }
  } catch (error) {
    console.error('Failed to fetch context chunk', error);
    ElMessage.error('获取切片内容失败');
  } finally {
    contextLoadingMap.value.delete(loadingKey);
  }
};

const navigateContext = async (item: ExtendedSearchResultItem, direction: 'prev' | 'next') => {
  const targetIndex = direction === 'prev' ? item.chunk_index - 1 : item.chunk_index + 1;
  if (targetIndex < 0) return;
  await updateChunkContent(item, targetIndex, direction);
};

const resetToOriginal = async (item: ExtendedSearchResultItem) => {
  if (item.chunk_index === item.original_index) return;
  await updateChunkContent(item, item.original_index, 'reset');
};

const handleConfirm = () => {
  if (selectedItems.value.length === 0) return;
  emit('confirm', selectedItems.value);
};

onMounted(() => {
  if (!selectedKbId.value && kbList.value.length > 0) {
    selectedKbId.value = kbList.value[0].id;
  }
});
</script>

<style scoped>
.kb-search-container {
  display: flex;
  flex-direction: column;
  height: 60vh;
  overflow: hidden;
}

.search-toolbar {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.kb-select-container {
  margin-bottom: 12px;
}

.search-input {
  margin-bottom: 12px;
}

.settings-row {
  display: flex;
  align-items: center;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.setting-label {
  margin-right: 8px;
}

.top-k-input {
  width: 100px;
}

.result-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.results-area {
  flex-grow: 1;
  overflow: hidden;
  min-height: 0;
  position: relative;
  background-color: var(--el-fill-color-blank);
  display: flex;
  flex-direction: column;
}

.custom-scrollbar {
  height: 100%;
}

.results-list {
  padding: 12px 0;
}

.result-item {
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background-color 0.2s;
}

.result-item:hover {
  background-color: var(--el-fill-color-light);
}

.result-item.is-selected {
  background-color: var(--el-color-primary-light-9);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  cursor: pointer;
}

.item-source {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
}

.kb-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.chunk-index-badge {
  background-color: var(--el-fill-color-dark);
  padding: 0 4px;
  border-radius: 4px;
  font-family: monospace;
}

.item-score {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.item-checkbox {
  margin-right: 0;
  height: 20px;
}

.item-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  word-break: break-all;
  white-space: pre-wrap;
  cursor: pointer;
}

.item-content.is-collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.item-actions {
  display: flex;
  justify-content: flex-start;
}

.context-nav {
  display: flex;
  justify-content: center;
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.context-label {
  min-width: 80px;
  font-family: monospace;
}

.placeholder-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
}

.placeholder-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.dialog-footer {
  margin-top: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  background-color: #fff;
  z-index: 10;
}

.selection-info {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.footer-buttons {
  display: flex;
  gap: 12px;
}
</style>
