<!-- frontend/mambo/src/components/settings/resource/ResourceTreePanel.vue -->
<template>
  <el-aside width="300px" class="resource-tree-panel">
    <ExplorerTree
      ref="treeRef"
      :data="data"
      :current-id="currentId"
      :is-loading="isLoading"
      :loading-folder-ids="loadingFolders"
      folder-item-type="folder"
      persistence-key="mambo_resource_folder_expanded_state"
      :custom-allow-drop="checkDropPermission"
      @node-click="handleNodeClick"
      @node-contextmenu="handleNodeContextMenu"
      @root-contextmenu="openRootContextMenu"
      @move="handleResourceMove"
      @node-expand="handleNodeExpand"
      @upload-success="handleUploadSuccess"
    >
      <template #header>
        <div class="panel-header">
          <h4>{{ t('resource.tree.title') }}</h4>
        </div>
      </template>

      <template #item-icon="{ data: itemData }">
        <el-icon>
          <Reading v-if="itemData.resourceType === 'skill'" />
          <Collection v-else-if="itemData.resourceType === 'knowledge_base'" />
          <Folder v-else-if="itemData.itemType === 'folder'" />
          <Memo v-else-if="itemData.resourceType === 'submessage_template'" />
          <Cpu v-else-if="itemData.resourceType === 'system_prompt'" />
          <Document v-else />
        </el-icon>
      </template>

      <template #item-suffix="{ data: itemData }">
        <el-tooltip
          v-if="itemData.resourceType === 'skill' && skillValidationStatus.has(itemData.id)"
          :content="skillValidationStatus.get(itemData.id)?.is_valid ? t('resource.skill.valid') : t('resource.skill.invalid')"
          placement="top"
        >
          <el-icon
            :color="skillValidationStatus.get(itemData.id)?.is_valid ? '#67C23A' : '#F56C6C'"
            :size="10"
            style="margin-right: 4px;"
          >
            <CircleCheckFilled v-if="skillValidationStatus.get(itemData.id)?.is_valid" />
            <CircleCloseFilled v-else />
          </el-icon>
        </el-tooltip>
      </template>
    </ExplorerTree>
  </el-aside>

  <!-- Context Menu -->
  <el-dropdown
    ref="contextMenuRef"
    trigger="contextmenu"
    @command="handleMenuCommand"
    popper-class="no-animation-popper"
  >
    <span :style="contextMenuPosition" />
    <template #dropdown>
      <el-dropdown-menu>
        <template v-if="!contextMenuItem || contextMenuItem.itemType === 'folder'">
          <el-dropdown-item command="newResource">
            <el-icon><DocumentAdd /></el-icon>{{ t('resource.tree.newResource') }}
          </el-dropdown-item>
          <el-dropdown-item command="newFolder">
            <el-icon><FolderAdd /></el-icon>{{ t('resource.tree.newFolder') }}
          </el-dropdown-item>
          <el-dropdown-item command="newKB">
            <el-icon><Collection /></el-icon>{{ t('resource.tree.newKB') }}
          </el-dropdown-item>
          <el-dropdown-item command="newSkill">
            <el-icon><Reading /></el-icon>{{ t('resource.tree.newSkill') }}
          </el-dropdown-item>
        </template>
        <template v-if="contextMenuItem">
          <el-dropdown-item
            command="rename"
            :divided="!contextMenuItem || contextMenuItem.itemType === 'folder'"
          >
            <el-icon><EditPen /></el-icon>{{ t('resource.tree.rename') }}
          </el-dropdown-item>
          <el-dropdown-item command="delete" class="delete-item">
            <el-icon><Delete /></el-icon>{{ t('resource.tree.delete') }}
          </el-dropdown-item>
        </template>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <!-- Dialogs -->

  <!-- 1. 通用实体表单 (新建资源/文件夹/重命名) -->
  <EntityFormDialog
    v-if="dialogState.payload.value?.type !== 'newKB' && dialogState.payload.value?.type !== 'newSkill'"
    v-model:visible="dialogState.visible.value"
    :title="dialogProps.title"
    :initial-name="dialogProps.initialName"
    :select-config="dialogProps.selectConfig"
    @confirm="onDialogConfirm"
  />

  <!-- 2. 知识库专用表单 (新建知识库) -->
  <KnowledgeBaseFormDialog
    v-else-if="dialogState.payload.value?.type === 'newKB'"
    v-model:visible="dialogState.visible.value"
    :embedding-model-options="embeddingModelOptions"
    @confirm="handleKBConfirm"
  />

  <!-- 3. SKILL 专用表单 -->
  <SkillFormDialog
    v-else-if="dialogState.payload.value?.type === 'newSkill'"
    v-model:visible="dialogState.visible.value"
    @confirm="handleSkillConfirm"
  />
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  Folder,
  Document,
  DocumentAdd,
  FolderAdd,
  EditPen,
  Delete,
  Memo,
  Collection,
  Cpu,
  Reading,
  CircleCheckFilled,
  CircleCloseFilled,
} from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import type { AllowDropType } from 'element-plus/es/components/tree/src/tree.type'
import type Node from 'element-plus/es/components/tree/src/model/node'

