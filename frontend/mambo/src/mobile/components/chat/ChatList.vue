<!-- frontend/mambo/src/mobile/components/chat/ChatList.vue -->
<template>
  <div class="mobile-chat-list">
    <div class="list-header">
      <span class="list-title">{{ $t('chat.sidebar.title') }}</span>
      <div class="header-actions">
        <button class="icon-btn" @click="toggleSortMode" :aria-label="isManualSort ? $t('chat.sidebar.sortByTime') : $t('chat.sidebar.sortManual')">
          <el-icon :size="18"><Sort /></el-icon>
        </button>
        <button class="icon-btn" @click="handleNewFolder(null)">
          <el-icon :size="18"><FolderAdd /></el-icon>
        </button>
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
        :custom-allow-drop="customAllowDrop"
        class="chat-tree"
        @node-click="handleNodeClick"
        @node-expand="handleNodeExpand"
      >
        <template #item-icon="{ data }">
          <el-icon :size="18">
            <Folder v-if="data.itemType === 'folder'" />
            <ChatDotRound v-else />
          </el-icon>
        </template>

        <template #item-suffix="{ data }">
          <div class="node-actions" @click.stop="openContextMenu(data)">
            <el-icon :size="16"><MoreFilled /></el-icon>
          </div>
        </template>
      </ExplorerTree>
    </div>

    <div class="mobile-footer">
      <button class="footer-btn" @click="goToSettings">
        <el-icon :size="20"><Setting /></el-icon>
      </button>

      <div class="fab-area">
        <Transition name="fab-pop">
          <div v-if="showFabMenu" class="fab-menu">
            <button class="fab-menu-btn" @click="handleNewAgent(); showFabMenu = false">
              <el-icon :size="18"><Service /></el-icon>
              <span>新建 Agent</span>
            </button>
            <button class="fab-menu-btn" @click="handleNewChat(null); showFabMenu = false">
              <el-icon :size="18"><ChatDotRound /></el-icon>
              <span>新建聊天</span>
            </button>
          </div>
        </Transition>
        <button
          class="fab-btn"
          :class="{ active: showFabMenu }"
          @click="showFabMenu = !showFabMenu"
        >
          <el-icon :size="24"><Plus /></el-icon>
        </button>
      </div>
    </div>

    <!-- Context Menu Sheet -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="contextMenuVisible" class="sheet-overlay" @click="contextMenuVisible = false">
          <div class="sheet-panel" @click.stop v-if="selectedContextItem">
            <div class="sheet-handle"></div>
            <div class="sheet-panel-title">{{ selectedContextItem.name }}</div>

            <div class="sheet-items">
              <button
                v-if="selectedContextItem.itemType === 'folder'"
                class="sheet-item"
                @click="handleExpandFolder"
              >
                <el-icon :size="20"><Expand v-if="!isExpanded(selectedContextItem.id)" /><Fold v-else /></el-icon>
                <span>{{ isExpanded(selectedContextItem.id) ? $t('common.action.collapse') : $t('common.action.expand') }}</span>
              </button>

              <button class="sheet-item" @click="handleContextAction('rename')">
                <el-icon :size="20"><EditPen /></el-icon>
                <span>{{ $t('chat.sidebar.rename') }}</span>
              </button>

              <button
                v-if="selectedContextItem.itemType === 'chat'"
                class="sheet-item"
                @click="handleContextAction('duplicate')"
              >
                <el-icon :size="20"><CopyDocument /></el-icon>
                <span>{{ $t('chat.sidebar.duplicate') }}</span>
              </button>

              <button class="sheet-item" @click="handleContextAction('move')">
                <el-icon :size="20"><Rank /></el-icon>
                <span>{{ $t('chat.sidebar.move') }}</span>
              </button>

              <div class="sheet-divider"></div>

              <template v-if="selectedContextItem.itemType === 'folder'">
                <button class="sheet-item" @click="handleNewChat(selectedContextItem.id)">
                  <el-icon :size="20"><Plus /></el-icon>
                  <span>{{ $t('chat.sidebar.newChat') }}</span>
                </button>
                <button class="sheet-item" @click="handleNewFolder(selectedContextItem.id)">
                  <el-icon :size="20"><FolderAdd /></el-icon>
                  <span>{{ $t('chat.sidebar.newFolder') }}</span>
                </button>
                <div class="sheet-divider"></div>
              </template>

              <button class="sheet-item" @click="handleContextAction('search')">
                <el-icon :size="20"><Search /></el-icon>
                <span>{{ $t('chat.sidebar.search') }}</span>
              </button>

              <button class="sheet-item danger" @click="handleContextAction('delete')">
                <el-icon :size="20"><Delete /></el-icon>
                <span>{{ $t('chat.sidebar.delete') }}</span>
              </button>
            </div>

            <button class="sheet-cancel-btn" @click="contextMenuVisible = false">
              {{ $t('common.action.cancel') }}
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>

    <EntityFormDialog
      v-model:visible="dialogState.visible.value"
      :title="dialogProps.title"
      :initial-name="dialogProps.initialName"
      @confirm="onDialogConfirm"
    />

    <MoveTargetDialog
      v-model:visible="moveDialogVisible"
      :item-to-move="selectedContextItem"
      :tree-data="folderTreeData"
      @confirm="handleMoveConfirm"
    />

    <SearchDialog
      v-model:visible="searchDialogVisible"
      :root-id="searchRootId"
      @select-result="handleSearchResultSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue' // [新增] 引入 watch
