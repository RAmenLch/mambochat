<!-- frontend/mambo/src/mobile/components/chat/MobileChatNavigator.vue — 会话内用户消息快速定位（移动端：悬浮入口 + 底部面板） -->
<template>
  <div v-if="showNavigator" class="navigator-fab" @click.stop="openSheet">
    <el-icon :size="16"><Tickets /></el-icon>
    <span class="fab-count">{{ userMessages.length }}</span>
  </div>

  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="sheetVisible" class="navigator-overlay" @click="sheetVisible = false">
        <div class="navigator-panel" @click.stop>
          <div class="sheet-handle"></div>
          <div class="panel-header">
            <span>{{ t('chat.navigator.title') }}</span>
            <span class="count">{{ t('chat.navigator.count', { count: userMessages.length }) }}</span>
          </div>
          <div class="panel-list" ref="listRef">
            <button
              v-for="msg in userMessages"
              :key="msg.id"
              class="list-item"
              :class="{ 'is-active': msg.id === activeMessageId }"
              @click="handleClick(msg.id)"
            >
              <span class="dot"></span>
              <span class="text">{{ getMessageSummary(msg) }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tickets } from '@element-plus/icons-vue'
import type { Message } from '@/api/types'

const props = defineProps<{
  messages: Message[]
  /** 当前视口顶部的用户消息 ID */
  activeMessageId: string | null
}>()

const emit = defineEmits<{
  (e: 'jump', messageId: string): void
}>()

const { t } = useI18n()

const sheetVisible = ref(false)
const listRef = ref<HTMLElement | null>(null)

const userMessages = computed(() => props.messages.filter(m => m.role === 'user'))

/** 用户消息过少时无需导航入口 */
const showNavigator = computed(() => userMessages.value.length > 3)

function getMessageSummary(message: Message): string {
  const textSub = message.sub_messages.find(sm => sm.type === 'Normal' || sm.type === 'File')
  if (!textSub) return '...'
  const text = textSub.content.trim()
  return text.length <= 20 ? text : `${text.substring(0, 20)}...`
}

function openSheet() {
  sheetVisible.value = true
  nextTick(() => {
    const container = listRef.value
    if (!container) return
    const active = container.querySelector('.list-item.is-active') as HTMLElement | null
    active?.scrollIntoView({ block: 'center' })
  })
}

function handleClick(messageId: string) {
  sheetVisible.value = false
  emit('jump', messageId)
}
</script>

<style scoped>
.navigator-fab {
  position: absolute;
  right: 8px;
  bottom: 12px;
  z-index: 5;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border-radius: 999px;
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  color: var(--el-text-color-secondary);
  font-size: 11px;
  opacity: 0.9;
}

.fab-count {
  line-height: 1;
}

.navigator-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background-color: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
}

.navigator-panel {
  width: 100%;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color);
  border-radius: 16px 16px 0 0;
  padding-bottom: env(safe-area-inset-bottom);
}

.sheet-handle {
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background-color: var(--el-border-color);
  margin: 8px auto 4px;
  flex-shrink: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
}

.count {
  font-size: 11px;
  background-color: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--el-text-color-secondary);
}

.panel-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 0;
}

.list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 16px;
  background: transparent;
  border: none;
  text-align: left;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.list-item:active {
  background-color: var(--el-fill-color-light);
}

.list-item.is-active {
  color: var(--el-color-primary);
  font-weight: 600;
  background-color: var(--el-color-primary-light-9);
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}

.list-item.is-active .dot {
  background-color: var(--el-color-primary);
}

.text {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.2s ease;
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
</style>
