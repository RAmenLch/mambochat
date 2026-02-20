<!-- frontend/mambo/src/mobile/components/chat/ChatList.vue -->
<template>
  <div class="mobile-chat-list">
    <div class="list-header">
      <span>{{ $t('chat.sidebar.title') }}</span>
      <div class="header-actions">
        <el-button link :icon="FolderAdd" @click="handleNewFolder(null)" class="icon-btn" />
        <el-button link :icon="Plus" @click="handleNewChat(null)" class="icon-btn" />
      </div>
    </div>

    <div class="tree-container">
      <ExplorerTree
        ref="treeRef"
        :data="treeData"
        :current-id="currentChatId"
        :is-loading="isChatListLoading"
        :loading-folder-ids="loadingFolders"
        folder-item-type="folder"
        class="chat-tree"
        @node-click="handleNodeClick"
        @node-expand="handleNodeExpand"
      >
        <!-- 使用 item-icon 插槽 -->
        <template #item-icon="{ data }">
          <el-icon>
            <Folder v-if="data.itemType === 'folder'" />
            <ChatDotRound v-else />
          </el-icon>
        </template>

        <!-- 使用新的 item-suffix 插槽放置菜单按钮 -->
        <template #item-suffix="{ data }">
          <div class="node-actions" @click.stop="openContextMenu(data)">
            <el-icon><MoreFilled /></el-icon>
          </div>
        </template>
      </ExplorerTree>
    </div>

    <div class="mobile-footer">
      <el-button :icon="Setting" circle @click="goToSettings" size="large" />
    </div>

    <!-- 底部动作面板 -->
    <el-drawer
      v-model="contextMenuVisible"
      direction="btt"
      :show-close="false"
      :with-header="false"
      size="auto"
      class="context-menu-drawer"
    >
      <div class="context-menu-list" v-if="selectedContextItem">
        <div class="menu-header">
          <span class="menu-title">{{ selectedContextItem.name }}</span>
        </div>

        <div
          class="menu-item"
          v-if="selectedContextItem.itemType === 'folder'"
          @click="handleExpandFolder"
        >
          <el-icon><Expand v-if="!isExpanded(selectedContextItem.id)" /><Fold v-else /></el-icon>
          <span>{{
            isExpanded(selectedContextItem.id)
              ? $t('common.action.collapse')
              : $t('common.action.expand')
          }}</span>
        </div>

        <div class="menu-item" @click="handleContextAction('rename')">
          <el-icon><EditPen /></el-icon>
          <span>{{ $t('chat.sidebar.rename') }}</span>
        </div>

        <div
          class="menu-item"
          v-if="selectedContextItem.itemType === 'chat'"
          @click="handleContextAction('duplicate')"
        >
          <el-icon><CopyDocument /></el-icon>
          <span>{{ $t('chat.sidebar.duplicate') }}</span>
        </div>

        <div class="menu-item" @click="handleContextAction('move')">
          <el-icon><Rank /></el-icon>
          <span>{{ $t('chat.sidebar.move') }}</span>
        </div>

        <el-divider />

        <template v-if="selectedContextItem.itemType === 'folder'">
          <div class="menu-item" @click="handleNewChat(selectedContextItem.id)">
            <el-icon><Plus /></el-icon>
            <span>{{ $t('chat.sidebar.newChat') }}</span>
          </div>
          <div class="menu-item" @click="handleNewFolder(selectedContextItem.id)">
            <el-icon><FolderAdd /></el-icon>
            <span>{{ $t('chat.sidebar.newFolder') }}</span>
          </div>
          <el-divider />
        </template>

        <div class="menu-item" @click="handleContextAction('search')">
          <el-icon><Search /></el-icon>
          <span>{{ $t('chat.sidebar.search') }}</span>
        </div>

        <div class="menu-item danger" @click="handleContextAction('delete')">
          <el-icon><Delete /></el-icon>
          <span>{{ $t('chat.sidebar.delete') }}</span>
        </div>

        <div class="menu-cancel" @click="contextMenuVisible = false">
          {{ $t('common.action.cancel') }}
        </div>
      </div>
    </el-drawer>

    <!-- 重命名/新建 输入弹窗 -->
    <EntityFormDialog
      v-model:visible="dialogState.visible.value"
      :title="dialogProps.title"
      :initial-name="dialogProps.initialName"
      @confirm="onDialogConfirm"
    />

    <!-- 移动目标选择弹窗 -->
    <MoveTargetDialog
      v-model:visible="moveDialogVisible"
      :item-to-move="selectedContextItem"
      :tree-data="folderTreeData"
      @confirm="handleMoveConfirm"
    />

    <!-- 搜索弹窗 -->
    <SearchDialog
      v-model:visible="searchDialogVisible"
      :root-id="searchRootId"
      @select-result="handleSearchResultSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Folder,
  ChatDotRound,
  Setting,
  MoreFilled,
  EditPen,
  Delete,
  Plus,
  CopyDocument,
  FolderAdd,
  Rank,
  Search,
  Expand,
  Fold,
} from '@element-plus/icons-vue'
import ExplorerTree from '@/components/common/ExplorerTree.vue'
import EntityFormDialog from '@/components/common/EntityFormDialog.vue'
import MoveTargetDialog from './dialogs/MoveTargetDialog.vue'
import SearchDialog from './dialogs/SearchDialog.vue'
import { useChatListStore } from '@/stores/chatListStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { buildChatTree } from '@/utils/treeHelper'
import type { BaseTreeItem, ChatNode, MoveRequest } from '@/api/types'
import { ElMessageBox, ElMessage } from 'element-plus'

