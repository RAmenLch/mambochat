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
        <div class="search-wrapper">
          <el-input
            v-model="searchText"
            placeholder="搜索资源名称、描述或内容..."
            clearable
            class="search-input"
            @input="handleSearchInput"
          />
          <el-tooltip content="启用正则表达式搜索" placement="top">
            <el-button
              :type="enableRegex ? 'primary' : 'default'"
              size="small"
              class="regex-btn"
              @click="toggleRegex"
            >
              .*
            </el-button>
          </el-tooltip>
        </div>

        <div class="multi-select-switch">
          <span>多选模式</span>
          <el-switch v-model="isMultiSelectMode" />
        </div>
      </div>
      <el-container class="resource-selector-container">
        <!-- 侧边栏：树形视图 OR 搜索结果列表 -->
        <el-aside width="280px" class="resource-tree-aside">
          <!-- 搜索结果列表视图 -->
          <div v-if="searchText" class="search-result-container">
            <div v-if="isSearching" class="loading-state">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在搜索...</span>
            </div>
            <div v-else-if="searchResult.length === 0" class="empty-state">
              <span class="empty-text">未找到匹配资源</span>
            </div>
            <el-scrollbar v-else @scroll="handleScroll">
              <div class="search-list">
                <div
                  v-for="item in searchResult"
                  :key="item.resource_id"
                  class="search-item"
                  :class="{ 'is-selected': isResourceSelected(item.resource_id) }"
                  @click="handleSearchResultClick(item)"
                >
                  <div class="search-item-header">
                    <span class="search-item-title">{{ item.resource_name }}</span>
                    <el-tag
                      size="small"
                      effect="plain"
                      :type="getMatchTypeTag(item.match_type)"
                      class="match-tag"
                    >
                      {{ getMatchTypeLabel(item.match_type) }}
                    </el-tag>
                  </div>
                  <div class="search-item-path" :title="item.resource_path">
                    {{ item.resource_path }}
                  </div>
                  <div
                    v-if="item.context_text"
                    class="search-item-context"
                    v-html="highlightKeyword(item.context_text)"
                  ></div>
                </div>
                <div v-if="hasMore" class="load-more-wrapper">
                  <el-button link size="small" :loading="isSearching" @click="loadMore">
                    加载更多
                  </el-button>
                </div>
              </div>
            </el-scrollbar>
          </div>

          <!-- 默认树形视图 -->
          <el-scrollbar v-else>
            <div v-if="isResourcesLoading && resourceTree.length === 0" class="loading-state">
              <el-skeleton :rows="5" animated />
            </div>
            <el-tree
              v-else
              ref="treeRef"
              :data="filteredTreeData"
              node-key="id"
              :props="treeProps"
              @node-click="handleNodeClick"
              @node-expand="handleNodeExpand"
              @node-collapse="handleNodeCollapse"
            >
              <template #default="{ data }">
                <span
                  class="custom-tree-node"
                  :class="{
                    'is-selected': isResourceSelected(data.id),
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

        <!-- 预览区域 -->
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
              <div v-for="(res, index) in selectedResources" :key="res.id" class="multi-preview-item">
                <div class="multi-preview-label">#{{ index + 1 }} {{ res.name }}</div>
                <pre class="preview-content">{{ res.latest_version?.content || '该资源没有内容' }}</pre>
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
import { ElTree, ElMessage } from 'element-plus';
import type { TreeNodeData } from 'element-plus/es/components/tree/src/tree.type';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import type Node from 'element-plus/es/components/tree/src/model/node';
import { Folder, Document, Memo, Loading } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import { useResourceStore } from '@/stores/resourceStore';
import { searchResources } from '@/api/resourceService';
import type { Resource, ResourceNode, ResourceType, ResourceSearchResultItem } from '@/api/types';

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
const isPreviewLoading = ref(false);
const STORAGE_KEY = 'resource_selector_multi_select_mode';

const expandedKeys = ref<Set<string>>(new Set());

// --- Search State ---
const isSearching = ref(false);
const enableRegex = ref(false);
const searchResult = ref<ResourceSearchResultItem[]>([]);
const searchPage = ref(1);
const searchTotal = ref(0);
const searchDebounceTimer = ref<number | undefined>(undefined);

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
  isLeaf: (data: TreeNodeData) => (data as ResourceNode).itemType !== 'folder',
  class: (data: TreeNodeData) => (data as ResourceNode).itemType === 'stub' ? 'is-hidden-node' : ''
};

