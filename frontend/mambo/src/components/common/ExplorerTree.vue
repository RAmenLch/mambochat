<!-- frontend/mambo/src/components/common/ExplorerTree.vue -->
<template>
  <div class="explorer-tree-container" @contextmenu.prevent="handleRootContextMenu">
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
        :indent="8"
        @node-click="handleNodeClick"
        @node-drop="handleNodeDrop"
        @node-contextmenu="handleNodeContextMenu"
        @node-expand="handleNodeExpand"
        @node-collapse="handleNodeCollapse"
        class="custom-tree"
        :props="treeProps"
      >
        <template #default="{ node, data }">
          <span class="custom-tree-node">
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

            <!-- Loading Indicator for Lazy Loading -->
            <el-icon v-if="loadingNodes.has(data.id)" class="is-loading loading-icon">
              <Loading />
            </el-icon>
          </span>
        </template>
      </el-tree>
      <el-empty v-else :description="emptyText" />
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed } from 'vue';
import { ElTree } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';
import type { AllowDropType, NodeDropType } from 'element-plus/es/components/tree/src/tree.type';
import type Node from 'element-plus/es/components/tree/src/model/node';
import type { BaseTreeItem, MoveRequest, MoveAction } from '@/api/types';

// --- Props & Emits ---

interface Props {
  data: BaseTreeItem[];
  currentId?: string | null;
  isLoading?: boolean;
  emptyText?: string;
  folderItemType?: string;
  persistenceKey?: string;
  // 外部传入的正在加载的文件夹ID集合，用于显示局部 Loading
  loadingFolderIds?: Set<string>;
}

const props = withDefaults(defineProps<Props>(), {
  currentId: null,
  isLoading: false,
  emptyText: '暂无数据',
  folderItemType: 'folder',
  persistenceKey: undefined,
  loadingFolderIds: () => new Set(),
});

const emit = defineEmits<{
  (e: 'node-click', data: BaseTreeItem): void;
  (e: 'node-contextmenu', event: MouseEvent, data: BaseTreeItem, node: Node): void;
  (e: 'root-contextmenu', event: MouseEvent): void;
  // 替换原有的 reorder 事件，改为 move 事件
  (e: 'move', req: MoveRequest): void;
  // 新增：节点展开事件，用于触发懒加载
  (e: 'node-expand', data: BaseTreeItem): void;
}>();

// --- State ---

const treeRef = ref<InstanceType<typeof ElTree>>();
const expandedState = ref<Record<string, boolean>>({});

// 计算属性：合并本地 loading 状态（如果有）和 props 传入的状态
const loadingNodes = computed(() => props.loadingFolderIds);

const treeProps = {
  label: 'name',
  children: 'children',
  // 在手动管理数据的懒加载模式下，我们不需要 el-tree 的 load 方法
  // 而是通过 data 的动态变化来驱动
  isLeaf: (data: TreeNodeData) => {
    // 只有非文件夹类型才被视为叶子节点
    // 文件夹即使当前没有 children，也被视为非叶子（可展开），以便触发加载
    return (data as BaseTreeItem).itemType !== props.folderItemType;
  },
  class: (data: TreeNodeData) => {
    return (data as BaseTreeItem).itemType === 'stub' ? 'is-hidden-node' : '';
  }
};

// --- Tree Event Handlers ---

const handleNodeClick = (data: BaseTreeItem) => {
  emit('node-click', data);
};

const handleNodeContextMenu = (event: MouseEvent, data: BaseTreeItem, node: Node) => {
  emit('node-contextmenu', event, data, node);
};

const handleRootContextMenu = (event: MouseEvent) => {
  emit('root-contextmenu', event);
};

// --- Drag & Drop Logic (Refactored for Move API) ---

const allowDrop = (draggingNode: Node, dropNode: Node, dropType: AllowDropType) => {
  // 不允许将节点拖入非文件夹节点内部
  if ((dropNode.data as BaseTreeItem).itemType !== props.folderItemType && dropType === 'inner') {
    return false;
  }
  return true;
};

const handleNodeDrop = (draggingNode: Node, dropNode: Node, dropType: NodeDropType) => {
  // 将 el-tree 的 dropType 映射为后端的 MoveAction
  let action: MoveAction;
  let referenceId: string;

  const draggingData = draggingNode.data as BaseTreeItem;
  const dropData = dropNode.data as BaseTreeItem;

  if (dropType === 'inner') {
    action = 'inside';
    referenceId = dropData.id;
  } else if (dropType === 'before') {
    action = 'before';
    referenceId = dropData.id;
  } else if (dropType === 'after') {
    action = 'after';
    referenceId = dropData.id;
  } else {
    // Should not happen given allowDrop
    return;
  }

  const req: MoveRequest = {
    item_ids: [draggingData.id],
    reference_id: referenceId,
    action: action,
  };

  emit('move', req);
};

// --- Expansion & Lazy Loading Logic ---

const loadExpandedState = () => {
  if (!props.persistenceKey) return;
  const savedState = localStorage.getItem(props.persistenceKey);
  if (savedState) {
    try {
      expandedState.value = JSON.parse(savedState);
    } catch (e) {
      console.error('Failed to parse expanded state', e);
      localStorage.removeItem(props.persistenceKey);
    }
  }
};

const saveExpandedState = () => {
  if (!props.persistenceKey) return;
  localStorage.setItem(props.persistenceKey, JSON.stringify(expandedState.value));
};

const handleNodeExpand = (data: BaseTreeItem) => {
  // 1. 记录展开状态
  if (data.itemType === props.folderItemType) {
    expandedState.value[data.id] = true;
    saveExpandedState();
  }

  // 2. 触发懒加载事件
  emit('node-expand', data);
};

const handleNodeCollapse = (data: BaseTreeItem) => {
  if (data.itemType === props.folderItemType) {
    delete expandedState.value[data.id];
    saveExpandedState();
  }
};

// 监听数据变化，恢复展开状态
// 注意：在懒加载模式下，数据是增量到来的。
// 当新数据到来时，如果它包含在 expandedState 中，我们需要确保它是展开的。
watch(() => props.data, (newData) => {
  if (newData.length > 0 && treeRef.value && Object.keys(expandedState.value).length > 0) {
    nextTick(() => {
      Object.keys(expandedState.value).forEach(key => {
        // 只有当节点存在于当前树中时才尝试展开
        const node = treeRef.value!.getNode(key);
        if (node && !node.expanded) {
          node.expand();
        }
      });
    });
  }
}, { deep: true, flush: 'post' });

// --- Lifecycle ---

onMounted(() => {
  loadExpandedState();
});

const scrollToKey = async (key: string) => {
  await nextTick();
  const node = treeRef.value?.getNode(key);
  if (node) {
    let parent = node.parent;
    while (parent && parent.level > 0) {
      parent.expand();
      parent = parent.parent;
    }
    await nextTick();
    treeRef.value?.setCurrentKey(key);
    const currentEl = treeRef.value?.$el.querySelector('.is-current');
    currentEl?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
};

defineExpose({
  scrollToKey,
});
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
  height: 40px;
  border-radius: 6px;
  margin: 0 4px 4px 4px;
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

.node-icon-wrapper {
  margin-right: 8px;
  font-size: 16px;
  display: flex;
  align-items: center;
}

.node-label {
  flex-grow: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  margin-right: 8px;
}

.loading-icon {
  animation: rotating 2s linear infinite;
  color: var(--el-text-color-secondary);
  margin-left: 4px;
}

@keyframes rotating {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>

<style>
/* Global style to hide stub nodes created for lazy loading triggers */
.is-hidden-node {
  display: none !important;
}
</style>
