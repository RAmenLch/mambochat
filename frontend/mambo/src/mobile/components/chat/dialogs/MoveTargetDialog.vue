<!-- frontend/mambo/src/mobile/components/chat/dialogs/MoveTargetDialog.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t('chat.move.title')"
    width="90%"
    :close-on-click-modal="false"
    class="move-target-dialog"
  >
    <div class="move-dialog-content">
      <!-- 根目录选项 -->
      <div
        class="target-item root-item"
        :class="{ 'is-selected': selectedTargetId === 'root' }"
        @click="selectTarget('root')"
      >
        <el-icon><HomeFilled /></el-icon>
        <span>{{ $t('chat.move.rootFolder') }}</span>
      </div>

      <el-divider />

      <!-- 文件夹树 -->
      <div class="tree-container">
        <div v-if="filteredTreeData.length === 0" class="empty-placeholder">
          {{ $t('chat.move.noFolder') }}
        </div>
        <el-tree
          v-else
          :data="filteredTreeData"
          :props="defaultProps"
          node-key="id"
          :expand-on-click-node="false"
          :default-expanded-keys="expandedKeys"
          highlight-current
          @node-click="handleNodeClick"
        >
          <template #default="{ data }">
            <div class="tree-node-content" :class="{ 'is-disabled': isDisabled(data) }">
              <el-icon><Folder /></el-icon>
              <span>{{ data.name }}</span>
            </div>
          </template>
        </el-tree>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="confirmMove" :disabled="!canConfirm">
          {{ $t('common.action.confirm') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { HomeFilled, Folder } from '@element-plus/icons-vue'
import type { BaseTreeItem, ChatNode } from '@/api/types'

const { t } = useI18n()

interface Props {
  visible: boolean
  itemToMove: BaseTreeItem | null
  treeData: ChatNode[]
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  itemToMove: null,
  treeData: () => [],
})

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'confirm', targetId: string): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const selectedTargetId = ref<string | null>(null)
const expandedKeys = ref<string[]>([])

const defaultProps = {
  children: 'children',
  label: 'name',
}

// 过滤掉被移动项及其子项，并只保留文件夹
const filteredTreeData = computed(() => {
  if (!props.itemToMove) return props.treeData

  const filterNode = (nodes: ChatNode[]): ChatNode[] => {
    return nodes
      .filter((node) => {
        // 过滤掉非文件夹
        if (node.itemType !== 'folder') return false
        // 过滤掉自己
        if (node.id === props.itemToMove!.id) return false
        return true
      })
      .map((node) => ({
        ...node,
        children: node.children ? filterNode(node.children as ChatNode[]) : [],
      }))
      .filter((node) => {
        // 如果是文件夹但没有子节点，也保留
        if (node.itemType === 'folder') return true
        return node.children && node.children.length > 0
      })
  }

  return filterNode(props.treeData)
})

// 检查节点是否禁用（即是否是被移动项的子项）
const isDisabled = (node: BaseTreeItem) => {
  if (!props.itemToMove || props.itemToMove.itemType !== 'folder') return false

  const checkChildren = (id: string): boolean => {
    if (id === props.itemToMove!.id) return true
    const item = props.treeData.find((n) => n.id === id)
    if (item?.parentId) return checkChildren(item.parentId)
    return false
  }

  // 简单的前向检查：如果该节点的祖先包含被移动项，则禁用
  // 由于我们在filteredTreeData中已经过滤掉了被移动项，
  // 这里的禁用逻辑主要用于UI提示（虽然通常已经被过滤了）
  // 此处为了简化，假设过滤后的都是可选的，除非有特殊业务逻辑
  return false
}

const canConfirm = computed(() => selectedTargetId.value !== null)

const selectTarget = (id: string) => {
  selectedTargetId.value = id
}

const handleNodeClick = (data: BaseTreeItem) => {
  if (data.itemType === 'folder') {
    selectTarget(data.id)
  }
}

const confirmMove = () => {
  if (selectedTargetId.value) {
    emit('confirm', selectedTargetId.value)
    dialogVisible.value = false
  }
}

watch(
  () => props.visible,
  (val) => {
    if (val) {
      selectedTargetId.value = null
      // 默认展开第一层
      expandedKeys.value = props.treeData.filter((n) => n.itemType === 'folder').map((n) => n.id)
    }
  },
)
</script>

<style scoped>
.move-target-dialog :deep(.el-dialog__body) {
  padding: 10px 20px;
  max-height: 60vh;
  overflow-y: auto;
}

.target-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  margin-bottom: 5px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.target-item:hover {
  background-color: var(--el-fill-color-light);
}

.target-item.is-selected {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.root-item {
  font-weight: 500;
}

.tree-container {
  min-height: 200px;
}

.tree-node-content {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.tree-node-content.is-disabled {
  color: var(--el-text-color-placeholder);
  pointer-events: none;
}

.empty-placeholder {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 20px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