const emit = defineEmits<{
  (e: 'close-drawer'): void
}>()

const { t } = useI18n()
const router = useRouter()
const chatListStore = useChatListStore()
const chatSessionStore = useChatSessionStore()
const treeRef = ref<InstanceType<typeof ExplorerTree>>()

const { chatList, isChatListLoading, loadingFolders, loadedFolderIds } = storeToRefs(chatListStore)
const { currentChatId } = storeToRefs(chatSessionStore)

const treeData = computed(
  () => buildChatTree(chatList.value, loadedFolderIds.value) as unknown as BaseTreeItem[],
)

const folderTreeData = computed(
  () => buildChatTree(chatList.value, loadedFolderIds.value) as ChatNode[],
)

const expandedFolderIds = ref<Set<string>>(new Set())

// Context Menu State
const contextMenuVisible = ref(false)
const selectedContextItem = ref<BaseTreeItem | null>(null)

// Dialog State
const dialogState = { visible: ref(false) }
const dialogProps = ref({
  title: '',
  initialName: '',
  type: '',
  contextItem: null as BaseTreeItem | null,
})

// Move Dialog State
const moveDialogVisible = ref(false)

// Search Dialog State
const searchDialogVisible = ref(false)
const searchRootId = ref<string | null>(null)

onMounted(() => {
  chatListStore.initializeList()
})

// --- Tree Interaction ---

const isExpanded = (id: string) => expandedFolderIds.value.has(id)

const handleExpandFolder = () => {
  if (!selectedContextItem.value) return
  const id = selectedContextItem.value.id
  if (isExpanded(id)) {
    expandedFolderIds.value.delete(id)
  } else {
    expandedFolderIds.value.add(id)
  }
  expandedFolderIds.value = new Set(expandedFolderIds.value)
  contextMenuVisible.value = false
}

const handleNodeClick = async (data: BaseTreeItem) => {
  if (data.itemType === 'chat') {
    await chatSessionStore.selectChat(data.id)
    emit('close-drawer')
  } else if (data.itemType === 'folder') {
    if (isExpanded(data.id)) {
      expandedFolderIds.value.delete(data.id)
    } else {
      expandedFolderIds.value.add(data.id)
    }
    expandedFolderIds.value = new Set(expandedFolderIds.value)
  }
}

const handleNodeExpand = (data: BaseTreeItem) => {
  if (data.itemType === 'folder') {
    // Fix: Pass data.id instead of data object
    chatListStore.fetchChatChildren(data.id)
    expandedFolderIds.value.add(data.id)
  }
}

const openContextMenu = (data: BaseTreeItem) => {
  selectedContextItem.value = data
  contextMenuVisible.value = true
}

// --- CRUD Operations ---

const handleNewChat = async (parentId: string | null) => {
  const finalParentId =
    parentId ||
    (selectedContextItem.value?.itemType === 'folder' ? selectedContextItem.value.id : null)
  const newItem = await chatListStore.createNewItem({
    name: t('chat.sidebar.initChatName'),
    itemType: 'chat',
    parentId: finalParentId,
  })
  contextMenuVisible.value = false
  if (newItem) {
    await chatSessionStore.selectChat(newItem.id)
    emit('close-drawer')
  }
}

const handleNewFolder = (parentId: string | null) => {
  const finalParentId =
    parentId ||
    (selectedContextItem.value?.itemType === 'folder' ? selectedContextItem.value.id : null)
  dialogProps.value = {
    title: t('chat.sidebar.newFolder'),
    initialName: t('chat.sidebar.initFolderName'),
    type: 'newFolder',
    contextItem: selectedContextItem.value,
  }
  ;(dialogProps.value as any).parentId = finalParentId
  dialogState.visible.value = true
  contextMenuVisible.value = false
}

