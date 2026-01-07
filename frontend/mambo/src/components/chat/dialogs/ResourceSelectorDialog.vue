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
            <div v-if="isResourcesLoading && resourceTree.length === 0" class="loading-state">
              <el-skeleton :rows="5" animated />
            </div>
            <el-tree
              v-else
              ref="treeRef"
              :data="filteredTreeData"
              node-key="id"
              :props="treeProps"
              :filter-node-method="filterNode"
              @node-click="handleNodeClick"
              @node-expand="handleNodeExpand"
              @node-collapse="handleNodeCollapse"
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
                    <!-- 显示局部加载状态 -->
                    <el-icon v-if="loadingFolders.has(data.id)" class="is-loading loading-icon">
                      <Loading />
                    </el-icon>
                  </span>

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
            <el-scrollbar class="preview-scrollbar" v-loading="isPreviewLoading">
              <pre class="preview-content">{{ selectedResources[0].latest_version?.content || '该资源没有内容' }}</pre>
            </el-scrollbar>
          </el-card>

          <!-- 多选预览 (合并内容) -->
          <el-card v-else shadow="never" class="preview-card">
             <template #header>
              <div class="preview-header">
                <strong>已选择 {{ selectedResources.length }} 个项目 (合并预览)</strong>
              </div>
            </template>
            <el-scrollbar class="preview-scrollbar" v-loading="isPreviewLoading">
              <!-- 这里改为遍历显示内容，或者显示合并后的内容 -->
              <div v-for="(res, index) in selectedResources" :key="res.id" class="multi-preview-item">
                <div class="multi-preview-label">#{{ index + 1 }} {{ res.name }}</div>
                <pre class="preview-content">{{ res.latest_version?.content || '正在加载内容...' }}</pre>
                <!-- 在项目之间显示分割线 -->
                <el-divider v-if="index < selectedResources.length - 1" border-style="dashed" />
              </div>
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
        使用 ({{ selectedResources.length }})
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { ElTree } from 'element-plus';
import type { TreeNodeData } from 'element-plus/es/components/tree/src/tree.type';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import type Node from 'element-plus/es/components/tree/src/model/node';
import { Folder, Document, Memo, Loading } from '@element-plus/icons-vue';
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
const { resourceTree, isResourcesLoading, loadingFolders, resources } = storeToRefs(resourceStore);

// --- Local State ---
const searchText = ref('');
const treeRef = ref<InstanceType<typeof ElTree>>();
const selectedResources = ref<Resource[]>([]);
const isMultiSelectMode = ref(false);
const selectionType = ref<ResourceType | null>(null);
const isPreviewLoading = ref(false); // 全局 Loading 状态
const STORAGE_KEY = 'resource_selector_multi_select_mode';

const expandedKeys = ref<Set<string>>(new Set());

// --- Lifecycle ---
onMounted(() => {
  const persistedMode = localStorage.getItem(STORAGE_KEY);
  isMultiSelectMode.value = persistedMode === 'true';
});

// --- Computed ---
const filteredTreeData = computed(() => filterTreeByType(resourceTree.value));

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: (data: TreeNodeData) => (data as ResourceNode).itemType !== 'folder'
};

function filterTreeByType(nodes: ResourceNode[]): ResourceNode[] {
  if (!props.resourceTypeFilter) return nodes;
  const result: ResourceNode[] = [];
  for (const node of nodes) {
    if (node.itemType === 'folder') {
      const children = filterTreeByType(node.children || []);
      result.push({ ...node, children });
    } else if (node.resourceType === props.resourceTypeFilter) {
      result.push(node);
    }
  }
  return result;
}

// --- Watchers ---
watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    resourceStore.initializeList();
    expandedKeys.value.clear();
  }
});

watch(searchText, (val) => {
  treeRef.value?.filter(val);
});

watch(isMultiSelectMode, (newMode) => {
  localStorage.setItem(STORAGE_KEY, String(newMode));
  selectedResources.value = [];
  selectionType.value = null;
});

