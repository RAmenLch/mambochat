<!-- frontend/mambo/src/components/common/dialogs/ResourceSelectorSidebar.vue -->
<template>
  <div class="sidebar-wrapper">
    <div class="toolbar">
      <div class="toolbar-header">
          <el-radio-group :model-value="selectorMode" @update:model-value="val => emit('update:selectorMode', val as 'resource' | 'kb')" size="small">
            <el-radio-button label="resource">{{ $t('resource.selector.modeResource') }}</el-radio-button>
            <el-radio-button label="kb">{{ $t('resource.selector.modeKb') }}</el-radio-button>
          </el-radio-group>
        <div class="multi-select-switch">
          <span class="switch-label">{{ $t('resource.selector.multiSelect') }}</span>
          <el-switch v-model="isMultiSelectMode" size="small" />
        </div>
      </div>

      <div class="search-wrapper">
        <el-input
          v-model="searchText"
          :placeholder="$t('resource.selector.searchPlaceholder')"
          clearable
          class="search-input"
          @input="handleSearchInput"
        >
          <template #append>
            <el-tooltip :content="$t('resource.selector.regexTooltip')" placement="top">
              <el-button :class="{ 'is-active-regex': enableRegex }" @click="toggleRegex">.*</el-button>
            </el-tooltip>
          </template>
        </el-input>
      </div>
    </div>

    <el-aside width="100%" class="resource-tree-aside">
      <div v-if="searchText" class="search-result-container">
        <div v-if="isSearching" class="loading-state">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ $t('common.status.searching') }}</span>
        </div>
        <div v-else-if="searchResult.length === 0" class="empty-state">
          <span class="empty-text">{{ $t('chat.search.noResult') }}</span>
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
                <el-tag size="small" effect="plain" :type="getMatchTypeTag(item.match_type)" class="match-tag">
                  {{ getMatchTypeLabel(item.match_type) }}
                </el-tag>
              </div>
              <div class="search-item-path" :title="item.resource_path">{{ item.resource_path }}</div>
              <div v-if="item.context_text" class="search-item-context" v-html="highlightKeyword(item.context_text)"></div>
            </div>
            <div v-if="hasMore" class="load-more-wrapper">
              <el-button link size="small" :loading="isSearching" @click="loadMore">{{ $t('common.action.loadMore') }}</el-button>
            </div>
          </div>
        </el-scrollbar>
      </div>

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
          :expand-on-click-node="false"
          @node-click="handleNodeClick"
          @node-expand="handleNodeExpand"
          @node-collapse="handleNodeCollapse"
        >
          <template #default="{ data }">
            <span class="custom-tree-node" :class="{ 'is-selected': isResourceSelected(data.id), 'is-disabled': isNodeDisabled(data) }">
              <span class="node-content">
                <el-icon>
                  <Reading v-if="data.resourceType === 'skill'" />
                  <Collection v-else-if="data.resourceType === 'knowledge_base'" />
                  <Folder v-else-if="data.itemType === 'folder'" />
                  <Memo v-else-if="data.resourceType === 'submessage_template'" />
                  <Document v-else />
                </el-icon>
                <span class="node-label">{{ data.name }}</span>
                <el-icon v-if="loadingFolders.has(data.id)" class="is-loading loading-icon"><Loading /></el-icon>
              </span>
              <el-tag v-if="data.itemType === 'resource' && data.resourceType" size="small" type="info" class="resource-type-tag">
                {{ getReadableResourceType(data.resourceType) }}
              </el-tag>
              <el-tag v-else-if="data.itemType === 'folder' && data.resourceType === 'knowledge_base'" size="small" type="primary" class="resource-type-tag">
                {{ $t('resource.types.knowledge_base') }}
              </el-tag>
              <el-tag v-else-if="data.itemType === 'folder' && data.resourceType === 'skill'" size="small" type="danger" class="resource-type-tag">
                {{ $t('resource.types.skill') }}
              </el-tag>
            </span>
          </template>
        </el-tree>
      </el-scrollbar>
    </el-aside>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { ElTree, ElMessage } from 'element-plus';
