<!-- frontend/mambo/src/components/common/ExplorerTree.vue -->
<template>
  <div
    class="explorer-tree-container"
    @contextmenu.prevent="handleRootContextMenu"
    @dragover.prevent
    @drop.prevent="handleContainerDrop"
  >
    <!-- ... 头部内容保持不变 ... -->
    <div class="explorer-tree-header" v-if="$slots.header">
      <slot name="header"></slot>
    </div>

    <el-scrollbar class="explorer-tree-scrollbar">
      <div v-if="isLoading && data.length === 0" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>
      <el-tree
        v-else-if="data.length > 0 || !isLoading"
        ref="treeRef"
        :data="data"
        node-key="id"
        :current-node-key="currentId || undefined"
        highlight-current
        :expand-on-click-node="false"
        draggable
        :allow-drop="allowDrop"
        :indent="5"
        @node-click="handleNodeClick"
        @node-drop="handleNodeDrop"
        @node-contextmenu="handleNodeContextMenu"
        @node-expand="handleNodeExpand"
        @node-collapse="handleNodeCollapse"
        class="custom-tree tree-with-lines"
        :props="treeProps"
      >
        <template #default="{ node, data }">
          <span
            class="custom-tree-node"
            :class="{ 'is-drag-over': dragOverId === data.id }"
            @dragover.prevent
            @dragenter.prevent="handleNodeDragEnter(data)"
            @dragleave.prevent="handleNodeDragLeave(data)"
            @drop.stop.prevent="handleNodeNativeDrop(data, $event)"
          >
            <span class="node-icon-wrapper" v-if="$slots['item-icon']">
              <slot name="item-icon" :node="node" :data="data"></slot>
            </span>

            <slot name="item-label" :node="node" :data="data">
              <el-tooltip
                :content="node.label"
                placement="top"
                :show-after="500"
                effect="dark"
                :disabled="!node.label || node.label.length < 15"
              >
                <span class="node-label">{{ node.label }}</span>
              </el-tooltip>
            </slot>

            <!-- 【新增】后缀插槽，用于放置移动端的菜单按钮或其他操作 -->
            <span class="node-suffix-wrapper" v-if="$slots['item-suffix']">
              <slot name="item-suffix" :node="node" :data="data"></slot>
            </span>

            <el-icon v-if="loadingNodes.has(data.id)" class="is-loading loading-icon">
              <Loading />
            </el-icon>
          </span>
        </template>
      </el-tree>
      <el-empty v-else :description="displayEmptyText" />
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
// ... 脚本部分保持不变，无需修改 ...
import { ref, watch, nextTick, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElTree, ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import type {
  AllowDropType,
  NodeDropType,
  TreeNodeData,
} from 'element-plus/es/components/tree/src/tree.type'
import type Node from 'element-plus/es/components/tree/src/model/node'
import type { BaseTreeItem, MoveRequest, MoveAction } from '@/api/types'
import { uploadResourceFile } from '@/api/kbService'

interface Props {
  data: BaseTreeItem[]
  currentId?: string | null
  isLoading?: boolean
  emptyText?: string
  folderItemType?: string
  persistenceKey?: string
  loadingFolderIds?: Set<string>
  customAllowDrop?: (draggingNode: Node, dropNode: Node, dropType: AllowDropType) => boolean
}

const props = withDefaults(defineProps<Props>(), {
  currentId: null,
  isLoading: false,
  emptyText: undefined,
  folderItemType: 'folder',
  persistenceKey: undefined,
  loadingFolderIds: () => new Set(),
  customAllowDrop: undefined,
})

const emit = defineEmits<{
  (e: 'node-click', data: BaseTreeItem): void
  (e: 'node-contextmenu', event: MouseEvent, data: BaseTreeItem, node: Node): void
  (e: 'root-contextmenu', event: MouseEvent): void
  (e: 'move', req: MoveRequest): void
  (e: 'node-expand', data: BaseTreeItem): void
  (e: 'upload-success'): void
}>()

const { t } = useI18n()
const treeRef = ref<InstanceType<typeof ElTree>>()
const expandedState = ref<Record<string, boolean>>({})
const dragOverId = ref<string | null>(null)

const displayEmptyText = computed(() => props.emptyText || t('common.status.noData'))
const loadingNodes = computed(() => props.loadingFolderIds)

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: (data: TreeNodeData) => {
    return (data as BaseTreeItem).itemType !== props.folderItemType
  },
  class: (data: TreeNodeData) => {
    return (data as BaseTreeItem).itemType === 'stub' ? 'is-hidden-node' : ''
  },
}

const handleNodeClick = (data: BaseTreeItem) => {
  emit('node-click', data)
}

const handleNodeContextMenu = (event: MouseEvent, data: BaseTreeItem, node: Node) => {
  emit('node-contextmenu', event, data, node)
}

const handleRootContextMenu = (event: MouseEvent) => {
  emit('root-contextmenu', event)
}

const allowDrop = (draggingNode: Node, dropNode: Node, dropType: AllowDropType) => {
  if (props.customAllowDrop) {
    if (!props.customAllowDrop(draggingNode, dropNode, dropType)) {
      return false
    }
  }

  if ((dropNode.data as BaseTreeItem).itemType !== props.folderItemType && dropType === 'inner') {
    return false
  }
  return true
}

const handleNodeDrop = (draggingNode: Node, dropNode: Node, dropType: NodeDropType) => {
  let action: MoveAction
  let referenceId: string
  const draggingData = draggingNode.data as BaseTreeItem
  const dropData = dropNode.data as BaseTreeItem

  if (dropType === 'inner') {
    action = 'inside'
    referenceId = dropData.id
  } else if (dropType === 'before') {
    action = 'before'
    referenceId = dropData.id
  } else if (dropType === 'after') {
    action = 'after'
    referenceId = dropData.id
  } else {
    return
  }

  const req: MoveRequest = {
    item_ids: [draggingData.id],
    reference_id: referenceId,
    action: action,
  }
  emit('move', req)
}

