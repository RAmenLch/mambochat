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
      <!--
         [修复] 移除 lazy 属性，回归完全受控的数据驱动模式。
         三角箭头的显示完全由数据中是否存在 children (包含 Stub) 决定。
      -->
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

            <!-- 局部 Loading 指示器 -->
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
import type {
  AllowDropType,
  NodeDropType,
  TreeNodeData
} from 'element-plus/es/components/tree/src/tree.type';
import type Node from 'element-plus/es/components/tree/src/model/node';
import type { BaseTreeItem, MoveRequest, MoveAction } from '@/api/types';

interface Props {
  data: BaseTreeItem[];
  currentId?: string | null;
  isLoading?: boolean;
  emptyText?: string;
  folderItemType?: string;
  persistenceKey?: string;
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
  (e: 'move', req: MoveRequest): void;
  (e: 'node-expand', data: BaseTreeItem): void;
}>();

const treeRef = ref<InstanceType<typeof ElTree>>();
const expandedState = ref<Record<string, boolean>>({});

const loadingNodes = computed(() => props.loadingFolderIds);

const treeProps = {
  label: 'name',
  children: 'children',
  // 即使不开启 lazy，isLeaf 也能辅助 CSS 样式，但核心控制权在于 children 数组不为空
  isLeaf: (data: TreeNodeData) => {
    return (data as BaseTreeItem).itemType !== props.folderItemType;
  },
  // 关键 CSS 类：隐藏 Stub 节点
  class: (data: TreeNodeData) => {
    return (data as BaseTreeItem).itemType === 'stub' ? 'is-hidden-node' : '';
  }
};

const handleNodeClick = (data: BaseTreeItem) => {
  emit('node-click', data);
};

const handleNodeContextMenu = (event: MouseEvent, data: BaseTreeItem, node: Node) => {
  emit('node-contextmenu', event, data, node);
};

const handleRootContextMenu = (event: MouseEvent) => {
  emit('root-contextmenu', event);
};

// --- Drag & Drop ---
const allowDrop = (draggingNode: Node, dropNode: Node, dropType: AllowDropType) => {
  if ((dropNode.data as BaseTreeItem).itemType !== props.folderItemType && dropType === 'inner') {
    return false;
  }
  return true;
};

const handleNodeDrop = (draggingNode: Node, dropNode: Node, dropType: NodeDropType) => {
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
    return;
  }

  const req: MoveRequest = {
    item_ids: [draggingData.id],
    reference_id: referenceId,
    action: action,
  };
  emit('move', req);
};

// --- Expansion Logic ---

const loadExpandedState = () => {
  if (!props.persistenceKey) return;
  const savedState = localStorage.getItem(props.persistenceKey);
  if (savedState) {
    try {
      expandedState.value = JSON.parse(savedState);
    } catch (e) {
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
  // 触发懒加载
  emit('node-expand', data);
};

const handleNodeCollapse = (data: BaseTreeItem) => {
  if (data.itemType === props.folderItemType) {
    delete expandedState.value[data.id];
    saveExpandedState();
  }
};

// [关键修复] 当数据更新（例如根目录加载完成）时，恢复展开状态
watch(() => props.data, (newData) => {
  if (newData.length > 0 && treeRef.value && Object.keys(expandedState.value).length > 0) {
    nextTick(() => {
      Object.keys(expandedState.value).forEach(key => {
        const node = treeRef.value!.getNode(key);
        // 如果节点存在、理论上应该展开、但实际上还没展开
        if (node && !node.expanded) {
          node.expand();

          // [Fix Problem 2]: 仅仅 node.expand() 只是 UI 展开
          // 我们必须通知上层组件去 fetch 它的子节点
          const item = node.data as BaseTreeItem;
          if (item && item.itemType === props.folderItemType) {
            emit('node-expand', item);
          }
        }
      });
    });
  }
}, { deep: true, flush: 'post' });

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
      // 在编程式展开路径时，同样要确保触发数据加载
      if (parent.data) {
        const parentData = parent.data as BaseTreeItem;
        if (parentData.itemType === props.folderItemType) {
          emit('node-expand', parentData);
        }
      }
      parent = parent.parent;
    }
    await nextTick();
    treeRef.value?.setCurrentKey(key);
    const currentEl = treeRef.value?.$el.querySelector('.is-current');
    currentEl?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
};

defineExpose({ scrollToKey });
</script>

<style scoped>
/* Previous styles remain the same */
.explorer-tree-container { height: 100%; display: flex; flex-direction: column; box-sizing: border-box; }
.explorer-tree-header { flex-shrink: 0; padding: 16px 16px 8px 16px; cursor: default; }
.explorer-tree-scrollbar { flex-grow: 1; padding: 0 12px; }
.loading-container { padding: 0 10px; }
.custom-tree { background-color: transparent; }
:deep(.el-tree-node__content) { height: 40px; border-radius: 6px; margin: 0 4px 4px 4px; }
:deep(.el-tree-node.is-current > .el-tree-node__content) { background-color: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-7); }
:deep(.el-tree-node__content:hover) { background-color: var(--color-background-mute); }
.custom-tree-node { flex: 1; display: flex; align-items: center; justify-content: space-between; font-size: 14px; padding-right: 8px; overflow: hidden; width: 100%; height: 100%; }
.node-icon-wrapper { margin-right: 8px; font-size: 16px; display: flex; align-items: center; }
.node-label { flex-grow: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; margin-right: 8px; }
.loading-icon { animation: rotating 2s linear infinite; color: var(--el-text-color-secondary); margin-left: 4px; }
@keyframes rotating { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>

<style>
/*
  [Fix Problem 1] 隐藏 Stub 节点
  通过 treeHelper 生成的 Stub 节点会有这个类名，从而被隐藏。
  这样用户看到的只是一个“展开后没有内容”的文件夹，而不是一行空白。
*/
.is-hidden-node {
  display: none !important;
}
</style>
