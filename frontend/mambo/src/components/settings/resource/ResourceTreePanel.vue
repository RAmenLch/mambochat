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
          <h4>资源列表</h4>
        </div>
      </template>

      <template #item-icon="{ data: itemData }">
        <el-icon>
          <!-- 优先匹配知识库类型 -->
          <Collection v-if="itemData.resourceType === 'knowledge_base'" />
          <Folder v-else-if="itemData.itemType === 'folder'" />
          <Memo v-else-if="itemData.resourceType === 'submessage_template'" />
          <Cpu v-else-if="itemData.resourceType === 'system_prompt'" />
          <Document v-else />
        </el-icon>
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
          <el-dropdown-item command="newResource"
            ><el-icon><DocumentAdd /></el-icon>新建资源</el-dropdown-item
          >
          <el-dropdown-item command="newFolder"
            ><el-icon><FolderAdd /></el-icon>新建文件夹</el-dropdown-item
          >
          <el-dropdown-item command="newKB"
            ><el-icon><Collection /></el-icon>新建知识库</el-dropdown-item
          >
        </template>
        <template v-if="contextMenuItem">
          <el-dropdown-item
            command="rename"
            :divided="!contextMenuItem || contextMenuItem.itemType === 'folder'"
            ><el-icon><EditPen /></el-icon>重命名</el-dropdown-item
          >
          <el-dropdown-item command="delete" class="delete-item"
            ><el-icon><Delete /></el-icon>删除</el-dropdown-item
          >
        </template>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <!-- Dialogs -->

  <!-- 1. 通用实体表单 (新建资源/文件夹/重命名) -->
  <EntityFormDialog
    v-if="dialogState.payload.value?.type !== 'newKB'"
    v-model:visible="dialogState.visible.value"
    :title="dialogProps.title"
    :initial-name="dialogProps.initialName"
    :select-config="dialogProps.selectConfig"
    @confirm="onDialogConfirm"
  />

  <!-- 2. 知识库专用表单 (新建知识库) -->
  <KnowledgeBaseFormDialog
    v-else
    v-model:visible="dialogState.visible.value"
    :embedding-model-options="embeddingModelOptions"
    @confirm="handleKBConfirm"
  />
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
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

import type {
  Resource,
  ResourceWithVersions,
  ResourceCreate,
  ResourceUpdate,
  ResourceType,
  BaseTreeItem,
  MoveRequest,
} from '@/api/types'

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
const { resources, loadingFolders } = storeToRefs(resourceStore)

// --- Constants ---
const creatableResourceTypes: { value: ResourceType; label: string }[] = [
  { value: 'system_prompt', label: '系统提示词' },
  { value: 'submessage_template', label: '消息模板' },
  { value: 'file', label: '通用文件' },
]

const DEFAULT_SUBMESSAGE_ATTRIBUTES = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: true,
}

// --- Computed Options ---

// 计算可用的 Embedding 模型选项，按服务商分组，适配 KnowledgeBaseFormDialog 的数据结构
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

/**
 * 查找节点所属的知识库 ID
 * @param node 树节点
 * @returns 知识库 ID，如果节点不在知识库中则返回 null
 */
const findKBParentId = (node: Node): string | null => {
  let current: Node | null = node
  // 向上遍历，检查当前节点或其祖先是否为 knowledge_base 类型
  while (current && current.level > 0) {
    const data = current.data as Resource
    if (data.resourceType === 'knowledge_base') {
      return data.id
    }
    current = current.parent
  }
  return null
}

/**
 * 自定义拖拽校验逻辑
 * 1. 禁止将 KB 嵌套 (KB 放入另一个 KB)。
 * 2. 允许将 KB 文件移出 KB 或跨 KB 移动 (逻辑层会进行警告拦截)。
 */
