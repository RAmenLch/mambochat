<!-- frontend/mambo/src/mobile/components/chat/ChatHeader.vue -->
<template>
  <div class="mobile-chat-header">
    <div class="header-left">
      <button class="icon-btn" @click="$emit('toggle-drawer')" :aria-label="$t('chat.sidebar.title')">
        <el-icon :size="22"><MenuIcon /></el-icon>
      </button>
    </div>

    <div class="header-center">
      <div class="title-wrapper" @click="startEdit" v-if="!isEditing">
        <span class="mobile-title">{{ currentChat?.name || $t('chat.header.noChat') }}</span>
        <span class="mobile-subtitle" v-if="currentChat && displayModelName">
          {{ displayModelName }}
        </span>
      </div>
      <el-input
        v-else
        ref="inputRef"
        v-model="editName"
        size="small"
        class="title-input"
        @blur="saveTitle"
        @keydown.enter="saveTitle"
      />
    </div>

    <div class="header-right">
      <button class="icon-btn" @click="$emit('open-settings')" :aria-label="$t('chat.settings.title')">
        <el-icon :size="20"><SettingIcon /></el-icon>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { Menu as MenuIcon, Setting as SettingIcon } from '@element-plus/icons-vue'
import type { Chat } from '@/api/types'
import { useChatListStore } from '@/stores/chatListStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useProviderStore } from '@/stores/providerStore'
import { useAgentStore } from '@/stores/agentStore'

const props = defineProps<{
  currentChat: Chat | null
}>()

const emit = defineEmits<{
  (e: 'toggle-drawer'): void
  (e: 'open-settings'): void
}>()

const { t } = useI18n()
const chatListStore = useChatListStore()
const chatSessionStore = useChatSessionStore()
const providerStore = useProviderStore()
const agentStore = useAgentStore()

const isEditing = ref(false)
const editName = ref('')
const inputRef = ref()

const displayModelName = computed(() => {
  const chat = props.currentChat
  if (chat?.chatMode === 'agent') {
    if (chat.agentId) {
      const agent = agentStore.allAgents.find(a => a.id === chat.agentId)
      if (agent) return agent.name
    }
    return ''
  }
  if (!chat?.aiModelId) return ''
  const model = providerStore.allModels.find((m) => m.id === chat.aiModelId)
  return model ? model.name : ''
})

function startEdit() {
  if (!props.currentChat) return
  editName.value = props.currentChat.name
  isEditing.value = true
  nextTick(() => inputRef.value?.focus())
}

async function saveTitle() {
  if (props.currentChat && editName.value.trim() && editName.value !== props.currentChat.name) {
    await chatListStore.updateChatSettings(props.currentChat.id, { name: editName.value })
  }
  isEditing.value = false
}
</script>

<style scoped>
.mobile-chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 4px;
  padding-top: env(safe-area-inset-top);
  background-color: rgba(255, 255, 255, 0.72);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
  z-index: 10;
}

.header-left,
.header-right {
  width: 44px;
  display: flex;
  justify-content: center;
  align-items: center;
  flex-shrink: 0;
}

.header-center {
  flex: 1;
  min-width: 0;
  display: flex;
  justify-content: center;
  align-items: center;
}

.title-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 100%;
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.mobile-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-heading);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
  line-height: 1.3;
}

.mobile-subtitle {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
  margin-top: 1px;
}

.title-input {
  max-width: 200px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 50%;
  color: var(--el-text-color-primary);
  cursor: pointer;
  transition: background-color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.icon-btn:active {
  background-color: rgba(0, 0, 0, 0.06);
}

@media (prefers-color-scheme: dark) {
  .mobile-chat-header {
    background-color: rgba(30, 30, 30, 0.72);
    border-bottom-color: rgba(255, 255, 255, 0.08);
  }

  .icon-btn:active {
    background-color: rgba(255, 255, 255, 0.08);
  }
}
</style>