import { storeToRefs } from 'pinia'
import { useRouter, useRoute } from 'vue-router' // [新增] 引入 useRoute
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
  Sort,
  Service,
} from '@element-plus/icons-vue'
import type { AllowDropType } from 'element-plus/es/components/tree/src/tree.type'
/** Element Plus Tree 内部节点结构（避免依赖内部路径） */
interface ElTreeNode {
  data: Record<string, any>
  parent: ElTreeNode | null
  level: number
  childNodes: ElTreeNode[]
}
import ExplorerTree from '@/components/common/ExplorerTree.vue'
import EntityFormDialog from '@/components/common/EntityFormDialog.vue'
import MoveTargetDialog from './dialogs/MoveTargetDialog.vue'
import SearchDialog from './dialogs/SearchDialog.vue'
import { useChatListStore } from '@/stores/chatListStore'
import { useChatSessionStore, LAST_ACTIVE_CHAT_KEY } from '@/stores/chatSessionStore'
import { useAgentStore } from '@/stores/agentStore' // [新增] 引入 LAST_ACTIVE_CHAT_KEY
import { buildChatTree } from '@/utils/treeHelper'
import type { ChatSortMode } from '@/utils/treeHelper'
import type { BaseTreeItem, ChatNode, MoveRequest } from '@/api/types'
import { ElMessageBox, ElMessage } from 'element-plus'

const emit = defineEmits<{
  (e: 'close-drawer'): void
}>()

const { t } = useI18n()
const router = useRouter()
const route = useRoute() // [新增] 获取 route 实例
const chatListStore = useChatListStore()
const chatSessionStore = useChatSessionStore()
const agentStore = useAgentStore()
const treeRef = ref<InstanceType<typeof ExplorerTree>>()

const { chatList, isChatListLoading, loadingFolders, loadedFolderIds } = storeToRefs(chatListStore)
const { currentChatId } = storeToRefs(chatSessionStore)

const showFabMenu = ref(false)

// 排序模式
const SORT_MODE_KEY = 'mambo_chat_sort_mode';
const chatSortMode = ref<ChatSortMode>(
  (localStorage.getItem(SORT_MODE_KEY) as ChatSortMode) || 'manual'
);

const isManualSort = computed(() => chatSortMode.value === 'manual');

const customAllowDrop = (draggingNode: any, dropNode: any, dropType: AllowDropType): boolean => {
  if (isManualSort.value) return true;
  const isDropRoot = !(dropNode.data as BaseTreeItem).parentId;
  if (!isDropRoot) return true;
  const isDragFromSub = !!(draggingNode.data as BaseTreeItem).parentId;
  if (isDragFromSub) return true;
  return dropType === 'inner';
};

function toggleSortMode() {
  chatSortMode.value = chatSortMode.value === 'manual' ? 'folder-top-time' : 'manual';
  localStorage.setItem(SORT_MODE_KEY, chatSortMode.value);
}

