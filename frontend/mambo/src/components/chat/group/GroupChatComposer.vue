<!-- frontend/mambo/src/components/chat/group/GroupChatComposer.vue -->
<template>
  <div class="group-composer" :style="{ height: `${composerHeight}px` }">
    <div class="resize-handle" @mousedown.prevent="startResizeComposer"></div>

    <!-- 顶部信息行：与普通会话输入区上方的工具条对齐 -->
    <div class="composer-toolbar">
      <div class="recipient-hint">
        <template v-if="mentionedNames.length">
          <el-tag v-for="n in mentionedNames" :key="n" size="small" class="recipient-tag">{{ n }}</el-tag>
        </template>
        <span v-else class="broadcast-hint">{{ $t('groupChat.window.broadcastHint') }}</span>
      </div>
      <span class="mention-tip">
        <span class="mention-at">@</span>
        {{ $t('groupChat.window.mentionHint') }}
      </span>
    </div>

    <div class="composer-body">
      <div class="editor-wrapper">
        <el-input
          ref="textareaRef"
          v-model="content"
          type="textarea"
          :rows="1"
          resize="none"
          :disabled="disabled"
          :placeholder="$t('groupChat.window.composerPlaceholder')"
          @input="refreshMentionState"
          @click="refreshMentionState"
          @keydown="onKeydown"
          @keyup="onKeyup"
          @blur="closeMentions"
        />

        <transition name="el-zoom-in-bottom">
          <div v-if="suggestionOpen && suggestions.length" class="mention-popup">
            <div class="mention-popup-title">{{ $t('groupChat.window.mentionSuggestTitle') }}</div>
            <div
              v-for="(m, idx) in suggestions"
              :key="m.chatId"
              class="mention-item"
              :class="{ 'is-active': idx === activeIndex }"
              @mousedown.prevent="applySuggestion(idx)"
              @mouseenter="activeIndex = idx"
            >
              <span class="mention-alias">@{{ m.memberAlias }}</span>
              <span class="mention-name">{{ m.agentName || m.name }}</span>
            </div>
          </div>
        </transition>
      </div>

      <el-tooltip
        :content="mentionedNames.length ? $t('groupChat.window.send') : $t('groupChat.window.sendBroadcast')"
        placement="top"
      >
        <el-button
          type="primary"
          class="action-button"
          :disabled="disabled || !content.trim()"
          @click="onSend"
        >
          <el-icon><Promotion /></el-icon>
        </el-button>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue';
import { Promotion } from '@element-plus/icons-vue';
import { useResizablePanels } from '@/composables/useResizablePanels';
import type { GroupMember } from '@/api/types/groupChatTypes';

const props = defineProps<{
  members: GroupMember[];
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'send', payload: { content: string; recipientNames: string[] }): void;
}>();

const content = ref('');
const textareaRef = ref();

// --- 高度可拖拽（与普通会话输入区一致的交互与上下限） ---
const MIN_COMPOSER_HEIGHT = 110;
const MAX_COMPOSER_HEIGHT = 600;
const composerHeight = ref(150);
// 群输入框不做“拖到折叠”，拖到最小高度即回弹到 min
const neverCollapsed = ref(false);
const { startResize: startResizeComposer } = useResizablePanels(
  composerHeight,
  neverCollapsed,
  {
    min: MIN_COMPOSER_HEIGHT,
    max: MAX_COMPOSER_HEIGHT,
    orientation: 'vertical',
    inverted: true,
    snapThreshold: -1,
  },
);

// --- @ 补全 ---
const suggestionOpen = ref(false);
const mentionQuery = ref('');
const activeIndex = ref(0);
const MAX_SUGGESTIONS = 8;

const candidates = computed(() =>
  // 保留成员 Master（= 用户本人）不是生成目标，不作为 @ 提及候选
  props.members.filter((m) => !m.isUser && !!(m.memberAlias || '').trim()),
);

const suggestions = computed(() => {
  const query = mentionQuery.value.trim().toLowerCase();
  const list = candidates.value;
  if (!query) return list.slice(0, MAX_SUGGESTIONS);
  const starts: GroupMember[] = [];
  const contains: GroupMember[] = [];
  for (const m of list) {
    const alias = m.memberAlias.toLowerCase();
    const name = (m.agentName || m.name || '').toLowerCase();
    if (alias.startsWith(query) || name.startsWith(query)) {
      starts.push(m);
    } else if (alias.includes(query) || name.includes(query)) {
      contains.push(m);
    }
  }
  return [...starts, ...contains].slice(0, MAX_SUGGESTIONS);
});

function getTextarea(): HTMLTextAreaElement | null {
  const el = textareaRef.value?.$el as HTMLElement | undefined;
  return (el?.querySelector('textarea') as HTMLTextAreaElement) || null;
}

function closeMentions() {
  suggestionOpen.value = false;
  mentionQuery.value = '';
  activeIndex.value = 0;
}

