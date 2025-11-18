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
      <el-input v-model="searchText" placeholder="搜索资源名称..." clearable class="search-input" />
      <el-container class="resource-selector-container">
        <el-aside width="250px" class="resource-tree-aside">
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
              highlight-current
              @node-click="handleNodeClick"
            >
              <template #default="{ data }">
                <span class="custom-tree-node">
                  <el-icon>
                    <Folder v-if="data.itemType === 'folder'" />
                    <Document v-else />
                  </el-icon>
                  <span class="node-label">{{ data.name }}</span>
                </span>
              </template>
            </el-tree>
          </el-scrollbar>
        </el-aside>
        <el-main class="resource-preview-main">
          <el-card v-if="selectedForPreview" shadow="never" class="preview-card">
            <template #header>
              <div class="preview-header">
                <strong>预览: {{ selectedForPreview.name }}</strong>
              </div>
            </template>
            <el-scrollbar class="preview-scrollbar">
              <pre class="preview-content">{{ selectedForPreview.latest_version?.content || '该资源没有内容' }}</pre>
            </el-scrollbar>
          </el-card>
          <el-empty v-else description="从左侧选择一个资源以预览" />
        </el-main>
      </el-container>
    </div>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        @click="handleConfirmSelection"
        :disabled="!selectedForPreview || !selectedForPreview.latest_version?.content"
      >
        追加内容
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { ElTree } from 'element-plus';
import { Folder, Document } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import { useResourceStore } from '@/stores/resourceStore';
import type { Resource, ResourceNode } from '@/api/types';

// --- Component Interface: Props & Emits ---
const props = defineProps<{
  visible: boolean;
  resourceTypeFilter?: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'append-content', content: string): void;
}>();

// --- Store Integration ---
const resourceStore = useResourceStore();
const { resourceTree, isResourcesLoading } = storeToRefs(resourceStore);

// --- Local State ---
const searchText = ref('');
const treeRef = ref<InstanceType<typeof ElTree>>();
const selectedForPreview = ref<Resource | null>(null);

// --- Computed Properties ---
/**
 * Filters the entire resource tree based on the `resourceTypeFilter` prop.
 * @param nodes The resource nodes to filter.
 * @returns A new array of filtered resource nodes.
 */
const filterTreeByType = (nodes: ResourceNode[]): ResourceNode[] => {
  if (!props.resourceTypeFilter) {
    return nodes;
  }
  const result: ResourceNode[] = [];
  for (const node of nodes) {
    if (node.itemType === 'folder') {
      const children = filterTreeByType(node.children || []);
      if (children.length > 0) {
        result.push({ ...node, children });
      }
    } else if (node.resourceType === props.resourceTypeFilter) {
      result.push(node);
    }
  }
  return result;
};

const filteredTreeData = computed(() => filterTreeByType(resourceTree.value));

// --- Watchers ---
watch(() => props.visible, (isVisible) => {
  if (isVisible && resourceStore.resources.length === 0) {
    resourceStore.fetchResources();
  }
});

watch(searchText, (val) => {
  treeRef.value?.filter(val);
});

// --- Methods ---
/**
 * Method for the el-tree's `filter-node-method` prop to filter nodes by name.
 * The `data` parameter is typed as `any` to match the signature of ElTree's prop.
 */
const filterNode = (value: string, data: any): boolean => {
  if (!value) return true;
  return (data as ResourceNode).name.toLowerCase().includes(value.toLowerCase());
};

/**
 * Handles clicks on tree nodes, setting the selected item for preview if it's a resource.
 * The `data` parameter is typed as `any` to match the signature of ElTree's event.
 */
const handleNodeClick = (data: any) => {
  const resource = data as ResourceNode;
  if (resource.itemType === 'resource') {
    selectedForPreview.value = resource;
  }
};

/**
 * Emits the selected resource's content and closes the dialog.
 */
function handleConfirmSelection() {
  if (!selectedForPreview.value || !selectedForPreview.value.latest_version?.content) {
    return;
  }
  const contentToAppend = selectedForPreview.value.latest_version.content;
  emit('append-content', contentToAppend);
  emit('update:visible', false);
}

/**
 * Resets the dialog's internal state when it is closed.
 */
function handleDialogClose() {
  searchText.value = '';
  selectedForPreview.value = null;
  // The tree filter will reset automatically due to the searchText watcher.
}
</script>

<style scoped>
.resource-selector-body {
  display: flex;
  flex-direction: column;
  height: 60vh;
}
.search-input {
  margin-bottom: 16px;
  flex-shrink: 0;
}
.resource-selector-container {
  flex-grow: 1;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
}
.resource-tree-aside {
  border-right: 1px solid var(--el-border-color-lighter);
}
.custom-tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
}
.node-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.resource-preview-main {
  padding: 0;
}
.preview-card {
  height: 100%;
  border: none;
  display: flex;
  flex-direction: column;
}
:deep(.preview-card .el-card__header) {
  flex-shrink: 0;
}
:deep(.preview-card .el-card__body) {
  flex-grow: 1;
  padding: 0;
  overflow: hidden;
}
.preview-scrollbar {
  padding: 20px;
}
.preview-content {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: var(--el-font-family);
  font-size: 14px;
  margin: 0;
}
.loading-state {
  padding: 20px;
}
</style>