import { useResourceStore } from '@/stores/resourceStore'
import { useProviderStore } from '@/stores/providerStore'
import { createKnowledgeBase } from '@/api/kbService'
import {
  useTreeController,
  type DialogPayload,
  type DialogConfirmPayload,
} from '@/composables/useTreeController'
import ExplorerTree from '@/components/common/ExplorerTree.vue'
import EntityFormDialog from '@/components/common/EntityFormDialog.vue'
import KnowledgeBaseFormDialog, {
  type KBConfirmPayload,
  type ModelGroup,
} from '@/components/settings/dialogs/KnowledgeBaseFormDialog.vue'
import SkillFormDialog from '@/components/settings/dialogs/SkillFormDialog.vue'

import type {
  Resource,
  ResourceWithVersions,
  ResourceCreate,
  ResourceUpdate,
  ResourceType,
  BaseTreeItem,
  MoveRequest,
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
  (e: 'move-success', item_ids: string[]): void
}>()

// --- Store ---
const resourceStore = useResourceStore()
const providerStore = useProviderStore()
const { resources, loadingFolders, skillValidationStatus } = storeToRefs(resourceStore)

// --- Constants ---
const creatableResourceTypes = computed(() => [
  { value: 'system_prompt' as ResourceType, label: t('resource.types.system_prompt') },
  { value: 'submessage_template' as ResourceType, label: t('resource.types.submessage_template') },
  { value: 'file' as ResourceType, label: t('resource.types.file') },
])

const DEFAULT_SUBMESSAGE_ATTRIBUTES = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: true,
}

// --- Computed Options ---

const embeddingModelOptions = computed<ModelGroup[]>(() => {
  const models = providerStore.allModels.filter((m) => m.model_type === 'embedding')
  const groups: Record<string, ModelGroup> = {}

  models.forEach((m) => {
    const providerName =
      providerStore.providers.find((p) => p.id === m.providerId)?.name || 'Unknown Provider'
    if (!groups[providerName]) {
      groups[providerName] = { label: providerName, options: [] }
    }
    groups[providerName].options.push({ label: m.name, value: m.id })
  })

  return Object.values(groups)
})

// --- Drag & Drop Validation Logic ---

const findKBParentId = (node: Node): string | null => {
  let current: Node | null = node
  while (current && current.level > 0) {
    const data = current.data as Resource
    if (data.resourceType === 'knowledge_base') {
      return data.id
    }
    current = current.parent
  }
  return null
}

const checkDropPermission = (
  draggingNode: Node,
  dropNode: Node,
  dropType: AllowDropType,
): boolean => {
  const draggingData = draggingNode.data as Resource
  const dropData = dropNode.data as Resource

  // Constraint for SKILL folder: Only allow plain folders or plain files
  if (dropType === 'inner' && dropData.resourceType === 'skill') {
    const isPlainFolder = draggingData.itemType === 'folder' && !draggingData.resourceType
    const isPlainFile = draggingData.resourceType === 'file'
    return isPlainFolder || isPlainFile
  }

  if (draggingData.resourceType === 'knowledge_base') {
    const targetKBId = findKBParentId(dropNode)
    if (targetKBId) {
      return false
    }
    if (dropType === 'inner' && dropData.resourceType === 'knowledge_base') {
      return false
    }
    return true
  }

  return true
}