import type { TreeNodeData } from 'element-plus/es/components/tree/src/tree.type';
import { Folder, Document, Memo, Loading, Collection, Reading } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { useResourceStore } from '@/stores/resourceStore';
import { searchResources } from '@/api/resourceService';
import type { Resource, ResourceNode, ResourceType, ResourceSearchResultItem } from '@/api/types';

const props = defineProps<{
  selectedResources: Resource[];
  isPreviewLoading: boolean;
  selectorMode: 'resource' | 'kb';
  contextConfig: { allowedTypes: string[], canMount: string[], canAppend: string[], canMountKb: string[] };
}>();

const emit = defineEmits<{
  (e: 'update:selectedResources', val: Resource[]): void;
  (e: 'update:isPreviewLoading', val: boolean): void;
  (e: 'update:selectorMode', val: 'resource' | 'kb'): void;
}>();

const resourceStore = useResourceStore();
const { resourceTree, isResourcesLoading, loadingFolders, resources } = storeToRefs(resourceStore);
const { t } = useI18n();

const searchText = ref('');
const treeRef = ref<InstanceType<typeof ElTree>>();
const isMultiSelectMode = ref(false);
const selectionType = ref<ResourceType | null>(null);
const STORAGE_KEY = 'resource_selector_multi_select_mode';
const expandedKeys = ref<Set<string>>(new Set());

const isSearching = ref(false);
const enableRegex = ref(false);
const searchResult = ref<ResourceSearchResultItem[]>([]);
const searchPage = ref(1);
const searchTotal = ref(0);
const searchDebounceTimer = ref<number | undefined>(undefined);

onMounted(() => {
  const persistedMode = localStorage.getItem(STORAGE_KEY);
  isMultiSelectMode.value = persistedMode === 'true';
  resourceStore.initializeList();
});

const filteredTreeData = computed(() => filterTreeByType(resourceTree.value));
const hasMore = computed(() => searchResult.value.length < searchTotal.value);

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: (data: TreeNodeData) => (data as ResourceNode).itemType !== 'folder',
  class: (data: TreeNodeData) => (data as ResourceNode).itemType === 'stub' ? 'is-hidden-node' : ''
};

function filterTreeByType(nodes: ResourceNode[]): ResourceNode[] {
  const allowed = props.contextConfig.allowedTypes;
  if (!allowed || allowed.length === 0) return nodes;

  const result: ResourceNode[] = [];
  for (const node of nodes) {
    if (node.itemType === 'folder') {
      const children = filterTreeByType(node.children || []);
      if (node.resourceType === 'knowledge_base' || node.resourceType === 'skill') {
        if (allowed.includes(node.resourceType)) result.push({ ...node, children });
      } else {
        result.push({ ...node, children });
      }
    } else if (node.resourceType && allowed.includes(node.resourceType)) {
      result.push(node);
    }
  }
  return result;
}

watch(isMultiSelectMode, (newMode) => {
  localStorage.setItem(STORAGE_KEY, String(newMode));
  emit('update:selectedResources', []);
  selectionType.value = null;
});

watch(filteredTreeData, () => {
  nextTick(() => {
    if (!treeRef.value) return;
    expandedKeys.value.forEach((key) => {
      const node = treeRef.value!.getNode(key);
      if (node && !node.expanded) node.expand();
    });
  });
});

const getReadableResourceType = (type: string | null) => {
  if (!type) return t('resource.types.unknown');
  const map: Record<string, string> = {
    'system_prompt': 'system_prompt',
    'submessage_template': 'submessage_template',
    'knowledge_base': 'knowledge_base',
    'file': 'file',
    'skill': 'skill'
  };
  return map[type] ? t(`resource.types.${map[type]}`) : type;
};

const isResourceSelected = (resourceId: string): boolean => {
  return props.selectedResources.some(r => r.id === resourceId);
};

