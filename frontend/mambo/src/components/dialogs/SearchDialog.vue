<!-- frontend/mambo/src/components/dialogs/SearchDialog.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    title="会话搜索"
    width="700px"
    :close-on-click-modal="false"
    @open="handleOpen"
    @close="handleClose"
  >
    <div class="search-dialog-container">
      <!-- 搜索范围提示 -->
      <div v-if="searchRootId && (rootName || rootPath)" class="search-scope-info">
        <el-icon><FolderOpened /></el-icon>
        <span class="scope-label">搜索范围：</span>
        <span class="scope-text">
          {{ rootName || rootPath }}
        </span>
      </div>
      <div v-else class="search-scope-info global-scope">
        <el-icon><Monitor /></el-icon>
        <span class="scope-label">搜索范围：</span>
        <span class="scope-text">全局搜索</span>
      </div>

      <!-- 搜索表单 -->
      <div class="search-form">
        <el-input
          v-model="searchKeyword"
          placeholder="输入搜索关键词..."
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button :icon="Search" @click="handleSearch" />
          </template>
        </el-input>

        <div class="search-options">
          <el-checkbox v-model="enableRegex" @change="handleSearch">使用正则表达式</el-checkbox>
        </div>
      </div>

      <!-- 搜索结果 -->
      <div class="search-results">
        <div v-if="isLoading" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>搜索中...</span>
        </div>

        <div v-else-if="searchResults.length === 0 && !hasSearched" class="empty-state">
          <el-icon><Search /></el-icon>
          <span>请输入关键词进行搜索</span>
        </div>

        <div v-else-if="searchResults.length === 0 && hasSearched" class="empty-state">
          <el-icon><DocumentDelete /></el-icon>
          <span>未找到匹配的结果</span>
        </div>

        <div v-else class="results-list">
          <div
            v-for="(item, index) in searchResults"
            :key="item.chat_id + '-' + item.sub_message_id + '-' + index"
            class="result-item"
            @click="handleResultClick(item)"
          >
            <div class="result-header">
              <div class="result-title">
                <el-icon><ChatDotRound /></el-icon>
                <span class="chat-name">{{ item.chat_name }}</span>
              </div>
              <el-tag :type="getMatchTypeTagType(item.match_type)" size="small">
                {{ getMatchTypeText(item.match_type) }}
              </el-tag>
            </div>

            <div v-if="item.chat_path" class="result-path">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ item.chat_path }}</span>
            </div>

            <div class="result-content" v-html="highlightKeyword(item.context_text)"></div>

            <div class="result-footer">
              <span class="result-time">{{ formatTime(item.created_at) }}</span>
              <el-button type="primary" link size="small">
                查看详情
                <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div v-if="total > 0" class="pagination-container">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleSearch"
            @current-change="handleSearch"
          />
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Search, Loading, DocumentDelete, ChatDotRound, FolderOpened, ArrowRight, Monitor } from '@element-plus/icons-vue';
import { searchChats } from '@/api/chatService';
import type { SearchResultItem } from '@/api/types';

interface Props {
  visible: boolean;
  rootId?: string | null;
  rootName?: string | null;
  rootPath?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  rootId: null,
  rootName: null,
  rootPath: null,
});

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'select-result', data: { chatId: string; subMessageId: string | null }): void;
}>();

const router = useRouter();

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
});

