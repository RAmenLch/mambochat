<!-- frontend/mambo/src/components/chat/ChatHeader.vue -->
<template>
  <div class="chat-header-container" :class="[`mode-${mode}`]">
    <!-- 竖向模式特有的顶部展开按钮 -->
    <div v-if="mode === 'vertical'" class="header-top-actions">
      <el-tooltip :content="$t('chat.header.expand')" placement="right">
        <el-button link class="expand-btn" @click="$emit('expand')">
          <el-icon :size="18"><Expand /></el-icon>
        </el-button>
      </el-tooltip>
    </div>

    <!-- 标题区域 -->
    <div class="title-section">
      <!-- 竖向编辑模式：使用 Popover -->
      <template v-if="mode === 'vertical'">
        <div class="vertical-title-wrapper">
          <h3 class="chat-title">{{ displayTitle || $t('chat.header.noChat') }}</h3>
        </div>
      </template>

      <!-- 横向编辑模式：行内 Input 切换 -->
      <template v-else>
        <div v-if="!isEditingTitle && currentChat" class="horizontal-title-display">
          <h3 class="chat-title">{{ displayTitle }}</h3>
          <div class="title-actions">
            <!-- 编辑和刷新保留在标题旁边 -->
            <el-tooltip :content="$t('chat.header.editTitle')" placement="bottom" :show-after="500">
              <el-button :icon="Edit" circle text @click="startHorizontalEdit" />
            </el-tooltip>
            <el-tooltip :content="$t('chat.header.refreshTitle')" placement="bottom" :show-after="500">
              <el-button
                :icon="Refresh"
                circle
                text
                @click="handleRefreshTitle"
                :loading="isTitleRefreshing"
              />
            </el-tooltip>
          </div>
        </div>
        <div v-else-if="isEditingTitle" class="title-edit-area">
          <el-input
            ref="titleInputRef"
            v-model="titleInput"
            @blur="saveTitle"
            @keydown.enter.prevent="saveTitle"
            class="title-input"
          />
        </div>
      </template>
    </div>

    <!-- 横向模式：右侧操作区 (导出/导入按钮) -->
    <div v-if="mode === 'horizontal'" class="header-right-actions">
      <input
        ref="importInputRef"
        type="file"
        accept=".json,application/json"
        style="display: none"
        @change="handleImportFile"
      />
      <el-dropdown trigger="click" @command="handleExport">
        <el-button :icon="Download" circle text :title="$t('chat.header.export')" />
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="json">{{ $t('chat.header.exportJson') }}</el-dropdown-item>
            <el-dropdown-item command="markdown">{{ $t('chat.header.exportMd') }}</el-dropdown-item>
            <el-dropdown-item command="html">{{ $t('chat.header.exportHtml') }}</el-dropdown-item>
            <el-dropdown-item command="importJson" divided>{{ $t('chat.header.importJson') }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 竖向模式底部的操作按钮组 -->
    <div v-if="mode === 'vertical' && currentChat" class="header-bottom-actions">

      <!-- 编辑按钮 (Popover) -->
      <el-popover
        v-model:visible="isPopoverVisible"
        placement="right"
        :width="250"
        trigger="click"
        @show="initPopoverInput"
      >
        <template #reference>
          <el-button :icon="Edit" circle text class="action-btn" :title="$t('chat.header.editTitle')" />
        </template>
        <div class="popover-edit-content">
          <el-input
            ref="popoverInputRef"
            v-model="titleInput"
            :placeholder="$t('chat.header.inputPlaceholder')"
            @keydown.enter.prevent="saveTitle"
          />
          <el-button type="primary" size="small" @click="saveTitle">{{ $t('common.action.save') }}</el-button>
        </div>
      </el-popover>

      <!-- 刷新按钮 -->
      <el-tooltip :content="$t('chat.header.refreshTitle')" placement="right">
        <el-button
          :icon="Refresh"
          circle
          text
          class="action-btn"
          @click="handleRefreshTitle"
          :loading="isTitleRefreshing"
        />
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ElInput } from 'element-plus';
import { ElMessage } from 'element-plus';
import { isDefaultChatName } from '@/utils/chatName';
import { Edit, Refresh, Expand, Download } from '@element-plus/icons-vue';
import type { Chat, Message } from '@/api/types';
import { importChat } from '@/api/chatService';
import { exportChat } from '@/utils/chatExport';

const { t } = useI18n();

