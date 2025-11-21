<!-- frontend/mambo/src/components/chat/dialogs/ResourceSelectorDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    title="从资源库选择"
    width="70%"
    @update:model-value="val => emit('update:visible', val)"
    @close="handleDialogClose"
  >
    <div class="resource-selector-body">
      <div class="toolbar">
        <el-input v-model="searchText" placeholder="搜索资源名称..." clearable class="search-input" />
        <div class="multi-select-switch">
          <span>多选模式</span>
          <el-switch v-model="isMultiSelectMode" />
        </div>
      </div>
      <el-container class="resource-selector-container">
        <el-aside width="280px" class="resource-tree-aside">
          <el-scrollbar>
            <div v-if="isResourcesLoading" class="loading-state">
              <el-skeleton :rows="5" animated />
            </div>
            <el-tree
              v-else
              ref="treeRef"
              :data="filteredTreeData"
              node-key="id"
              :props="{ label: 'name', children: 'children' }"
              :filter-node-method="filterNode"
              @node-click="handleNodeClick"
            >
              <template #default="{ data }">
                <span
                  class="custom-tree-node"
                  :class="{
                    'is-selected': isNodeSelected(data),
                    'is-disabled': isNodeDisabled(data)
                  }"
                >
                  <span class="node-content">
                    <el-icon>
                      <Folder v-if="data.itemType === 'folder'" />
                      <Memo v-else-if="data.resourceType === 'submessage_template'" />
                      <Document v-else />
                    </el-icon>
                    <span class="node-label">{{ data.name }}</span>
                  </span>

                  <!-- 仅显示中文类型的 Tag -->
                  <el-tag
                    v-if="data.itemType === 'resource' && data.resourceType"
                    size="small"
                    type="info"
                    class="resource-type-tag"
                  >
                    {{ getReadableResourceType(data.resourceType) }}
                  </el-tag>
                </span>
              </template>
            </el-tree>
          </el-scrollbar>
        </el-aside>
        <el-main class="resource-preview-main">
          <el-empty v-if="selectedResources.length === 0" description="从左侧选择一个资源以预览" />

          <!-- 单选预览 -->
          <el-card v-else-if="selectedResources.length === 1" shadow="never" class="preview-card">
            <template #header>
              <div class="preview-header">
                <strong>预览: {{ selectedResources[0].name }}</strong>
              </div>
            </template>
            <el-scrollbar class="preview-scrollbar">
              <pre class="preview-content">{{ selectedResources[0].latest_version?.content || '该资源没有内容' }}</pre>
            </el-scrollbar>
          </el-card>

          <!-- 多选列表 -->
          <el-card v-else shadow="never" class="preview-card">
             <template #header>
              <div class="preview-header">
                <strong>已选择 {{ selectedResources.length }} 个项目</strong>
              </div>
            </template>
            <el-scrollbar class="preview-scrollbar">
              <ul class="selection-list">
                <li v-for="resource in selectedResources" :key="resource.id">
                  {{ resource.name }}
                </li>
              </ul>
            </el-scrollbar>
          </el-card>
        </el-main>
      </el-container>
    </div>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        @click="handleConfirmSelection"
        :disabled="selectedResources.length === 0"
      >
        使用
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { ElTree } from 'element-plus';
import type { TreeNodeData } from 'element-plus/es/components/tree/src/tree.type';
import { Folder, Document, Memo } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import { useResourceStore } from '@/stores/resourceStore';
import type { Resource, ResourceNode, ResourceType } from '@/api/types';

// --- Component Interface ---
const props = defineProps<{
  visible: boolean;
  resourceTypeFilter?: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'select-resource', resources: Resource[]): void;
}>();

// --- Store ---
const resourceStore = useResourceStore();
const { resourceTree, isResourcesLoading } = storeToRefs(resourceStore);

// --- Local State ---
const searchText = ref('');
const treeRef = ref<InstanceType<typeof ElTree>>();
const selectedResources = ref<Resource[]>([]);
const isMultiSelectMode = ref(false);
const selectionType = ref<ResourceType | null>(null);
const STORAGE_KEY = 'resource_selector_multi_select_mode';

// --- Lifecycle ---
onMounted(() => {
  const persistedMode = localStorage.getItem(STORAGE_KEY);
  isMultiSelectMode.value = persistedMode === 'true';
});

// --- Computed ---
const filteredTreeData = computed(() => filterTreeByType(resourceTree.value));

function filterTreeByType(nodes: ResourceNode[]): ResourceNode[] {
  if (!props.resourceTypeFilter) return nodes;
  const result: ResourceNode[] = [];
  for (const node of nodes) {
    if (node.itemType === 'folder') {
      const children = filterTreeByType(node.children || []);
      if (children.length > 0) result.push({ ...node, children });
    } else if (node.resourceType === props.resourceTypeFilter) {
      result.push(node);
    }
  }
  return result;
}

