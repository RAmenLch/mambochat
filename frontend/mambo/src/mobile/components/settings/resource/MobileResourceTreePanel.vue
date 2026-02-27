<!-- frontend/mambo/src/mobile/components/settings/resource/MobileResourceTreePanel.vue -->
<template>
  <div class="mobile-resource-tree-panel">
    <!-- Header -->
    <div class="panel-header">
      <span class="title">{{ t('resource.tree.title') }}</span>
      <div class="header-actions">
        <el-dropdown trigger="click" @command="handleRootCommand">
          <el-button link :icon="Plus" class="icon-btn" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="newResource">
                <el-icon><DocumentAdd /></el-icon>{{ t('resource.tree.newResource') }}
              </el-dropdown-item>
              <el-dropdown-item command="newFolder">
                <el-icon><FolderAdd /></el-icon>{{ t('resource.tree.newFolder') }}
              </el-dropdown-item>
              <el-dropdown-item command="newKB">
                <el-icon><Collection /></el-icon>{{ t('resource.tree.newKB') }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- Tree Content -->
    <div class="tree-container" v-loading="isLoading && !data.length">
      <ExplorerTree
        ref="treeRef"
        :data="data"
        :current-id="currentId"
        :is-loading="isLoading"
        :loading-folder-ids="loadingFolders"
        folder-item-type="folder"
        persistence-key="mambo_mobile_resource_tree"
        @node-click="handleNodeClick"
        @node-expand="handleNodeExpand"
      >
        <template #item-icon="{ data: itemData }">
          <el-icon>
            <Collection v-if="itemData.resourceType === 'knowledge_base'" />
            <Folder v-else-if="itemData.itemType === 'folder'" />
            <Memo v-else-if="itemData.resourceType === 'submessage_template'" />
            <Cpu v-else-if="itemData.resourceType === 'system_prompt'" />
            <Document v-else />
          </el-icon>
        </template>

        <template #item-suffix="{ data: itemData }">
          <div class="node-actions" @click.stop="openContextMenu(itemData)">
            <el-icon><MoreFilled /></el-icon>
          </div>
        </template>
      </ExplorerTree>

      <el-empty v-if="!isLoading && data.length === 0" :description="t('common.msg.noData')" />
    </div>

    <!-- Context Menu Drawer -->
    <el-drawer
      v-model="contextMenuVisible"
      direction="btt"
      :show-close="false"
      :with-header="false"
      size="auto"
      class="context-menu-drawer"
    >
      <!-- Drawer content unchanged ... -->
       <div class="context-menu-list" v-if="selectedItem">
        <div class="menu-header">
          <span class="menu-title">{{ selectedItem.name }}</span>
        </div>

        <template v-if="selectedItem.itemType === 'folder'">
          <div class="menu-item" @click="handleContextAction('newResource')">
            <el-icon><DocumentAdd /></el-icon>
            <span>{{ t('resource.tree.newResource') }}</span>
          </div>
          <div class="menu-item" @click="handleContextAction('newFolder')">
            <el-icon><FolderAdd /></el-icon>
            <span>{{ t('resource.tree.newFolder') }}</span>
          </div>
          <div class="menu-item" @click="handleContextAction('newKB')">
            <el-icon><Collection /></el-icon>
            <span>{{ t('resource.tree.newKB') }}</span>
          </div>
          <el-divider />
        </template>

        <div class="menu-item" @click="handleContextAction('rename')">
          <el-icon><EditPen /></el-icon>
          <span>{{ t('resource.tree.rename') }}</span>
        </div>

         <div class="menu-item" @click="handleContextAction('move')">
          <el-icon><Rank /></el-icon>
          <span>{{ t('resource.tree.move') }}</span>
        </div>

        <el-divider />

        <div class="menu-item danger" @click="handleContextAction('delete')">
          <el-icon><Delete /></el-icon>
          <span>{{ t('resource.tree.delete') }}</span>
        </div>

        <div class="menu-cancel" @click="contextMenuVisible = false">
          {{ t('common.action.cancel') }}
        </div>
      </div>
    </el-drawer>

    <!-- Dialogs -->
    <EntityFormDialog
      v-if="dialogState.type !== 'newKB'"
      v-model:visible="dialogVisible"
      :title="dialogProps.title"
      :initial-name="dialogProps.initialName"
      :select-config="dialogProps.selectConfig"
      @confirm="handleDialogConfirm"
    />

    <KnowledgeBaseFormDialog
      v-else
      v-model:visible="dialogVisible"
      :embedding-model-options="embeddingModelOptions"
      @confirm="handleKBConfirm"
    />

    <!-- 3. Move Dialog -->
    <MoveTargetDialog
      v-model:visible="moveDialogVisible"
      :item-to-move="selectedItem"
      :tree-data="folderTreeData"
      @confirm="handleMoveConfirm"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  Folder, Document, DocumentAdd, FolderAdd, EditPen, Delete, Memo, Collection, Cpu, Plus, MoreFilled, Rank
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useResourceStore } from '@/stores/resourceStore'
import { useProviderStore } from '@/stores/providerStore'
import { createKnowledgeBase } from '@/api/kbService'
import ExplorerTree from '@/components/common/ExplorerTree.vue'
import EntityFormDialog from '@/components/common/EntityFormDialog.vue'
import KnowledgeBaseFormDialog, { type ModelGroup } from '@/components/settings/dialogs/KnowledgeBaseFormDialog.vue'
import MoveTargetDialog from '@/mobile/components/chat/dialogs/MoveTargetDialog.vue'