const hasMore = computed(() => searchResult.value.length < searchTotal.value);

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

const isResourceSelected = (resourceId: string): boolean => {
  return selectedResources.value.some(r => r.id === resourceId);
};

const isNodeDisabled = (data: ResourceNode): boolean => {
  if (!isMultiSelectMode.value || !selectionType.value) return false;
  if (data.itemType === 'folder') return false;
  return data.resourceType !== selectionType.value;
};

// 定义符合 Element Plus Tag 组件 props 类型
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger';

const getMatchTypeTag = (type: string): TagType => {
  const map: Record<string, TagType> = {
    name: 'primary',
    description: 'info',
    content: 'success'
  };
  return map[type] || 'info';
};

const getMatchTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    name: '标题',
    description: '描述',
    content: '内容'
  };
  return map[type] || type;
};

const highlightKeyword = (text: string): string => {
  if (!searchText.value) return text;
  const keyword = enableRegex.value
    ? searchText.value
    : searchText.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  try {
    const regex = new RegExp(`(${keyword})`, 'gi');
    return text.replace(regex, '<span class="highlight-text">$1</span>');
  } catch (e) {
    return text;
  }
};

// --- Search Methods ---

const toggleRegex = () => {
  enableRegex.value = !enableRegex.value;
  if (searchText.value) {
    triggerSearch();
  }
};

const handleSearchInput = () => {
  clearTimeout(searchDebounceTimer.value);
  searchDebounceTimer.value = window.setTimeout(() => {
    triggerSearch();
  }, 300);
};

const triggerSearch = async (resetPage = true) => {
  if (!searchText.value.trim()) {
    searchResult.value = [];
    searchTotal.value = 0;
    return;
  }

  if (resetPage) {
    searchPage.value = 1;
    searchResult.value = [];
  }

  isSearching.value = true;
  try {
    const res = await searchResources({
      keyword: searchText.value.trim(),
      enable_regex: enableRegex.value,
      page_num: searchPage.value,
      page_size: 20
    });

    if (resetPage) {
      searchResult.value = res.items;
    } else {
      searchResult.value = [...searchResult.value, ...res.items];
    }
    searchTotal.value = res.total;
  } catch (e) {
    console.error('Search failed:', e);
    ElMessage.error('搜索失败，请稍后重试');
  } finally {
    isSearching.value = false;
  }
};

const loadMore = () => {
  searchPage.value++;
  triggerSearch(false);
};

// --- Selection Logic (Shared) ---

/**
 * 统一处理资源选择逻辑，无论是来自 Tree 还是 Search List
 */
const selectResourceById = async (resourceId: string, resourceType?: ResourceType | null, initialResourceObj?: Resource) => {
  // 1. 获取资源完整对象
  // 显式声明类型为 Resource | undefined，兼容 ResourceWithVersions (从 store) 和 Resource (从 initialResourceObj)
  let targetResource: Resource | undefined = resources.value.find(r => r.id === resourceId);

  // 如果缓存没有（例如搜索结果中的深层资源），且提供了初始对象，则使用初始对象
  if (!targetResource && initialResourceObj) {
    targetResource = initialResourceObj;
  }

  // 如果不知道类型，且目前没有加载该资源，我们可能需要先 fetchDetails 才能判断类型校验
  if (targetResource && props.resourceTypeFilter && targetResource.resourceType !== props.resourceTypeFilter) {
    ElMessage.warning(`只能选择类型为 ${getReadableResourceType(props.resourceTypeFilter)} 的资源`);
    return;
  }

  // 2. 检查多选类型限制
  const typeToCheck = targetResource?.resourceType || resourceType;
  if (isMultiSelectMode.value && selectionType.value && typeToCheck && typeToCheck !== selectionType.value) {
     // 类型不匹配，跳过
     return;
  }

  // 3. 执行选中/取消选中
  if (!isMultiSelectMode.value) {
    // 单选：直接替换
    // 先放一个占位对象，如果 targetResource 存在
    if (targetResource) {
      selectedResources.value = [targetResource];
    }

    // 加载详情
    await loadResourcePreview(resourceId);
  } else {
    // 多选
    const index = selectedResources.value.findIndex(r => r.id === resourceId);
    if (index > -1) {
      // 取消选中
      selectedResources.value.splice(index, 1);
      if (selectedResources.value.length === 0) {
        selectionType.value = null;
      }
    } else {
      // 选中
      // 如果是第一个，确定类型
      if (selectedResources.value.length === 0) {
        selectionType.value = typeToCheck || null;
      }

      // 添加到列表
      if (targetResource) {
        selectedResources.value.push(targetResource);
      } else {
        // 如果缓存里没有，根据 ID 造一个临时的，等待 fetchDetails 完善它
        selectedResources.value.push({
          id: resourceId,
          name: '正在加载...',
          description: null, // [修复] 补全 description 字段
          itemType: 'resource',
          resourceType: typeToCheck || null,
          parentId: null,
          sortOrder: 0,
          createdAt: '',
          updatedAt: '',
          latest_version: null
        });
      }

      // 异步加载内容
      loadResourcePreview(resourceId);
    }
  }
};

