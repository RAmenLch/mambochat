<!-- frontend/mambo/src/components/chat/ChatNavigator.vue -->
<template>
  <div
    v-if="showNavigator"
    class="chat-navigator"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
  >
    <!-- 细条轨道 (始终显示) -->
    <div class="navigator-track">
      <div
        v-for="msg in visibleUserMessages"
        :key="msg.id"
        class="track-item"
        :class="{
          'is-active': msg.id === activeMessageId,
          'is-hovered': msg.id === hoveredMessageId
        }"
        @click="handleClick(msg.id)"
        @mouseenter.stop="hoveredMessageId = msg.id"
        @mouseleave.stop="hoveredMessageId = null"
      >
        <div class="item-bar"></div>
      </div>
    </div>

    <!-- 悬浮展开区域 (仅悬停时显示) -->
    <transition name="fade-slide">
      <div v-if="isPanelVisible" class="navigator-panel">
        <div class="panel-header">
          <span>会话导航</span>
          <span class="count">{{ userMessages.length }} 条对话</span>
        </div>
        <div class="panel-list">
          <div
            v-for="msg in visibleUserMessages"
            :key="'list-' + msg.id"
            class="list-item"
            :class="{ 'is-active': msg.id === activeMessageId }"
            @click="handleClick(msg.id)"
          >
            <span class="dot"></span>
            <span class="text">{{ getMessageSummary(msg) }}</span>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Message } from '@/api/types'

const props = defineProps<{
  messages: Message[]
  activeMessageId: string | null // 当前视口活跃的消息ID
}>()

const emit = defineEmits<{
  (e: 'jump', messageId: string): void
}>()

const isHovered = ref(false)
const hoveredMessageId = ref<string | null>(null)
let hideTimer: ReturnType<typeof setTimeout> | null = null;

// 过滤出用户消息
const userMessages = computed(() => {
  return props.messages.filter(m => m.role === 'user')
})

// 计算需要展示的消息（前后10条，最多21条）
const visibleUserMessages = computed(() => {
  const all = userMessages.value;
  if (all.length <= 21) return all;

  let activeIndex = all.findIndex(m => m.id === props.activeMessageId);
  if (activeIndex === -1) activeIndex = all.length - 1;

  let start = activeIndex - 10;
  let end = activeIndex + 11;

  if (start < 0) {
    end += Math.abs(start);
    start = 0;
  }
  if (end > all.length) {
    start -= (end - all.length);
    end = all.length;
  }
  start = Math.max(0, start);

  return all.slice(start, end);
})

// 只有超过3条用户消息才显示
const showNavigator = computed(() => userMessages.value.length > 3)

// 控制面板显示逻辑
const isPanelVisible = computed(() => isHovered.value)

// 防抖处理
function handleMouseEnter() {
  if (hideTimer) clearTimeout(hideTimer);
  isHovered.value = true;
}

function handleMouseLeave() {
  // 延迟隐藏，防止鼠标在条目和面板间移动时闪烁
  hideTimer = setTimeout(() => {
    isHovered.value = false;
    hoveredMessageId.value = null;
  }, 200);
}

// 获取消息摘要（取前15个字符）
function getMessageSummary(message: Message): string {
  const textSub = message.sub_messages.find(sm => sm.type === 'Normal' || sm.type === 'File')
  if (!textSub) return '...'
  const text = textSub.content.trim()
  if (text.length <= 15) return text
  return text.substring(0, 15) + '...'
}

function handleClick(messageId: string) {
  emit('jump', messageId)
}
</script>

<style scoped>
.chat-navigator {
  position: absolute;
  top: 0;
  bottom: 0;
  right: 16px; /* 向左挪挪，避开原生滚动条 */
  width: 24px;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  pointer-events: none; /* 整体穿透，避免挡住滚动条的点击 */
}

/* 轨道样式 */
.navigator-track {
  position: relative;
  display: flex;
  flex-direction: column;
  pointer-events: auto; /* 轨道内部允许交互 */
  background-color: transparent;
  padding: 8px 0; /* 与面板列表的 padding 保持一致 */
}

.track-item {
  width: 24px;
  height: 28px; /* 固定高度，与列表项高度严格对齐 */
  display: flex;
  align-items: center;
  justify-content: flex-end;
  cursor: pointer;
}

/* 横细条 */
.item-bar {
  width: 12px;
  height: 3px;
  background-color: #c0c4cc;
  border-radius: 2px;
  transition: all 0.3s;
}

/* 当前视口消息高亮 (蓝色) */
.track-item.is-active .item-bar {
  background-color: var(--el-color-primary);
  width: 16px;
  height: 4px;
  box-shadow: 0 0 4px var(--el-color-primary-light-5);
}

/* 悬停高亮 (黑色)，优先级低于 Active */
.track-item.is-hovered:not(.is-active) .item-bar {
  background-color: #303133;
  width: 14px;
}

/* 展开面板样式 */
.navigator-panel {
  position: absolute;
  right: 32px; /* 在轨道左侧 */
  top: 50%;
  transform: translateY(-50%);
  width: 200px;
  background-color: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: -1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  pointer-events: auto; /* 面板允许交互 */
}

.panel-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.count {
  font-size: 10px;
  background-color: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 4px;
}

.panel-list {
  padding: 8px 0;
  flex: 1;
  /* 去掉 overflow-y: auto，使滚轮事件自然冒泡到外层聊天记录 */
}

.list-item {
  padding: 0 12px 0 20px;
  position: relative;
  font-size: 13px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  transition: background-color 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  height: 28px; /* 固定高度，与轨道项高度严格对齐 */
  display: flex;
  align-items: center;
}

.list-item:hover {
  background-color: var(--el-fill-color-light);
}

.list-item.is-active {
  color: var(--el-color-primary);
  font-weight: 600;
  background-color: var(--el-color-primary-light-9);
}

.list-item .dot {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--el-text-color-placeholder);
}

.list-item.is-active .dot {
  background-color: var(--el-color-primary);
  width: 6px;
  height: 6px;
  left: 9px;
}

/* 动画 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-50%) translateX(10px);
}
</style>