// 修复 1: 引入 ChatNode 类型以进行类型断言
import type {
  Resource, ResourceWithVersions, ResourceCreate, ResourceType, BaseTreeItem, MoveRequest, ChatNode
} from '@/api/types'

const { t } = useI18n()

// --- Props & Emits ---
defineProps<{
  data: Resource[]
  currentId: string | null
  isLoading: boolean
}>()

const emit = defineEmits<{
  (e: 'node-click', data: BaseTreeItem): void
  (e: 'item-created', data: Resource): void
  (e: 'item-deleted', id: string): void
}>()

// --- Stores ---
const resourceStore = useResourceStore()
const providerStore = useProviderStore()

// 修复 2: 将 loadingFolderIds 改为 loadingFolders，与 Store 导出保持一致
const { resources, loadingFolders, loadedFolderIds, resourceTree } = storeToRefs(resourceStore)

// --- State ---
const treeRef = ref<InstanceType<typeof ExplorerTree>>()
const contextMenuVisible = ref(false)
const selectedItem = ref<Resource | null>(null)

// Dialog State
const dialogVisible = ref(false)
const dialogState = ref<{
  type: 'rename' | 'newResource' | 'newFolder' | 'newKB' | null
  targetItem: Resource | null
  parentId: string | null
}>({
  type: null,
  targetItem: null,
  parentId: null
})

const dialogProps = ref<{
  title: string
  initialName: string
  selectConfig?: { label: string; options: { value: string; label: string }[]; initialValue: string }
}>({
  title: '',
  initialName: ''
})

// Move Dialog State
const moveDialogVisible = ref(false)

// --- Computed ---
const creatableResourceTypes = computed(() => [
  { value: 'system_prompt' as ResourceType, label: t('resource.types.system_prompt') },
  { value: 'submessage_template' as ResourceType, label: t('resource.types.submessage_template') },
  { value: 'file' as ResourceType, label: t('resource.types.file') },
])

const embeddingModelOptions = computed<ModelGroup[]>(() => {
  const models = providerStore.allModels.filter((m) => m.model_type === 'embedding')
  const groups: Record<string, ModelGroup> = {}
  models.forEach((m) => {
    const providerName = providerStore.providers.find((p) => p.id === m.providerId)?.name || 'Unknown'
    if (!groups[providerName]) groups[providerName] = { label: providerName, options: [] }
    groups[providerName].options.push({ label: m.name, value: m.id })
  })
  return Object.values(groups)
})

// 修复 3: 类型断言以匹配 MoveTargetDialog 的 props (ChatNode[])
const folderTreeData = computed(() => {
  return resourceTree.value as unknown as ChatNode[]
})

// --- Lifecycle ---
onMounted(() => {
  providerStore.fetchProviders()
})

// --- Interaction Handlers ---

function handleNodeClick(data: BaseTreeItem) {
  emit('node-click', data)
}

function handleNodeExpand(data: BaseTreeItem) {
  if (data.itemType === 'folder') {
    resourceStore.fetchResourceChildren(data.id)
  }
}

function openContextMenu(data: Resource) {
  selectedItem.value = data
  contextMenuVisible.value = true
}

function handleRootCommand(command: string) {
  handleContextAction(command, null)
}