// --- Native File Drop Handlers ---

const processFileUpload = async (files: FileList, parentId: string) => {
  if (files.length === 0) return

  const loading = ElMessage.info({
    message: t('resource.explorer.uploadingCount', { count: files.length }),
    duration: 0,
  })

  try {
    const uploadPromises = Array.from(files).map((file) => {
      return uploadResourceFile(file, parentId)
    })

    await Promise.all(uploadPromises)
    ElMessage.success(t('resource.explorer.uploadSuccess'))
    emit('upload-success')
  } catch (error) {
    console.error('File upload failed', error)
    ElMessage.error(t('resource.explorer.uploadPartialFail'))
  } finally {
    loading.close()
  }
}

const handleContainerDrop = async (event: DragEvent) => {
  dragOverId.value = null
  const files = event.dataTransfer?.files
  if (files && files.length > 0) {
    await processFileUpload(files, 'root')
  }
}

const handleNodeDragEnter = (data: BaseTreeItem) => {
  if (data.itemType === props.folderItemType) {
    dragOverId.value = data.id
  } else {
    dragOverId.value = null
  }
}

const handleNodeDragLeave = (data: BaseTreeItem) => {
  if (dragOverId.value === data.id) {
    dragOverId.value = null
  }
}

const handleNodeNativeDrop = async (data: BaseTreeItem, event: DragEvent) => {
  dragOverId.value = null
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return

  const targetParentId = data.itemType === props.folderItemType ? data.id : 'root'
  await processFileUpload(files, targetParentId)
}

// --- State Management ---

const loadExpandedState = () => {
  if (!props.persistenceKey) return
  const savedState = localStorage.getItem(props.persistenceKey)
  if (savedState) {
    try {
      expandedState.value = JSON.parse(savedState)
    } catch (e) {
      localStorage.removeItem(props.persistenceKey)
    }
  }
}

const saveExpandedState = () => {
  if (!props.persistenceKey) return
  localStorage.setItem(props.persistenceKey, JSON.stringify(expandedState.value))
}

const handleNodeExpand = (data: BaseTreeItem) => {
  if (data.itemType === props.folderItemType) {
    expandedState.value[data.id] = true
    saveExpandedState()
  }
  emit('node-expand', data)
}

const handleNodeCollapse = (data: BaseTreeItem) => {
  if (data.itemType === props.folderItemType) {
    delete expandedState.value[data.id]
    saveExpandedState()
  }
}

watch(
  () => props.data,
  (newData) => {
    if (newData.length > 0 && treeRef.value && Object.keys(expandedState.value).length > 0) {
      nextTick(() => {
        Object.keys(expandedState.value).forEach((key) => {
          const node = treeRef.value!.getNode(key)
          if (node && !node.expanded) {
            node.expand()
            const item = node.data as BaseTreeItem
            if (item && item.itemType === props.folderItemType) {
              emit('node-expand', item)
            }
          }
        })
      })
    }
  },
  { deep: true, flush: 'post' },
)

onMounted(() => {
  loadExpandedState()
})

const scrollToKey = async (key: string) => {
  await nextTick()
  const node = treeRef.value?.getNode(key)
  if (node) {
    let parent = node.parent
    while (parent && parent.level > 0) {
      parent.expand()
      if (parent.data) {
        const parentData = parent.data as BaseTreeItem
        if (parentData.itemType === props.folderItemType) {
          emit('node-expand', parentData)
        }
      }
      parent = parent.parent
    }
    await nextTick()
    treeRef.value?.setCurrentKey(key)
    const currentEl = treeRef.value?.$el.querySelector('.is-current')
    currentEl?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }
}

defineExpose({ scrollToKey })
</script>

<style scoped>
.explorer-tree-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.explorer-tree-header {
  flex-shrink: 0;
  padding: 16px 16px 8px 16px;
  cursor: default;
}
.explorer-tree-scrollbar {
  flex-grow: 1;
  padding: 0 12px;
}
.loading-container {
  padding: 0 10px;
}
.custom-tree {
  background-color: transparent;
}

:deep(.el-tree-node__content) {
  height: 36px;
  border-radius: 4px;
  margin: 0 0 2px 0;
  position: relative;
}

:deep(.el-tree-node.is-current > .el-tree-node__content) {
  background-color: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
}
:deep(.el-tree-node__content:hover) {
  background-color: var(--color-background-mute);
}
.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  padding-right: 8px;
  overflow: hidden;
  width: 100%;
  height: 100%;
}
.custom-tree-node.is-drag-over {
  background-color: var(--el-color-primary-light-8);
  outline: 1px dashed var(--el-color-primary);
}
.node-icon-wrapper {
  margin-right: 8px;
  font-size: 16px;
  display: flex;
  align-items: center;
  color: var(--el-text-color-secondary);
}
.node-label {
  flex-grow: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  margin-right: 8px;
}
/* 【新增】后缀容器样式 */
.node-suffix-wrapper {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.loading-icon {
  animation: rotating 2s linear infinite;
  color: var(--el-text-color-secondary);
  margin-left: 4px;
}
@keyframes rotating {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>

<style>
.is-hidden-node {
  display: none !important;
}

.tree-with-lines .el-tree-node__children {
  position: relative;
  margin-left: 5px;
  border-left: 3px solid var(--el-border-color-lighter);
}

.tree-with-lines .el-tree-node__children:hover {
  border-left-color: var(--el-color-primary-light-5);
}
</style>