const handleSearchResultClick = (item: ResourceSearchResultItem) => {
  // 搜索结果点击，构造临时 Resource 对象，必须包含 Resource 接口的所有必填字段
  selectResourceById(item.resource_id, null, {
    id: item.resource_id,
    name: item.resource_name,
    description: null, // [修复] 补全 description 字段
    itemType: 'resource',
    resourceType: null, // 未知，待加载
    parentId: null,
    sortOrder: 0,
    createdAt: item.updated_at,
    updatedAt: item.updated_at,
    latest_version: null
  });
};

// --- Tree Interaction Methods ---
const filterNode = (value: string, data: TreeNodeData): boolean => {
  // Deprecated due to lazy loading, but kept for interface compatibility if needed
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
  selectResourceById(resource.id, resource.resourceType, resource);
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

        // 如果是多选的第一个，更新类型约束
        if (isMultiSelectMode.value && selectedResources.value.length === 1) {
          selectionType.value = updatedResource.resourceType;
        }
      } else if (selectedResources.value.length === 0 && !isMultiSelectMode.value) {
        // 单选模式下，如果刚才被清空了或者还在初始化
        selectedResources.value = [updatedResource];
      }
    }
  } catch(e) {
    console.error("Failed to load resource content", e);
  } finally {
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
  searchResult.value = [];
  searchPage.value = 1;
  searchTotal.value = 0;
}

// 简单的滚动处理
const handleScroll = ({ scrollTop, scrollHeight, clientHeight }: any) => {
  // 简易无限滚动：接近底部且不处于加载状态
  if (scrollTop + clientHeight > scrollHeight - 50 && hasMore.value && !isSearching.value) {
    loadMore();
  }
};
</script>

<style scoped>
/* Reset & Layout */
.resource-selector-body { display: flex; flex-direction: column; height: 60vh; }
.toolbar { display: flex; align-items: center; gap: 20px; margin-bottom: 16px; flex-shrink: 0; }
.search-wrapper { display: flex; align-items: center; gap: 8px; flex-grow: 1; }
.search-input { flex-grow: 1; }
.regex-btn { font-family: monospace; font-weight: bold; padding: 8px; }

.multi-select-switch { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--el-text-color-regular); }
.resource-selector-container { flex-grow: 1; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; overflow: hidden; }
.resource-tree-aside { border-right: 1px solid var(--el-border-color-lighter); background-color: #fff; display: flex; flex-direction: column; }

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

/* Search Results Styles */
.search-result-container { height: 100%; display: flex; flex-direction: column; }
.search-list { padding: 10px; }
.search-item {
  padding: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  transition: background-color 0.2s;
}
.search-item:hover { background-color: var(--el-fill-color-light); }
.search-item.is-selected { background-color: var(--el-color-primary-light-9); }

.search-item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.search-item-title { font-weight: 500; font-size: 14px; color: var(--el-text-color-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; margin-right: 8px; }
.match-tag { flex-shrink: 0; }
.search-item-path { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-item-context { font-size: 12px; color: var(--el-text-color-regular); background-color: var(--el-fill-color-lighter); padding: 4px; border-radius: 4px; line-height: 1.4; word-break: break-all; }
:deep(.highlight-text) { color: var(--el-color-primary); font-weight: bold; background-color: var(--el-color-primary-light-9); }

.empty-state { padding: 40px 0; text-align: center; color: var(--el-text-color-secondary); }
.loading-state { padding: 20px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--el-text-color-secondary); }
.load-more-wrapper { text-align: center; padding: 10px 0; }

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

@keyframes rotating {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
<style>
.is-hidden-node {
  display: none !important;
}
</style>