const isNodeDisabled = (data: ResourceNode): boolean => {
  if (!isMultiSelectMode.value || !selectionType.value) return false;
  if (data.itemType === 'folder' && data.resourceType !== 'knowledge_base' && data.resourceType !== 'skill') return false;
  return data.resourceType !== selectionType.value;
};

const getMatchTypeTag = (type: string) => {
  const map: Record<string, any> = { name: 'primary', description: 'info', content: 'success' };
  return map[type] || 'info';
};

const getMatchTypeLabel = (type: string) => {
  const map: Record<string, string> = { name: t('resource.meta.name'), description: t('resource.meta.description'), content: t('resource.editor.contentLabel') };
  return map[type] || type;
};

const highlightKeyword = (text: string): string => {
  if (!searchText.value) return text;
  const keyword = enableRegex.value ? searchText.value : searchText.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  try {
    const regex = new RegExp(`(${keyword})`, 'gi');
    return text.replace(regex, '<span class="highlight-text">$1</span>');
  } catch (e) {
    return text;
  }
};

const toggleRegex = () => {
  enableRegex.value = !enableRegex.value;
  if (searchText.value) triggerSearch();
};

const handleSearchInput = () => {
  clearTimeout(searchDebounceTimer.value);
  searchDebounceTimer.value = window.setTimeout(() => triggerSearch(), 300);
};

const triggerSearch = async (resetPage = true) => {
  if (!searchText.value.trim()) {
    searchResult.value = [];
    searchTotal.value = 0;
    return;
  }
  if (resetPage) { searchPage.value = 1; searchResult.value = []; }
  isSearching.value = true;
  try {
    const res = await searchResources({ keyword: searchText.value.trim(), enable_regex: enableRegex.value, page_num: searchPage.value, page_size: 20 });
    searchResult.value = resetPage ? res.items : [...searchResult.value, ...res.items];
    searchTotal.value = res.total;
  } catch (e) {
    ElMessage.error(t('resource.msg.searchFailed'));
  } finally {
    isSearching.value = false;
  }
};

const loadMore = () => { searchPage.value++; triggerSearch(false); };

const selectResourceById = async (resourceId: string, resourceType?: ResourceType | null, initialResourceObj?: Resource) => {
  let targetResource = resources.value.find(r => r.id === resourceId) || initialResourceObj;
  const typeToCheck = targetResource?.resourceType || resourceType;

  if (typeToCheck && !props.contextConfig.allowedTypes.includes(typeToCheck as string)) {
    ElMessage.warning(t('resource.msg.typeMismatch', { type: getReadableResourceType(typeToCheck as string) }));
    return;
  }

  if (isMultiSelectMode.value && selectionType.value && typeToCheck && typeToCheck !== selectionType.value) return;

  let newSelection = [...props.selectedResources];

  if (!isMultiSelectMode.value) {
    if (targetResource) newSelection = [targetResource];
    emit('update:selectedResources', newSelection);
    await loadResourcePreview(resourceId, newSelection);
  } else {
    const index = newSelection.findIndex(r => r.id === resourceId);
    if (index > -1) {
      newSelection.splice(index, 1);
      if (newSelection.length === 0) selectionType.value = null;
    } else {
      if (newSelection.length === 0) selectionType.value = typeToCheck || null;
      if (targetResource) newSelection.push(targetResource);
      else {
        newSelection.push({ id: resourceId, name: t('common.status.loading'), description: null, itemType: 'resource', resourceType: typeToCheck || null, parentId: null, sortOrder: 0, createdAt: '', updatedAt: '', latest_version: null, kb_id: null, kb_config: null });
      }
      emit('update:selectedResources', newSelection);
      loadResourcePreview(resourceId, newSelection);
    }
    emit('update:selectedResources', newSelection);
  }
};