/** 根据光标位置判断是否处于 `@别名` 提及模式 */
function refreshMentionState() {
  const ta = getTextarea();
  if (!ta) return closeMentions();
  const caret = ta.selectionStart ?? content.value.length;
  const before = content.value.slice(0, caret);
  const at = before.lastIndexOf('@');
  if (at === -1) return closeMentions();
  const query = before.slice(at + 1);
  // 空格 / 换行 / 又一个 @ / 中文标点表示该提及已结束；查询词为空时展示全部成员
  if (/[\s@，,。.！!？?：:]/.test(query) || query.length > 64) {
    return closeMentions();
  }
  mentionQuery.value = query;
  suggestionOpen.value = true;
  activeIndex.value = 0;
}

function onKeydown(e: Event) {
  const evt = e as KeyboardEvent;
  if (suggestionOpen.value && suggestions.value.length) {
    if (evt.key === 'ArrowDown') {
      evt.preventDefault();
      activeIndex.value = (activeIndex.value + 1) % suggestions.value.length;
      return;
    }
    if (evt.key === 'ArrowUp') {
      evt.preventDefault();
      activeIndex.value =
        (activeIndex.value - 1 + suggestions.value.length) % suggestions.value.length;
      return;
    }
    if (evt.key === 'Enter' || evt.key === 'Tab') {
      evt.preventDefault();
      applySuggestion(activeIndex.value);
      return;
    }
    if (evt.key === 'Escape') {
      evt.preventDefault();
      closeMentions();
      return;
    }
  }

  // 与普通会话一致：仅「无修饰键的 Enter」发送，Shift+Enter 换行
  if (evt.key === 'Enter' && !evt.shiftKey && !evt.ctrlKey && !evt.altKey && !evt.metaKey) {
    evt.preventDefault();
    onSend();
  }
}

function onKeyup(e: Event) {
  const evt = e as KeyboardEvent;
  // 左右移动光标后重新判断提及上下文
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(evt.key)) {
    refreshMentionState();
  }
}

/** 用选中的成员别名替换当前光标处的 `@查询词` */
function applySuggestion(idx: number) {
  const member = suggestions.value[idx];
  if (!member) return;
  const ta = getTextarea();
  const text = content.value;
  const caret = ta?.selectionStart ?? text.length;
  const before = text.slice(0, caret);
  const at = before.lastIndexOf('@');
  if (at === -1) return closeMentions();

  const insert = `@${member.memberAlias} `;
  content.value = text.slice(0, at) + insert + text.slice(caret);
  closeMentions();

  nextTick(() => {
    const position = at + insert.length;
    if (ta) {
      ta.focus();
      ta.setSelectionRange(position, position);
    }
  });
}

// --- 收件人解析与发送 ---
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * 结构化 @ 提及：按成员别名精确匹配 @别名，去重并保留成员顺序。
 * 未使用 @ 时返回空数组，后端将广播给全部成员。
 */
const mentionedNames = computed(() => {
  const text = content.value;
  if (!text.includes('@')) return [];
  const result: string[] = [];
  const seen = new Set<string>();
  for (const m of props.members) {
    const alias = m.memberAlias;
    if (!alias || seen.has(alias)) continue;
    const re = new RegExp(`@${escapeRegExp(alias)}(?=$|[\\s，,。.！!？?：:]|$)`);
    if (re.test(text)) {
      seen.add(alias);
      result.push(alias);
    }
  }
  return result;
});

function onSend() {
  if (props.disabled) return;
  const text = content.value.trim();
  if (!text) return;
  emit('send', { content: text, recipientNames: mentionedNames.value });
  content.value = '';
  closeMentions();
}
</script>

<style scoped>
.group-composer {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 6px 16px 10px;
  border-top: 1px solid var(--el-border-color-lighter);
  background-color: var(--color-background-soft);
  box-sizing: border-box;
}
.resize-handle {
  position: absolute;
  top: -3px;
  left: 0;
  width: 100%;
  height: 6px;
  cursor: ns-resize;
  z-index: 10;
}
.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 28px;
  flex-shrink: 0;
}
.recipient-hint {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  min-width: 0;
}
.broadcast-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.mention-tip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
/* @ 提及提示前缀（Element Plus 图标库没有“At”图标，用字符代替） */
.mention-at {
  font-weight: 600;
  color: var(--el-color-primary);
}
.composer-body {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: stretch;
  gap: 10px;
}
.editor-wrapper {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background-color: #ffffff;
  padding: 0 12px;
}
.editor-wrapper :deep(.el-textarea) {
  flex: 1;
  min-height: 0;
  display: flex;
}
.editor-wrapper :deep(.el-textarea__inner) {
  flex: 1;
  height: 100%;
  border: none;
  box-shadow: none;
  padding: 12px 0;
  background-color: transparent;
  resize: none;
  font-size: 14px;
  font-family: var(--el-font-family);
}
.action-button {
  width: 54px;
  font-size: 20px;
  flex-shrink: 0;
  align-self: stretch;
  height: auto;
  margin-left: 0;
}

/* --- @ 补全下拉 --- */
.mention-popup {
  position: absolute;
  left: -1px;
  right: -1px;
  bottom: calc(100% + 6px);
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
  background-color: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
  z-index: 30;
}
.mention-popup-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 4px 8px;
}
.mention-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.mention-item.is-active {
  background-color: var(--el-fill-color-light);
}
.mention-alias {
  color: var(--el-color-primary);
  font-weight: 500;
}
.mention-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