const props = withDefaults(defineProps<{
  currentChat: Chat | null;
  isTitleRefreshing: boolean;
  mode?: 'horizontal' | 'vertical';
  messages?: Message[];
}>(), {
  mode: 'horizontal',
  messages: () => []
});

const emit = defineEmits<{
  (e: 'save-title', newTitle: string): void;
  (e: 'refresh-title'): void;
  (e: 'expand'): void;
  (e: 'imported', chatId: string): void;
}>();

// --- State ---
const isEditingTitle = ref(false);
const isPopoverVisible = ref(false);
const titleInput = ref('');
const isExporting = ref(false);

// 默认标题占位 Key 渲染为 i18n 文本，其余情况原样显示
const displayTitle = computed(() => {
  if (!props.currentChat) return '';
  return isDefaultChatName(props.currentChat.name) ? t('chat.sidebar.initChatName') : props.currentChat.name;
});

// Refs
const titleInputRef = ref<InstanceType<typeof ElInput>>();
const popoverInputRef = ref<InstanceType<typeof ElInput>>();
const importInputRef = ref<HTMLInputElement>();

// --- Actions ---

function startHorizontalEdit() {
  if (!props.currentChat) return;
  isEditingTitle.value = true;
  titleInput.value = displayTitle.value;
  nextTick(() => titleInputRef.value?.focus());
}

function initPopoverInput() {
  if (!props.currentChat) return;
  titleInput.value = displayTitle.value;
  nextTick(() => popoverInputRef.value?.focus());
}

function saveTitle() {
  if (!props.currentChat) return;

  const newName = titleInput.value.trim();
  // 与显示名比较：默认标题 Key 显示为 i18n 文本，未修改直接保存时保持 Key，
  // 不覆盖为 i18n 文本，保留后端自动生成标题的机会
  if (newName && newName !== displayTitle.value) {
    emit('save-title', newName);
  }

  isEditingTitle.value = false;
  isPopoverVisible.value = false;
}

function handleRefreshTitle() {
  emit('refresh-title');
}

// --- Export / Import（逻辑集中在 utils/chatExport.ts，与移动端共用） ---

async function handleExport(format: 'json' | 'markdown' | 'html' | 'importJson') {
  if (!props.currentChat) return;

  if (format === 'importJson') {
    importInputRef.value?.click();
    return;
  }
  if (isExporting.value) return;

  isExporting.value = true;
  try {
    await exportChat(props.currentChat, props.messages || [], format);
  } catch (error) {
    console.error('Export failed:', error);
    ElMessage.error(t('chat.header.exportFailed'));
  } finally {
    isExporting.value = false;
  }
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file || !props.currentChat) return;

  isExporting.value = true;
  try {
    const report = await importChat(file);
    ElMessage.success(t('chat.header.importSuccess', { name: report.name }));
    emit('imported', report.chat_id);
  } catch (error) {
    console.error('Chat import failed:', error);
  } finally {
    isExporting.value = false;
  }
}

watch(() => props.currentChat?.id, () => {
  isEditingTitle.value = false;
  isPopoverVisible.value = false;
});
</script>

<style scoped>
.chat-header-container {
  box-sizing: border-box;
  background-color: var(--color-background);
}

/* --- Horizontal Mode Styles --- */
.mode-horizontal {
  flex-shrink: 0;
  padding: 0 20px;
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--color-border);
  width: 100%;
}

.horizontal-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  width: 100%;
}

.title-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.title-edit-area {
  width: 100%;
}

.header-right-actions {
  flex-shrink: 0;
  margin-left: 16px;
}

/* --- Vertical Mode Styles --- */
.mode-vertical {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0;
  overflow: hidden;
}

.header-top-actions {
  flex-shrink: 0;
  margin-bottom: 15px;
}

.expand-btn {
  color: var(--el-text-color-regular);
}

.expand-btn:hover {
  color: var(--el-color-primary);
}

.title-section {
  flex-grow: 1;
  display: flex;
  justify-content: center;
  overflow: hidden;
  min-width: 0;
}

.mode-horizontal .title-section {
  justify-content: flex-start;
  width: auto;
}

.vertical-title-wrapper {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: 2px;
  display: flex;
  align-items: center;
  padding: 10px 0;
}

.header-bottom-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 15px;
}

.action-btn {
  margin-left: 0 !important;
}

.chat-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-heading);
}

.mode-horizontal .chat-title {
  font-size: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.popover-edit-content {
  display: flex;
  gap: 8px;
}
</style>