watch(filteredTreeData, () => {
  nextTick(() => {
    if (!treeRef.value) return;
    expandedKeys.value.forEach((key) => {
      const node = treeRef.value!.getNode(key);
      if (node && !node.expanded) {
        node.expand();
      }
    });
  });
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

const handleNodeExpand = (data: ResourceNode) => {
  expandedKeys.value.add(data.id);
  if (data.itemType === 'folder') {
    resourceStore.fetchResourceChildren(data.id);
  }
};

const handleNodeCollapse = (data: ResourceNode) => {
  expandedKeys.value.delete(data.id);
};

const handleNodeClick = async (data: TreeNodeData) => {
  const resource = data as ResourceNode;
  if (resource.itemType !== 'resource' || isNodeDisabled(resource)) return;

  if (!isMultiSelectMode.value) {
    // 单选逻辑
    selectedResources.value = [resource];
    // 强制检查并加载
    if (!resource.latest_version?.content) {
      await loadResourcePreview(resource.id);
    }
  } else {
    // 多选逻辑
    if (selectedResources.value.length === 0) {
      selectedResources.value.push(resource);
      selectionType.value = resource.resourceType;
      // 检查第一个元素
      if (!resource.latest_version?.content) {
        await loadResourcePreview(resource.id);
      }
    } else {
      if (resource.resourceType !== selectionType.value) return;

      const index = selectedResources.value.findIndex(r => r.id === resource.id);
      if (index > -1) {
        // 取消选中
        selectedResources.value.splice(index, 1);
        if (selectedResources.value.length === 0) {
          selectionType.value = null;
        }
      } else {
        // 选中，添加到列表
        selectedResources.value.push(resource);

        // 【关键修复】: 立即检查并异步加载内容，不论这是第几个被选中的元素
        if (!resource.latest_version?.content) {
          // 不使用 await，让其并行请求，不阻塞 UI 继续选择
          // 设置 isPreviewLoading 仅仅是为了让右侧显示转圈，这里简单的处理方式
          loadResourcePreview(resource.id);
        }
      }
    }
  }
};

/**
 * 加载资源详情
 */
async function loadResourcePreview(resourceId: string) {
  isPreviewLoading.value = true;
  try {
    await resourceStore.fetchResourceDetails(resourceId);

    // 更新后，从 Store 获取最新完整对象
    const updatedResource = resources.value.find(r => r.id === resourceId);
    if (updatedResource) {
      // 在已选列表中找到并替换，触发响应式更新
      const index = selectedResources.value.findIndex(r => r.id === resourceId);
      if (index !== -1) {
        selectedResources.value.splice(index, 1, updatedResource);
      } else if (selectedResources.value.length === 0 && !isMultiSelectMode.value) {
        // 应对极端边界情况
        selectedResources.value = [updatedResource];
      }
    }
  } catch(e) {
    console.error("Failed to load resource content", e);
  } finally {
    // 改良 Loading 逻辑：检查是否还有选中项没有内容，如果有，保持 Loading
    // 这是一个简单的防抖，防止最后一个请求结束关闭 Loading，但其他请求还在跑
    // 这里做简化处理：每次请求结束都尝试关闭，除非我们追踪正在进行的请求数。
    // 在多选并行请求下，UI Loading 可能会闪烁，但功能是正常的。
    // 为了更好的体验，可以加一个计数器，但这里简化为直接 false
    isPreviewLoading.value = false;
  }
}

function handleConfirmSelection() {
  if (selectedResources.value.length === 0) return;
  emit('select-resource', selectedResources.value);
  emit('update:visible', false);
}

function handleDialogClose() {
  searchText.value = '';
  selectedResources.value = [];
  selectionType.value = null;
  isPreviewLoading.value = false;
  expandedKeys.value.clear();
}
</script>

<style scoped>
/* Reset & Layout */
.resource-selector-body { display: flex; flex-direction: column; height: 60vh; }
.toolbar { display: flex; align-items: center; gap: 20px; margin-bottom: 16px; flex-shrink: 0; }
.search-input { flex-grow: 1; }
.multi-select-switch { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--el-text-color-regular); }
.resource-selector-container { flex-grow: 1; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; overflow: hidden; }
.resource-tree-aside { border-right: 1px solid var(--el-border-color-lighter); }

/* Tree Nodes */
.custom-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 2px 0;
  padding-right: 8px;
}
.custom-tree-node.is-selected { background-color: var(--el-color-primary-light-9); }
.custom-tree-node.is-disabled { color: var(--el-text-color-disabled); cursor: not-allowed; }
.custom-tree-node.is-disabled .el-icon, .custom-tree-node.is-disabled .resource-type-tag { opacity: 0.6; }
.node-content { display: flex; align-items: center; gap: 8px; overflow: hidden; }
.node-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.loading-icon { animation: rotating 2s linear infinite; color: var(--el-text-color-secondary); margin-left: 4px; }
.resource-type-tag { flex-shrink: 0; margin-left: 8px; }

/* Preview Pane */
.resource-preview-main { padding: 0; }
.preview-card { height: 100%; border: none; display: flex; flex-direction: column; }
:deep(.preview-card .el-card__header) { flex-shrink: 0; }
:deep(.preview-card .el-card__body) { flex-grow: 1; padding: 0; overflow: hidden; }
.preview-scrollbar { padding: 20px; }
.preview-content { white-space: pre-wrap; word-wrap: break-word; font-family: var(--el-font-family); font-size: 14px; margin: 0; }

/* Multi-select Preview Styles */
.multi-preview-item { margin-bottom: 10px; }
.multi-preview-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; font-weight: bold; }
.loading-state { padding: 20px; }

@keyframes rotating {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