// --- Watchers ---
watch(() => props.visible, (isVisible) => {
  if (isVisible) resourceStore.fetchResources();
});

watch(searchText, (val) => {
  treeRef.value?.filter(val);
});

watch(isMultiSelectMode, (newMode) => {
  localStorage.setItem(STORAGE_KEY, String(newMode));
  selectedResources.value = [];
  selectionType.value = null;
});

// --- Helper Methods ---
const getReadableResourceType = (type: string | null) => {
  if (!type) return '未知';
  const map: Record<string, string> = {
    'system_prompt': '系统提示词',
    'submessage_template': '消息模板'
  };
  return map[type] || type;
};

const isNodeSelected = (data: ResourceNode): boolean => {
  return selectedResources.value.some(r => r.id === data.id);
};

const isNodeDisabled = (data: ResourceNode): boolean => {
  if (!isMultiSelectMode.value || !selectionType.value) return false;
  if (data.itemType === 'folder') return false;
  return data.resourceType !== selectionType.value;
};

// --- Interaction Methods ---
const filterNode = (value: string, data: TreeNodeData): boolean => {
  if (!value) return true;
  return (data as ResourceNode).name.toLowerCase().includes(value.toLowerCase());
};

const handleNodeClick = (data: TreeNodeData) => {
  const resource = data as ResourceNode;
  // 如果不是资源，或者被禁用了，直接返回
  if (resource.itemType !== 'resource' || isNodeDisabled(resource)) return;

  if (!isMultiSelectMode.value) {
    selectedResources.value = [resource];
    return;
  }

  // 多选逻辑
  if (selectedResources.value.length === 0) {
    selectedResources.value.push(resource);
    selectionType.value = resource.resourceType;
  } else {
    // 双重检查类型，虽然 isNodeDisabled 已经防住了
    if (resource.resourceType !== selectionType.value) return;

    const index = selectedResources.value.findIndex(r => r.id === resource.id);
    if (index > -1) {
      selectedResources.value.splice(index, 1);
      // 如果清空了选择，重置类型限制
      if (selectedResources.value.length === 0) {
        selectionType.value = null;
      }
    } else {
      selectedResources.value.push(resource);
    }
  }
};

function handleConfirmSelection() {
  if (selectedResources.value.length === 0) return;
  emit('select-resource', selectedResources.value);
  emit('update:visible', false);
}

function handleDialogClose() {
  searchText.value = '';
  selectedResources.value = [];
  selectionType.value = null;
}
</script>

<style scoped>
.resource-selector-body { display: flex; flex-direction: column; height: 60vh; }
.toolbar { display: flex; align-items: center; gap: 20px; margin-bottom: 16px; flex-shrink: 0; }
.search-input { flex-grow: 1; }
.multi-select-switch { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--el-text-color-regular); }
.resource-selector-container { flex-grow: 1; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; overflow: hidden; }
.resource-tree-aside { border-right: 1px solid var(--el-border-color-lighter); }

/* Tree Node Styling */
.custom-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between; /* 让 Tag 靠右 */
  width: 100%;
  padding: 2px 0;
  padding-right: 8px; /* 右侧留白给 Tag */
}

.custom-tree-node.is-selected {
  background-color: var(--el-color-primary-light-9);
}

/* 禁用状态样式：灰色文字，鼠标显示禁止符号 */
.custom-tree-node.is-disabled {
  color: var(--el-text-color-disabled);
  cursor: not-allowed;
}
.custom-tree-node.is-disabled .el-icon,
.custom-tree-node.is-disabled .resource-type-tag {
  opacity: 0.6;
}

.node-content {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}
.node-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.resource-type-tag {
  flex-shrink: 0;
  margin-left: 8px;
}

/* Preview Area */
.resource-preview-main { padding: 0; }
.preview-card { height: 100%; border: none; display: flex; flex-direction: column; }
:deep(.preview-card .el-card__header) { flex-shrink: 0; }
:deep(.preview-card .el-card__body) { flex-grow: 1; padding: 0; overflow: hidden; }
.preview-scrollbar { padding: 20px; }
.preview-content { white-space: pre-wrap; word-wrap: break-word; font-family: var(--el-font-family); font-size: 14px; margin: 0; }
.loading-state { padding: 20px; }
.selection-list { list-style-type: none; padding-left: 0; margin: 0; }
.selection-list li { padding: 4px 0; font-size: 14px; border-bottom: 1px solid var(--el-border-color-lighter); }
.selection-list li:last-child { border-bottom: none; }
</style>