// --- Tree Controller Logic ---
const {
  treeRef,
  contextMenuRef,
  contextMenuItem,
  contextMenuPosition,
  dialogState,
  dialogProps,
  handleNodeExpand,
  handleNodeContextMenu,
  openRootContextMenu,
  handleMenuCommand,
  onDialogConfirm,
} = useTreeController<Resource, ResourceCreate, ResourceUpdate>({
  items: resources,
  crudHandlers: {
    createItem: resourceStore.addResourceItem,
    updateItem: resourceStore.updateResourceItem,
    deleteItem: async (id: string) => {
      await resourceStore.deleteResourceItem(id)
      emit('item-deleted', id)
    },
    moveItem: resourceStore.moveResourceItem,
  },
  onExpand: resourceStore.fetchResourceChildren,
  getDialogProps: (payload: DialogPayload<Resource>) => {
    switch (payload.type) {
      case 'rename':
        return { title: t('resource.tree.rename'), initialName: payload.targetItem?.name || '' }
      case 'newResource':
        return {
          title: t('resource.tree.newResource'),
          initialName: t('resource.tree.newResource'),
          selectConfig: {
            label: t('resource.meta.type'),
            options: creatableResourceTypes.value,
            initialValue: creatableResourceTypes.value[0].value,
          },
        }
      case 'newFolder':
        return { title: t('resource.tree.newFolder'), initialName: t('resource.tree.newFolder') }
      case 'newKB':
        return { title: '', initialName: '' }
      case 'newSkill':
        return { title: t('resource.tree.newSkill'), initialName: '' }
      default:
        return { title: '', initialName: '' }
    }
  },
  handleDialogConfirm: async (
    dialogPayload: DialogPayload<Resource>,
    formPayload: DialogConfirmPayload,
  ): Promise<Resource | null> => {
    if (dialogPayload.type === 'rename' && dialogPayload.targetItem) {
      await resourceStore.updateResourceItem(dialogPayload.targetItem.id, {
        name: formPayload.name,
      })
      return null
    }

    let newItem: Resource | null = null

    if (dialogPayload.type === 'newResource') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'resource',
        resourceType: formPayload.selectValue as ResourceType,
        parentId: dialogPayload.parentId,
        initial_content: '',
        initial_attributes:
          formPayload.selectValue === 'submessage_template'
            ? { ...DEFAULT_SUBMESSAGE_ATTRIBUTES }
            : undefined,
      })
    } else if (dialogPayload.type === 'newFolder') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'folder',
        parentId: dialogPayload.parentId,
      })
    }

    if (newItem) {
      emit('item-created', newItem)
    }
    return newItem
  },
})

// --- Custom Move Handler with Warning ---

const handleResourceMove = async (req: MoveRequest) => {
  let targetParentId: string | null = null
  if (req.action === 'inside') {
    targetParentId = req.reference_id
  } else {
    const refNode = resources.value.find((r) => r.id === req.reference_id)
    targetParentId = refNode?.parentId ?? null
  }

  let targetKbId: string | null = null
  if (targetParentId) {
    const parentRes = resources.value.find((r) => r.id === targetParentId)
    if (parentRes) {
      targetKbId = parentRes.resourceType === 'knowledge_base' ? parentRes.id : parentRes.kb_id
    }
  }

  const movingIds = req.item_ids
  let needsWarning = false

  for (const id of movingIds) {
    const item = resources.value.find((r) => r.id === id)
    if (item && item.kb_id && item.kb_id !== targetKbId) {
      needsWarning = true
      break
    }
  }

  if (needsWarning) {
    try {
      await ElMessageBox.confirm(
        t('resource.tree.moveWarning'),
        t('resource.tree.moveWarningTitle'),
        {
          confirmButtonText: t('common.action.confirm'),
          cancelButtonText: t('common.action.cancel'),
          type: 'warning',
        },
      )
    } catch {
      return
    }
  }

  await resourceStore.moveResourceItem(req)
  emit('move-success', req.item_ids)
}

const handleUploadSuccess = () => {
  resourceStore.initializeList()
}

// --- KB Specific Handlers ---

const handleKBConfirm = async (payload: KBConfirmPayload) => {
  const parentId = dialogState.payload.value?.parentId ?? null

  const newItem = await createKnowledgeBase({
    name: payload.name,
    parent_id: parentId,
    embedding_model_id: payload.embeddingModelId,
    embedding_rate_limit: payload.embeddingRateLimit,
  })

  if (newItem) {
    const newItemWithVersions: ResourceWithVersions = {
      ...newItem,
      versions: newItem.latest_version ? [newItem.latest_version] : [],
    }

    resourceStore.resources.push(newItemWithVersions)

    if (newItem.itemType === 'folder') {
      resourceStore.loadedFolderIds.add(newItem.id)
    }
    emit('item-created', newItem)
  }

  dialogState.visible.value = false
}

// --- SKILL Specific Handlers ---

const handleSkillConfirm = async (payload: { name: string; description: string }) => {
  const parentId = dialogState.payload.value?.parentId ?? null
  const newItem = await resourceStore.addSkillItem({
    name: payload.name,
    description: payload.description,
    parentId: parentId,
  })

  if (newItem) {
    emit('item-created', newItem)
    resourceStore.checkSkillValidation(newItem.id)
  }
  dialogState.visible.value = false
}

// --- Lifecycle ---
onMounted(() => {
  resourceStore.initializeList()
  providerStore.fetchProviders()
})

// --- Handlers ---
function handleNodeClick(data: BaseTreeItem) {
  emit('node-click', data)
}
</script>

<style scoped>
.resource-tree-panel {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--el-border-color);
  background-color: var(--color-background-soft);
}

.panel-header {
  padding: 16px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: default;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
}

.delete-item {
  color: var(--el-color-danger);
}
</style>

<style>
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
