<!-- frontend/mambo/src/mobile/components/chat/ChatHeader.vue -->
<template>
  <div class="mobile-chat-header">
    <!-- 左侧：菜单按钮 -->
    <div class="header-left">
      <el-button link @click="$emit('toggle-drawer')" class="icon-btn">
        <el-icon :size="24"><MenuIcon /></el-icon>
      </el-button>
    </div>

    <!-- 中间：标题 -->
    <div class="header-center">
      <div class="title-wrapper" @click="startEdit" v-if="!isEditing">
        <h3 class="mobile-title">{{ currentChat?.name || $t('chat.header.noChat') }}</h3>
      </div>
      <el-input
        v-else
        ref="inputRef"
        v-model="editName"
        size="small"
        @blur="saveTitle"
        @keydown.enter="saveTitle"
      />
    </div>

    <!-- 右侧：操作菜单 -->
    <div class="header-right">
      <el-dropdown trigger="click" @command="handleCommand">
        <el-button link class="icon-btn">
          <el-icon :size="20"><MoreFilled /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="newChat" :icon="Plus">{{
              $t('chat.sidebar.newChat')
            }}</el-dropdown-item>
            <el-dropdown-item command="refreshTitle" :icon="Refresh" divided>{{
              $t('chat.header.refreshTitle')
            }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { Menu as MenuIcon, MoreFilled, Plus, Refresh } from '@element-plus/icons-vue' // 移除了 Tools
import type { Chat } from '@/api/types'
import { useChatListStore } from '@/stores/chatListStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'

const props = defineProps<{
  currentChat: Chat | null
}>()

const emit = defineEmits<{
  (e: 'toggle-drawer'): void
}>()

const { t } = useI18n()
const chatListStore = useChatListStore()
const chatSessionStore = useChatSessionStore()

const isEditing = ref(false)
const editName = ref('')
const inputRef = ref()

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

async function handleCommand(command: string) {
  if (command === 'newChat') {
    const newChat = await chatListStore.createNewItem({
      name: t('chat.sidebar.initChatName'),
      itemType: 'chat',
      parentId: null,
    })
    if (newChat) {
      await chatSessionStore.selectChat(newChat.id)
    }
  } else if (command === 'refreshTitle' && props.currentChat) {
    chatListStore.refreshChatTitle(props.currentChat.id)
  }
}
</script>

<style scoped>
.mobile-chat-header {
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 5px;
  background-color: var(--color-background);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  padding-top: env(safe-area-inset-top);
}

.header-left,
.header-right {
  width: 40px;
  display: flex;
  justify-content: center;
}

.header-center {
  flex-grow: 1;
  text-align: center;
  margin: 0 10px;
  overflow: hidden;
  display: flex;
  justify-content: center;
}

.title-wrapper {
  max-width: 100%;
}

.mobile-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-heading);
}

.icon-btn {
  color: var(--el-text-color-primary);
}
</style>