const checkDropPermission = (
  draggingNode: Node,
  dropNode: Node,
  dropType: AllowDropType,
): boolean => {
  const draggingData = draggingNode.data as Resource
  const dropData = dropNode.data as Resource

  // 场景 1: 拖拽的是知识库本身
  if (draggingData.resourceType === 'knowledge_base') {
    // 目标不能在另一个知识库内部
    const targetKBId = findKBParentId(dropNode)
    if (targetKBId) {
      return false // 禁止 KB 嵌套
    }
    // 如果目标是另一个 KB (且 dropType 是 inner)，也禁止
    if (dropType === 'inner' && dropData.resourceType === 'knowledge_base') {
      return false
    }
    return true
  }

  // 场景 2: 拖拽的是普通资源
  // 允许任意移动，具体的副作用（如向量丢失）在 handleResourceMove 中处理
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
  // handleMove, // 不使用默认的 handleMove，改用自定义的 handleResourceMove
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
        return { title: '重命名', initialName: payload.targetItem?.name || '' }
      case 'newResource':
        return {
          title: '新建资源',
          initialName: '新的资源',
          selectConfig: {
            label: '资源类型',
            options: creatableResourceTypes,
            initialValue: creatableResourceTypes[0].value,
          },
        }
      case 'newFolder':
        return { title: '新建文件夹', initialName: '新的文件夹' }
      // newKB 使用专用 Dialog，此处无需配置 props，但为了类型安全返回空对象
      case 'newKB':
        return { title: '', initialName: '' }
      default:
        return { title: '', initialName: '' }
    }
  },
  handleDialogConfirm: async (
    dialogPayload: DialogPayload<Resource>,
    formPayload: DialogConfirmPayload,
  ): Promise<Resource | null> => {
    // 注意：newKB 的处理逻辑已分离到 handleKBConfirm，此处仅处理通用资源
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
  // 1. 计算目标父节点 ID
  let targetParentId: string | null = null
  if (req.action === 'inside') {
    targetParentId = req.reference_id
  } else {
    // 如果是 before/after，目标父节点是参考节点的父节点
    const refNode = resources.value.find((r) => r.id === req.reference_id)
    targetParentId = refNode?.parentId ?? null
  }

  // 2. 确定目标位置所属的 Knowledge Base ID
  let targetKbId: string | null = null
  if (targetParentId) {
    const parentRes = resources.value.find((r) => r.id === targetParentId)
    if (parentRes) {
      // 如果父节点本身是 KB，则 ID 即为 KB ID；否则沿用其 kb_id
      targetKbId = parentRes.resourceType === 'knowledge_base' ? parentRes.id : parentRes.kb_id
    }
  }

  // 3. 检查是否涉及将资源移出知识库或跨知识库移动
  const movingIds = req.item_ids
  let needsWarning = false

  for (const id of movingIds) {
    const item = resources.value.find((r) => r.id === id)
    // 如果源资源属于某个 KB，且目标位置的 KB ID 与源不一致（包括移到非 KB 区域），则需要警告
    if (item && item.kb_id && item.kb_id !== targetKbId) {
      needsWarning = true
      break
    }
  }

  if (needsWarning) {
    try {
      await ElMessageBox.confirm(
        '将资源移出知识库或移动到其他知识库会导致原有的切片和向量数据丢失，是否继续？',
        '警告',
        {
          confirmButtonText: '确定移动',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch {
      // 用户取消操作
      return
    }
  }

  // 4. 执行移动
  await resourceStore.moveResourceItem(req)
  emit('move-success', req.item_ids)
}

const handleUploadSuccess = () => {
  // 上传成功后刷新列表以显示新文件
  resourceStore.initializeList()
}

// --- KB Specific Handlers ---

/**
 * 处理知识库创建确认
 */
const handleKBConfirm = async (payload: KBConfirmPayload) => {
  // 获取当前上下文的父节点 ID (由 useTreeController 管理)
  const parentId = dialogState.payload.value?.parentId ?? null

  // 调用 Service 创建知识库
  const newItem = await createKnowledgeBase({
    name: payload.name,
    parent_id: parentId,
    embedding_model_id: payload.embeddingModelId,
    embedding_rate_limit: payload.embeddingRateLimit,
  })

  // 手动同步到 Store
  if (newItem) {
    // 构造符合 Store 要求的 ResourceWithVersions 类型
    // 后端创建知识库时会自动创建初始版本并挂载到 latest_version
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

  // 关闭弹窗
  dialogState.visible.value = false
}

// --- Lifecycle ---
onMounted(() => {
  // 初始化资源列表（加载根节点）
  resourceStore.initializeList()
  // 预加载服务商列表，以便创建知识库时有模型可选
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
