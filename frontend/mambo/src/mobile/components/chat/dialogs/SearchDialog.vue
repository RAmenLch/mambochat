<!-- frontend/mambo/src/mobile/components/chat/dialogs/SearchDialog.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t('chat.search.title')"
    width="100%"
    fullscreen
    :show-close="false"
    class="mobile-search-dialog"
  >
    <template #header>
      <div class="mobile-search-header">
        <el-button link @click="dialogVisible = false">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <span class="title">{{ $t('chat.search.title') }}</span>
        <div style="width: 30px"></div>
      </div>
    </template>

    <div class="search-container">
      <el-input
        v-model="searchKeyword"
        :placeholder="$t('chat.search.placeholder')"
        clearable
        size="large"
        @clear="handleSearch"
        @keyup.enter="handleSearch"
      >
        <template #append>
          <el-button :icon="Search" @click="handleSearch" />
        </template>
      </el-input>

      <div class="search-options">
        <el-checkbox v-model="enableRegex" @change="handleSearch">
          {{ $t('chat.search.regex') }}
        </el-checkbox>
      </div>

      <!-- Results -->
      <div class="search-results" v-loading="isLoading">
        <div v-if="searchResults.length === 0 && hasSearched" class="empty-state">
          <el-empty :description="$t('chat.search.noResult')" />
        </div>

        <div v-else-if="searchResults.length === 0" class="empty-state">
          <el-empty :description="$t('chat.search.tipInput')" />
        </div>

        <div v-else class="results-list">
          <div
            v-for="item in searchResults"
            :key="item.chat_id"
            class="result-item"
            @click="handleResultClick(item)"
          >
            <div class="result-title">
              <el-icon><ChatDotRound /></el-icon>
              <span>{{ item.chat_name }}</span>
            </div>
            <div class="result-path" v-if="item.chat_path">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ item.chat_path }}</span>
            </div>
            <div class="result-content" v-html="highlightKeyword(item.context_text)"></div>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Search, ArrowLeft, ChatDotRound, FolderOpened } from '@element-plus/icons-vue'
import { searchChats } from '@/api/chatService'
import type { SearchResultItem } from '@/api/types'

const { t } = useI18n()

interface Props {
  visible: boolean
  rootId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  rootId: null,
})

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'select-result', data: { chatId: string; subMessageId: string | null }): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const searchKeyword = ref('')
const enableRegex = ref(false)
const searchResults = ref<SearchResultItem[]>([])
const isLoading = ref(false)
const hasSearched = ref(false)

const handleSearch = async () => {
  if (!searchKeyword.value.trim()) {
    return
  }

  isLoading.value = true
  hasSearched.value = true

  try {
    const response = await searchChats({
      keyword: searchKeyword.value.trim(),
      root_id: props.rootId,
      enable_regex: enableRegex.value,
    })
    searchResults.value = response.items
  } catch (error) {
    ElMessage.error(t('chat.search.error'))
  } finally {
    isLoading.value = false
  }
}

const handleResultClick = (item: SearchResultItem) => {
  emit('select-result', {
    chatId: item.chat_id,
    subMessageId: item.sub_message_id,
  })
  dialogVisible.value = false
}

const highlightKeyword = (text: string): string => {
  if (!searchKeyword.value) return text
  const keyword = enableRegex.value
    ? searchKeyword.value
    : searchKeyword.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  try {
    const regex = new RegExp(`(${keyword})`, 'gi')
    return text.replace(regex, '<mark class="highlight">$1</mark>')
  } catch {
    return text
  }
}
</script>

<style scoped>
.mobile-search-dialog :deep(.el-dialog__header) {
  padding: 0;
}

.mobile-search-dialog :deep(.el-dialog__body) {
  padding: 10px;
  height: calc(100vh - 60px);
  overflow: hidden;
}

.mobile-search-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 15px;
  border-bottom: 1px solid var(--el-border-color);
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.search-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.search-options {
  margin: 10px 0;
}

.search-results {
  flex: 1;
  overflow-y: auto;
}

.result-item {
  padding: 15px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 5px;
}

.result-path {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.result-content {
  font-size: 14px;
  color: var(--el-text-color-regular);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

:deep(.highlight) {
  background-color: var(--el-color-warning-light-5);
  color: var(--el-color-warning-dark-2);
  padding: 0 2px;
  border-radius: 2px;
}
</style>