// --- Context Menu Actions ---

const handleContextAction = async (action: string) => {
  contextMenuVisible.value = false
  if (!selectedContextItem.value) return

  const item = selectedContextItem.value

  if (action === 'delete') {
    try {
      await ElMessageBox.confirm(t('chat.sidebar.deleteConfirm'), t('common.action.delete'), {
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      })
      await chatListStore.deleteItem(item.id)
      if (currentChatId.value === item.id) {
        // Fix: Pass empty string instead of null
        chatSessionStore.selectChat('')
      }
      ElMessage.success(t('common.msg.deleteSuccess'))
    } catch {}
  } else if (action === 'rename') {
    dialogProps.value = {
      title: t('chat.sidebar.rename'),
      initialName: item.name,
      type: 'rename',
      contextItem: item,
    }
    dialogState.visible.value = true
  } else if (action === 'duplicate') {
    // Fix: Use optional chaining
    const newItem = await chatListStore.duplicateChat?.(item.id)
    if (newItem) {
      ElMessage.success(t('common.msg.duplicateSuccess'))
    }
  } else if (action === 'move') {
    moveDialogVisible.value = true
  } else if (action === 'search') {
    searchRootId.value = item.itemType === 'folder' ? item.id : item.parentId
    searchDialogVisible.value = true
  }
}

const handleMoveConfirm = async (targetId: string) => {
  if (!selectedContextItem.value) return

  const moveRequest: MoveRequest = {
    item_ids: [selectedContextItem.value.id],
    reference_id: targetId,
    action: 'inside',
  }

  try {
    await chatListStore.moveChatItem(moveRequest)
    ElMessage.success(t('common.msg.moveSuccess'))

    // Fix: Pass targetId string directly
    if (targetId !== 'root') {
      chatListStore.fetchChatChildren(targetId)
    }
  } catch (error) {
    ElMessage.error(t('common.error.moveFailed'))
  }
}

const handleSearchResultSelect = async (data: { chatId: string; subMessageId: string | null }) => {
  if (data.subMessageId) {
    chatSessionStore.setSearchTarget(data.subMessageId)
  }
  await chatListStore.resolvePath(data.chatId)
  await chatSessionStore.selectChat(data.chatId)
  emit('close-drawer')
}

const onDialogConfirm = async (payload: { name: string }) => {
  const { type, contextItem } = dialogProps.value
  const parentId = (dialogProps.value as any).parentId

  if (type === 'rename' && contextItem) {
    await chatListStore.updateChatSettings(contextItem.id, { name: payload.name })
    ElMessage.success(t('common.msg.updateSuccess'))
  } else if (type === 'newFolder') {
    const newItem = await chatListStore.createNewItem({
      name: payload.name,
      itemType: 'folder',
      parentId: parentId || null,
    })
    if (newItem) {
      ElMessage.success(t('common.msg.createSuccess'))
    }
  }
}

const goToSettings = () => {
  router.push('/settings')
  emit('close-drawer')
}
</script>

<style scoped>
.mobile-chat-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft);
}

.list-header {
  padding: 15px;
  font-weight: bold;
  font-size: 18px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 0;
}

.icon-btn {
  margin-left: 5px;
  padding: 8px;
}

.tree-container {
  flex-grow: 1;
  overflow-y: auto;
  padding: 10px 0;
}

/* 修正：使用 :deep() 穿透到子组件样式 */
:deep(.node-actions) {
  padding: 10px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  cursor: pointer;
}

.mobile-footer {
  padding: 15px;
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: center;
  padding-bottom: calc(15px + env(safe-area-inset-bottom));
}

/* Context Menu Drawer Styles */
.context-menu-list {
  padding: 0 0 20px 0;
  background: var(--color-background);
}

.menu-header {
  padding: 15px;
  text-align: center;
  border-bottom: 1px solid var(--color-border);
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.menu-item {
  padding: 15px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
}

.menu-item:active {
  background-color: var(--el-fill-color-light);
}

.menu-item.danger {
  color: var(--el-color-danger);
}

.el-divider {
  margin: 5px 0;
}

.menu-cancel {
  margin-top: 10px;
  padding: 15px;
  text-align: center;
  font-weight: bold;
  border-top: 5px solid var(--el-fill-color-light);
  background: var(--color-background-soft);
  cursor: pointer;
}
</style>
