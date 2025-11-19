<template>
  <div class="explorer-tree-container" @contextmenu.prevent="handleRootContextMenu">
    <div class="explorer-tree-header" v-if="$slots.header">
      <slot name="header"></slot>
    </div>

    <el-scrollbar class="explorer-tree-scrollbar">
      <div v-if="isLoading" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>
      <el-tree
        v-else-if="data.length > 0"
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
        :props="{ label: 'name', children: 'children' }"
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
          </span>
        </template>
      </el-tree>
      <el-empty v-else :description="emptyText" />
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue';
import { ElTree } from 'element-plus';
import type { AllowDropType, NodeDropType } from 'element-plus/es/components/tree/src/tree.type';
import type Node from 'element-plus/es/components/tree/src/model/node';
import type { BaseTreeItem, TreeReorderEvent } from '@/api/types';

// --- Props & Emits ---

interface Props {
  data: BaseTreeItem[];
  currentId?: string | null;
  isLoading?: boolean;
  emptyText?: string;
  folderItemType?: string;
  persistenceKey?: string;
}

const props = withDefaults(defineProps<Props>(), {
  currentId: null,
  isLoading: false,
  emptyText: '暂无数据',
  folderItemType: 'folder',
  persistenceKey: undefined,
});

const emit = defineEmits<{
  (e: 'node-click', data: BaseTreeItem): void;
  (e: 'node-contextmenu', event: MouseEvent, data: BaseTreeItem, node: Node): void;
  // 新增：根区域右键事件
  (e: 'root-contextmenu', event: MouseEvent): void;
  (e: 'reorder', updates: TreeReorderEvent[]): void;
}>();

// --- State ---

const treeRef = ref<InstanceType<typeof ElTree>>();
const expandedState = ref<Record<string, boolean>>({});

// --- Tree Event Handlers ---

const handleNodeClick = (data: BaseTreeItem) => {
  emit('node-click', data);
};

const handleNodeContextMenu = (event: MouseEvent, data: BaseTreeItem, node: Node) => {
  // ElTree 的 node-contextmenu 会阻止冒泡，所以这里只处理节点上的右键
  emit('node-contextmenu', event, data, node);
};

// 新增：处理容器背景的右键点击
const handleRootContextMenu = (event: MouseEvent) => {
  emit('root-contextmenu', event);
};

// --- Drag & Drop Logic ---

const allowDrop = (draggingNode: Node, dropNode: Node, dropType: AllowDropType) => {
  return !((dropNode.data as BaseTreeItem).itemType !== props.folderItemType && dropType === 'inner');
};

const handleNodeDrop = (draggingNode: Node, dropNode: Node, dropType: NodeDropType) => {
  let parentId: string | null = null;
  let siblings: Node[] = [];

  if (dropType === 'inner') {
    parentId = (dropNode.data as BaseTreeItem).id;
    siblings = dropNode.childNodes || [];
  } else {
    parentId = (dropNode.data as BaseTreeItem).parentId;
    siblings = dropNode.parent?.childNodes || treeRef.value?.root.childNodes || [];
  }

  const updates: TreeReorderEvent[] = siblings.map((node, index) => ({
    id: (node.data as BaseTreeItem).id,
    parentId,
    sortOrder: index,
  }));

  if (updates.length > 0) {
    emit('reorder', updates);
  }
};

// --- Expansion Persistence Logic ---

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
  if (data.itemType === props.folderItemType) {
    expandedState.value[data.id] = true;
    saveExpandedState();
  }
};

const handleNodeCollapse = (data: BaseTreeItem) => {
  if (data.itemType === props.folderItemType) {
    delete expandedState.value[data.id];
    saveExpandedState();
  }
};

watch(() => props.data, (newData) => {
  if (!props.persistenceKey) return;

  const getAllFolderIds = (nodes: any[]): Set<string> => {
    let ids = new Set<string>();
    for (const node of nodes) {
      if (node.itemType === props.folderItemType) {
        ids.add(node.id);
        if (node.children) {
          const childIds = getAllFolderIds(node.children);
          childIds.forEach(id => ids.add(id));
        }
      }
    }
    return ids;
  };

  const folderIds = getAllFolderIds(newData);
  const hasChanged = Object.keys(expandedState.value).some(id => !folderIds.has(id));

  if (hasChanged) {
    expandedState.value = Object.fromEntries(
      Object.entries(expandedState.value).filter(([key]) => folderIds.has(key))
    );
    saveExpandedState();
  }
}, { deep: true });

watch(() => props.data, (newData) => {
  if (newData.length > 0 && treeRef.value && Object.keys(expandedState.value).length > 0) {
    nextTick(() => {
      Object.keys(expandedState.value).forEach(key => {
        const node = treeRef.value!.getNode(key);
        if (node && !node.expanded) {
          node.expand();
        }
      });
    });
  }
}, { flush: 'post' });

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
</style>
