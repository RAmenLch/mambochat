<template>
  <div class="kb-search-container">
    <!-- 搜索工具栏 -->
    <div class="search-toolbar">
      <div class="kb-select-container">
        <el-select
          v-model="selectedKbId"
          placeholder="选择知识库范围 (默认全部)"
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
            @click="toggleSelection(item)"
          >
            <div class="item-header">
              <div class="item-source">
                <el-icon><Collection /></el-icon>
                <span class="kb-name">{{ item.kb_name }}</span>
                <el-divider direction="vertical" />
                <el-icon><Document /></el-icon>
                <span class="file-name" :title="item.resource_name">{{ item.resource_name }}</span>
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

            <div class="item-content">
              {{ item.chunk_content }}
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
import { ref, computed } from 'vue';
import { Search, Document, Collection } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { searchKnowledgeBase } from '@/api/kbService';
import { useResourceStore } from '@/stores/resourceStore';
import type { KBSearchResultItem } from '@/api/types';

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
const results = ref<KBSearchResultItem[]>([]);
const selectedItems = ref<KBSearchResultItem[]>([]);

// --- Computed ---
const kbList = computed(() => {
  return resourceStore.resources.filter(r => r.resourceType === 'knowledge_base');
});

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

const handleSearch = async () => {
  if (!queryText.value.trim()) {
    ElMessage.warning('请输入搜索内容');
    return;
  }

  isSearching.value = true;
  hasSearched.value = true;
  selectedItems.value = [];

  try {
    const res = await searchKnowledgeBase({
      query_text: queryText.value.trim(),
      top_k: topK.value,
      kb_id: selectedKbId.value
    });
    results.value = res.items;
  } catch (error) {
    console.error('Vector search failed', error);
    ElMessage.error('检索失败，请稍后重试');
    results.value = [];
  } finally {
    isSearching.value = false;
  }
};

const handleConfirm = () => {
  if (selectedItems.value.length === 0) return;
  emit('confirm', selectedItems.value);
};
</script>

<style scoped>
.kb-search-container {
  display: flex;
  flex-direction: column;
  height: 60vh;
  /* 关键修复 1: 强制隐藏溢出，防止内部元素（如Loading遮罩）撑开容器 */
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
  /* 关键修复 2: 防止 Flex 子元素溢出，并允许其在空间不足时收缩 */
  overflow: hidden;
  min-height: 0;
  position: relative;
  background-color: var(--el-fill-color-blank);
  display: flex;
  flex-direction: column;
}

/* 确保滚动条占满剩余空间 */
.custom-scrollbar {
  height: 100%;
}

.results-list {
  padding: 12px 0;
}

.result-item {
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
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

.item-content {
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
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
  background-color: #fff; /* 确保背景色不透明 */
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