// 搜索相关状态
const searchKeyword = ref('');
const searchScope = ref<string | null>(null);
const enableRegex = ref(false);
const searchResults = ref<SearchResultItem[]>([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(20);
const isLoading = ref(false);
const hasSearched = ref(false);
const searchRootId = ref<string | null>(props.rootId);
const rootName = ref<string | null>(props.rootName);
const rootPath = ref<string | null>(props.rootPath);

function handleOpen() {
  // 重置搜索状态
  searchKeyword.value = '';
  searchScope.value = props.rootId || null;
  enableRegex.value = false;
  searchResults.value = [];
  total.value = 0;
  currentPage.value = 1;
  hasSearched.value = false;
  searchRootId.value = props.rootId || null;
  rootName.value = props.rootName || null;
  rootPath.value = props.rootPath || null;
}

function handleClose() {
  // 清理状态
  searchKeyword.value = '';
  searchResults.value = [];
  hasSearched.value = false;
}

async function handleSearch() {
  if (!searchKeyword.value.trim()) {
    ElMessage.warning('请输入搜索关键词');
    return;
  }

  isLoading.value = true;
  hasSearched.value = true;

  try {
    const response = await searchChats({
      keyword: searchKeyword.value.trim(),
      root_id: searchScope.value,
      enable_regex: enableRegex.value,
      page_num: currentPage.value,
      page_size: pageSize.value,
    });

    searchResults.value = response.items;
    total.value = response.total;
  } catch (error) {
    console.error('Search failed:', error);
    ElMessage.error('搜索失败，请稍后重试');
  } finally {
    isLoading.value = false;
  }
}

function handleResultClick(item: SearchResultItem) {
  emit('select-result', {
    chatId: item.chat_id,
    subMessageId: item.sub_message_id,
  });
  dialogVisible.value = false;
}

function highlightKeyword(text: string): string {
  if (!searchKeyword.value) return text;

  const keyword = enableRegex.value
    ? searchKeyword.value
    : searchKeyword.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  try {
    const regex = new RegExp(`(${keyword})`, 'gi');
    return text.replace(regex, '<mark class="search-highlight">$1</mark>');
  } catch (e) {
    // 如果正则表达式无效，返回原文本
    return text;
  }
}

function getMatchTypeText(type: string): string {
  switch (type) {
    case 'title':
      return '标题';
    case 'system_prompt':
      return '系统提示词';
    case 'content':
      return '消息内容';
    default:
      return type;
  }
}

function getMatchTypeTagType(type: string): any {
  switch (type) {
    case 'title':
      return 'primary';
    case 'system_prompt':
      return 'warning';
    case 'content':
      return 'success';
    default:
      return 'info';
  }
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return '今天';
  if (days === 1) return '昨天';
  if (days < 7) return `${days}天前`;

  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}
</script>

<style scoped>
.search-dialog-container {
  display: flex;
  flex-direction: column;
  min-height: 400px;
}

.search-scope-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background-color: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.search-scope-info .el-icon {
  font-size: 16px;
  color: var(--el-color-primary);
}

.search-scope-info.global-scope .el-icon {
  color: var(--el-color-success);
}

.scope-label {
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.scope-text {
  flex-grow: 1;
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.search-form {
  margin-bottom: 20px;
}

.search-options {
  margin-top: 10px;
  display: flex;
  align-items: center;
}

.search-results {
  flex-grow: 1;
  overflow-y: auto;
  max-height: 500px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--el-text-color-secondary);
}

.loading-state .el-icon,
.empty-state .el-icon {
  font-size: 48px;
  margin-bottom: 16px;
  color: var(--el-text-color-placeholder);
}

.loading-state span,
.empty-state span {
  font-size: 14px;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-item {
  padding: 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background-color: var(--color-background-soft);
  cursor: pointer;
  transition: all 0.2s;
}

.result-item:hover {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.result-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-grow: 1;
  min-width: 0;
}

.result-title .el-icon {
  flex-shrink: 0;
  color: var(--el-color-primary);
}

.chat-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-path {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.result-path .el-icon {
  font-size: 14px;
}

.result-path span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.result-content {
  padding: 8px;
  background-color: var(--color-background);
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  word-break: break-word;
  margin-bottom: 8px;
}

:deep(.search-highlight) {
  background-color: var(--el-color-warning-light-7);
  color: var(--el-color-warning-dark-2);
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}

.result-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.result-time {
  color: var(--el-text-color-placeholder);
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color);
}
</style>