const handleSearchResultClick = (item: ResourceSearchResultItem) => {
  selectResourceById(item.resource_id, null, { id: item.resource_id, name: item.resource_name, description: null, itemType: 'resource', resourceType: null, parentId: null, sortOrder: 0, createdAt: item.updated_at, updatedAt: item.updated_at, latest_version: null, kb_id: null, kb_config: null });
};

const handleNodeExpand = (data: ResourceNode) => {
  expandedKeys.value.add(data.id);
  if (data.itemType === 'folder') resourceStore.fetchResourceChildren(data.id);
};

const handleNodeCollapse = (data: ResourceNode) => { expandedKeys.value.delete(data.id); };

const handleNodeClick = async (data: TreeNodeData) => {
  const resource = data as ResourceNode;
  const isSelectable = resource.itemType === 'resource' || (resource.itemType === 'folder' && (resource.resourceType === 'knowledge_base' || resource.resourceType === 'skill'));
  if (!isSelectable || isNodeDisabled(resource)) return;
  selectResourceById(resource.id, resource.resourceType, resource);
};

async function loadResourcePreview(resourceId: string, currentSelection: Resource[]) {
  emit('update:isPreviewLoading', true);
  try {
    await resourceStore.fetchResourceDetails(resourceId);
    const updatedResource = resources.value.find(r => r.id === resourceId);
    if (updatedResource) {
      const index = currentSelection.findIndex(r => r.id === resourceId);
      if (index !== -1) {
        currentSelection.splice(index, 1, updatedResource);
        if (isMultiSelectMode.value && currentSelection.length === 1) selectionType.value = updatedResource.resourceType;
      } else if (currentSelection.length === 0 && !isMultiSelectMode.value) {
        currentSelection = [updatedResource];
      }
      emit('update:selectedResources', currentSelection);
    }
  } catch(e) {
    console.error("Failed to load resource content", e);
  } finally {
    emit('update:isPreviewLoading', false);
  }
}

const handleScroll = ({ scrollTop, scrollHeight, clientHeight }: any) => {
  if (scrollTop + clientHeight > scrollHeight - 50 && hasMore.value && !isSearching.value) loadMore();
};
</script>

<style scoped>
.sidebar-wrapper {
  display: flex;
  flex-direction: column;
  width: 300px;
  border-right: 1px solid var(--el-border-color-lighter);
  background-color: var(--el-bg-color-page);
}

.toolbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.toolbar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.multi-select-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.is-active-regex {
  color: var(--el-color-primary);
  font-weight: bold;
}

.resource-tree-aside {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 8px 0;
}

.custom-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 4px 8px 4px 0;
  border-radius: 6px;
  transition: all 0.2s;
}

.custom-tree-node:hover {
  background-color: var(--el-fill-color-light);
}

.custom-tree-node.is-selected {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

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
  font-size: 14px;
  overflow: hidden;
}

.node-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.loading-icon {
  animation: rotating 2s linear infinite;
  color: var(--el-text-color-secondary);
  margin-left: 4px;
}

.resource-type-tag {
  flex-shrink: 0;
  margin-left: 8px;
  transform: scale(0.9);
}

.search-result-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.search-list {
  padding: 10px;
}

.search-item {
  margin: 0 12px 8px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  background-color: var(--el-bg-color);
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  transition: all 0.2s;
  cursor: pointer;
}

.search-item:hover {
  border-color: var(--el-border-color-lighter);
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.search-item.is-selected {
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}

.search-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.search-item-title {
  font-weight: 500;
  font-size: 14px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
}

.search-item-path {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-item-context {
  font-size: 12px;
  color: var(--el-text-color-regular);
  background-color: var(--el-fill-color-lighter);
  padding: 4px;
  border-radius: 4px;
  line-height: 1.4;
  word-break: break-all;
}

:deep(.highlight-text) {
  color: var(--el-color-primary);
  font-weight: bold;
  background-color: var(--el-color-primary-light-9);
}

.empty-state, .loading-state {
  padding: 40px 0;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.load-more-wrapper {
  text-align: center;
  padding: 10px 0;
}

@keyframes rotating {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