function handleContextAction(action: string, parentIdOverride: string | null = null) {
  contextMenuVisible.value = false
  const item = selectedItem.value

  const parentId = parentIdOverride !== null ? parentIdOverride :
                   (item?.itemType === 'folder' ? item.id : item?.parentId) || null

  if (action === 'newResource') {
    dialogState.value = { type: 'newResource', targetItem: null, parentId }
    dialogProps.value = {
      title: t('resource.tree.newResource'),
      initialName: t('resource.tree.newResource'),
      selectConfig: {
        label: t('resource.meta.type'),
        options: creatableResourceTypes.value,
        initialValue: 'system_prompt'
      }
    }
    dialogVisible.value = true
  } else if (action === 'newFolder') {
    dialogState.value = { type: 'newFolder', targetItem: null, parentId }
    dialogProps.value = {
      title: t('resource.tree.newFolder'),
      initialName: t('resource.tree.newFolder'),
      selectConfig: undefined
    }
    dialogVisible.value = true
  } else if (action === 'newKB') {
    dialogState.value = { type: 'newKB', targetItem: null, parentId }
    dialogProps.value = { title: '', initialName: '' }
    dialogVisible.value = true
  } else if (action === 'rename' && item) {
    dialogState.value = { type: 'rename', targetItem: item, parentId: null }
    dialogProps.value = {
      title: t('resource.tree.rename'),
      initialName: item.name,
      selectConfig: undefined
    }
    dialogVisible.value = true
  } else if (action === 'delete' && item) {
    handleDelete(item)
  } else if (action === 'move' && item) {
    moveDialogVisible.value = true
  }
}

async function handleDelete(item: Resource) {
  try {
    await ElMessageBox.confirm(t('common.msg.deleteConfirm', { name: item.name }), t('common.action.delete'), {
      type: 'warning',
      confirmButtonClass: 'el-button--danger'
    })
    await resourceStore.deleteResourceItem(item.id)
    emit('item-deleted', item.id)
    ElMessage.success(t('common.msg.deleteSuccess'))
  } catch {}
}

// --- Dialog Confirm Handlers ---

const DEFAULT_SUBMESSAGE_ATTRIBUTES = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: true,
}

async function handleDialogConfirm(payload: { name: string; selectValue?: string }) {
  const state = dialogState.value
  if (!state) return

  try {
    if (state.type === 'rename' && state.targetItem) {
      await resourceStore.updateResourceItem(state.targetItem.id, { name: payload.name })
      ElMessage.success(t('common.msg.updateSuccess'))
    } else if (state.type === 'newResource') {
      const newItem = await resourceStore.addResourceItem({
        name: payload.name,
        itemType: 'resource',
        resourceType: (payload.selectValue || 'system_prompt') as ResourceType,
        parentId: state.parentId,
        initial_content: '',
        initial_attributes: payload.selectValue === 'submessage_template' ? { ...DEFAULT_SUBMESSAGE_ATTRIBUTES } : undefined
      })
      if (newItem) emit('item-created', newItem)
    } else if (state.type === 'newFolder') {
      const newItem = await resourceStore.addResourceItem({
        name: payload.name,
        itemType: 'folder',
        parentId: state.parentId
      })
      if (newItem) emit('item-created', newItem)
    }
    dialogVisible.value = false
  } catch (error) {
    console.error(error)
  }
}

async function handleKBConfirm(payload: { name: string; embeddingModelId: string; embeddingRateLimit: number }) {
  const state = dialogState.value
  if (!state) return

  try {
    const newItem = await createKnowledgeBase({
      name: payload.name,
      parent_id: state.parentId,
      embedding_model_id: payload.embeddingModelId,
      embedding_rate_limit: payload.embeddingRateLimit
    })

    if (newItem) {
      const newItemWithVersions: ResourceWithVersions = {
        ...newItem,
        versions: newItem.latest_version ? [newItem.latest_version] : []
      }
      resourceStore.resources.push(newItemWithVersions)
      if (newItem.itemType === 'folder') resourceStore.loadedFolderIds.add(newItem.id)
      emit('item-created', newItem)
    }
    dialogVisible.value = false
  } catch (error) {
    console.error(error)
    ElMessage.error(t('common.msg.createFailed'))
  }
}

async function handleMoveConfirm(targetId: string) {
  if (!selectedItem.value) return

  const req: MoveRequest = {
    item_ids: [selectedItem.value.id],
    reference_id: targetId,
    action: 'inside'
  }

  try {
    await resourceStore.moveResourceItem(req)
    ElMessage.success(t('common.msg.moveSuccess'))
    if (targetId !== 'root') {
      resourceStore.fetchResourceChildren(targetId)
    }
  } catch (error) {
    ElMessage.error(t('common.error.moveFailed'))
  } finally {
    moveDialogVisible.value = false
  }
}

</script>

<style scoped>
/* 样式保持不变 */
.mobile-resource-tree-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft);
}

.panel-header {
  padding: 15px;
  font-weight: bold;
  font-size: 18px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--color-background);
}

.header-actions {
  display: flex;
  gap: 5px;
}

.icon-btn {
  padding: 5px;
  font-size: 20px;
}

.tree-container {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 50px;
}

.node-actions {
  padding: 8px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
  cursor: pointer;
}

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