const treeData = computed(
  () => buildChatTree(chatList.value, loadedFolderIds.value, chatSortMode.value) as unknown as BaseTreeItem[],
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

// --- Lifecycle & Initialization [修改] ---

onMounted(async () => {
  await chatListStore.initializeList()
  await router.isReady()

  // 1. 尝试从 URL 获取 ID
  let targetChatId = route.params.id as string

  // 2. 尝试从 URL Path 解析 (兼容性处理)
  if (!targetChatId) {
    const match = window.location.pathname.match(/\/chat\/([a-zA-Z0-9-]+)/)
    if (match && match[1]) {
      targetChatId = match[1]
    }
  }

  // 3. 尝试从 LocalStorage 获取最后一次活跃的 ID
  if (!targetChatId) {
    const lastActiveId = localStorage.getItem(LAST_ACTIVE_CHAT_KEY)
    if (lastActiveId) {
      targetChatId = lastActiveId
    }
  }

  // 4. 执行选中逻辑
  if (targetChatId) {
    // 确保路径上的文件夹已展开
    await chatListStore.resolvePath(targetChatId)
    await handleSelectChat(targetChatId)
    // 手机端不需要 scrollToKey，因为列表是在抽屉里的，或者可以按需添加
  }
})

// [新增] 监听路由变化，处理浏览器后退/前进按钮
watch(
  () => route.params.id,
  async (newId) => {
    if (newId && typeof newId === 'string') {
      if (currentChatId.value !== newId) {
        // 如果路由变了但 Store 没变，说明是浏览器导航，需要同步 Store
        const exists = chatList.value.some((c) => c.id === newId)
        if (!exists) {
          await chatListStore.resolvePath(newId)
        }
        await chatSessionStore.selectChat(newId)
      }
    }
  },
)

// --- Helper: 统一选中逻辑 [新增] ---
const handleSelectChat = async (chatId: string) => {
  await chatSessionStore.selectChat(chatId)

  // 核心修复：如果当前路由不是该 ID，则推入新路由
  if (route.params.id !== chatId) {
    router.push(`/chat/${chatId}`)
  }
}

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
    // [修改] 使用统一的选中方法，包含路由跳转
    await handleSelectChat(data.id)
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
    // [修改] 新建后跳转路由
    await handleSelectChat(newItem.id)
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

const handleNewAgent = async () => {
  const firstAgent = agentStore.allAgents[0]
  const newChat = await chatListStore.createNewItem({
    name: t('chat.sidebar.initChatName'),
    itemType: 'chat',
    chatMode: 'agent',
    agentId: firstAgent?.id ?? null,
    parentId: null,
  })
  if (newChat) {
    await handleSelectChat(newChat.id)
    emit('close-drawer')
  }
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
        chatSessionStore.selectChat('')
        router.push('/chat') // [新增] 删除当前会话后，清除 URL 上的 ID
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
  // [修改] 搜索选中后跳转路由
  await handleSelectChat(data.chatId)
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
  background: var(--color-background);
}

.list-header {
  padding: 12px 16px;
  padding-top: max(12px, env(safe-area-inset-top));
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 0.5px solid var(--el-border-color-lighter);
}

.list-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-heading);
  letter-spacing: -0.3px;
}

.header-actions {
  display: flex;
  gap: 4px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: background-color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.icon-btn:active {
  background: var(--el-fill-color-light);
}

.tree-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

:deep(.node-actions) {
  padding: 8px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  cursor: pointer;
  border-radius: 6px;
  transition: background-color 0.15s;
}

:deep(.node-actions:active) {
  background: var(--el-fill-color-light);
}

.mobile-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  padding-bottom: max(10px, env(safe-area-inset-bottom));
  border-top: 0.5px solid var(--el-border-color-lighter);
}

.footer-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: all 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.footer-btn:active {
  background: var(--el-fill-color);
  transform: scale(0.94);
}

.fab-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.4);
  transition: all 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.fab-btn:active {
  transform: scale(0.92);
  box-shadow: 0 2px 8px rgba(var(--el-color-primary-rgb, 64, 158, 255), 0.3);
}

.fab-btn.active {
  transform: rotate(45deg);
  background: var(--el-text-color-secondary);
}

.fab-area {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.fab-menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}

.fab-menu-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: none;
  border-radius: 20px;
  background: var(--color-background);
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  font-family: inherit;
  white-space: nowrap;
  transition: all 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.fab-menu-btn:active {
  background: var(--el-fill-color-light);
  transform: scale(0.96);
}

.fab-pop-enter-active {
  transition: all 0.2s ease-out;
}
.fab-pop-leave-active {
  transition: all 0.15s ease-in;
}
.fab-pop-enter-from,
.fab-pop-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

/* Bottom Sheet Styles */
.sheet-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 2000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.sheet-panel {
  width: 100%;
  max-width: 500px;
  background: var(--color-background);
  border-radius: 16px 16px 0 0;
  padding: 8px 16px;
  padding-bottom: max(16px, env(safe-area-inset-bottom));
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--el-border-color);
  border-radius: 2px;
  margin: 8px auto 12px;
}

.sheet-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  padding: 0 8px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sheet-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sheet-item {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 14px 8px;
  border: none;
  border-radius: 10px;
  background: transparent;
  font-size: 16px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  transition: background-color 0.15s;
  font-family: inherit;
  -webkit-tap-highlight-color: transparent;
}

.sheet-item:active {
  background: var(--el-fill-color-light);
}

.sheet-item.danger {
  color: var(--el-color-danger);
}

.sheet-divider {
  height: 1px;
  background: var(--el-border-color-lighter);
  margin: 6px 8px;
}

.sheet-cancel-btn {
  width: 100%;
  padding: 14px;
  margin-top: 8px;
  border: none;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  font-family: inherit;
  -webkit-tap-highlight-color: transparent;
}

.sheet-cancel-btn:active {
  background: var(--el-fill-color);
}

/* Sheet transitions */
.sheet-enter-active {
  transition: all 0.25s ease-out;
}
.sheet-leave-active {
  transition: all 0.2s ease-in;
}
.sheet-enter-from .sheet-panel,
.sheet-leave-to .sheet-panel {
  transform: translateY(100%);
}
.sheet-enter-from {
  opacity: 0;
}
.sheet-leave-to {
  opacity: 0;
}
</style>
