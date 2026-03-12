<!-- frontend/mambo/src/components/chat/dialogs/ResourceSelectorDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="$t('resource.selector.title')"
    width="70%"
    @update:model-value="val => emit('update:visible', val)"
    @close="handleDialogClose"
  >
    <div class="resource-selector-body">
      <div class="toolbar">
        <!-- 模式切换 -->
        <el-radio-group v-model="selectorMode" size="small" class="mode-switch">
          <el-radio-button label="resource">{{ $t('resource.selector.modeResource') }}</el-radio-button>
          <el-radio-button label="kb">{{ $t('resource.selector.modeKb') }}</el-radio-button>
        </el-radio-group>

        <el-divider direction="vertical" class="toolbar-divider" />

        <!-- 资源浏览模式下的工具栏 -->
        <template v-if="selectorMode === 'resource'">
          <div class="search-wrapper">
            <el-input
              v-model="searchText"
              :placeholder="$t('resource.selector.searchPlaceholder')"
              clearable
              class="search-input"
              @input="handleSearchInput"
            />
            <el-tooltip :content="$t('resource.selector.regexTooltip')" placement="top">
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
            <span>{{ $t('resource.selector.multiSelect') }}</span>
            <el-switch v-model="isMultiSelectMode" />
          </div>
        </template>

        <!-- 知识库模式下的占位符 -->
        <div v-else class="kb-toolbar-placeholder">
          <span class="info-text">{{ $t('resource.selector.kbModeTip') }}</span>
        </div>
      </div>

      <!-- 模式 A: 资源树与预览 -->
      <el-container v-if="selectorMode === 'resource'" class="resource-selector-container">
        <!-- 侧边栏：树形视图 OR 搜索结果列表 -->
        <el-aside width="280px" class="resource-tree-aside">
          <!-- 搜索结果列表视图 -->
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
                    {{ $t('common.action.loadMore') }}
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
              :expand-on-click-node="false"
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
                  <!-- 特殊处理：知识库也是文件夹，但也显示类型标签 -->
                  <el-tag
                    v-else-if="data.itemType === 'folder' && data.resourceType === 'knowledge_base'"
                    size="small"
                    type="primary"
                    class="resource-type-tag"
                  >
                    {{ $t('resource.types.knowledge_base') }}
                  </el-tag>
                </span>
              </template>
            </el-tree>
          </el-scrollbar>
        </el-aside>

        <!-- 预览区域 -->
        <el-main class="resource-preview-main">
          <el-empty v-if="selectedResources.length === 0" :description="$t('resource.editor.placeholder')" />

          <!-- 单选预览 -->
          <el-card v-else-if="selectedResources.length === 1" shadow="never" class="preview-card">
            <template #header>
              <div class="preview-header">
                <strong>{{ $t('resource.selector.previewHeader', { name: selectedResources[0].name }) }}</strong>
              </div>
            </template>
            <el-scrollbar class="preview-scrollbar" v-loading="isPreviewLoading">
              <!-- Knowledge Base Preview -->
              <template v-if="selectedResources[0].resourceType === 'knowledge_base'">
                <div class="kb-preview-wrapper">
                  <el-icon :size="64" color="#409EFF"><Collection /></el-icon>
                  <h3>{{ selectedResources[0].name }}</h3>
                  <p class="kb-desc">{{ selectedResources[0].description || $t('resource.selector.noDesc') }}</p>
                  <el-alert
                    :title="$t('resource.selector.kbMountTip')"
                    type="info"
                    :closable="false"
                    show-icon
                    style="margin-top: 20px; max-width: 80%;"
                  >
                    {{ $t('resource.selector.kbMountContent') }}
                  </el-alert>
                </div>
              </template>

              <!-- File Resource Preview -->
              <template v-else-if="selectedResources[0].resourceType === 'file'">
                <div v-if="currentFileInfo" class="file-preview-wrapper">
                  <!-- Image Preview -->
                  <div v-if="isImage" class="file-preview-image">
                    <el-image
                      :src="currentFileInfo.url"
                      :preview-src-list="[currentFileInfo.url]"
                      fit="contain"
                      class="preview-img"
                    >
                      <template #error>
                        <div class="image-slot">
                          <el-icon><Picture /></el-icon>
                          <span>{{ $t('resource.attachment.imageLoadFailed') }}</span>
                        </div>
                      </template>
                    </el-image>
                  </div>
                  <!-- Generic File Icon -->
                  <div v-else class="file-generic">
                    <el-icon :size="48"><Document /></el-icon>
                    <div class="file-meta">
                      <div class="file-name">{{ currentFileInfo.filename }}</div>
                      <div class="file-size">{{ formatFileSize(currentFileInfo.size) }}</div>
                    </div>
                    <a :href="currentFileInfo.url" target="_blank" class="download-link">
                      <el-button type="primary" link icon="Download">{{ $t('resource.editor.downloadFile') }}</el-button>
                    </a>
                  </div>
                </div>
                <div v-else class="file-empty-state">
                  <el-icon :size="48"><Document /></el-icon>
                  <p>{{ $t('resource.selector.noFileContent') }}</p>
                </div>
              </template>

              <!-- Text Resource Preview -->
              <pre v-else class="preview-content">{{ selectedResources[0].latest_version?.content || $t('resource.selector.noContent') }}</pre>
            </el-scrollbar>
          </el-card>

          <!-- 多选预览 (合并内容) -->
          <el-card v-else shadow="never" class="preview-card">
             <template #header>
              <div class="preview-header">
                <strong>{{ $t('resource.selector.multiPreview', { count: selectedResources.length }) }}</strong>
              </div>
            </template>
            <el-scrollbar class="preview-scrollbar" v-loading="isPreviewLoading">
              <div v-for="(res, index) in selectedResources" :key="res.id" class="multi-preview-item">
                <div class="multi-preview-label">#{{ index + 1 }} {{ res.name }}</div>

                <template v-if="res.resourceType === 'knowledge_base'">
                   <div class="mini-empty">{{ $t('resource.selector.kbContainer') }}</div>
                </template>

                <!-- Multi-select File Preview -->
                <template v-else-if="res.resourceType === 'file'">
                  <div v-if="res.latest_version?.file_info" class="file-preview-wrapper mini">
                    <div v-if="isResourceImage(res)" class="file-preview-image mini">
                      <el-image
                        :src="res.latest_version.file_info.url"
                        :preview-src-list="[res.latest_version.file_info.url]"
                        fit="contain"
                        style="width: 100%; height: 100%;"
                      />
                    </div>
                    <div v-else class="file-generic mini">
                      <el-icon><Document /></el-icon>
                      <span>{{ res.latest_version.file_info.filename }}</span>
                    </div>
                  </div>
                  <div v-else class="mini-empty">{{ $t('resource.selector.noFile') }}</div>
                </template>

                <!-- Multi-select Text Preview -->
                <pre v-else class="preview-content">{{ res.latest_version?.content || $t('resource.selector.noContent') }}</pre>

                <el-divider v-if="index < selectedResources.length - 1" border-style="dashed" />
              </div>
            </el-scrollbar>
          </el-card>
        </el-main>
      </el-container>

      <!-- 模式 B: 知识库向量检索 -->
      <KnowledgeBaseSearchDialog
        v-else
        @cancel="emit('update:visible', false)"
        @confirm="handleKBSelection"
      />
    </div>

    <!-- Footer: 仅在资源模式下显示 (KB模式有内部Footer) -->
    <template #footer v-if="selectorMode === 'resource'">
      <div class="action-buttons">
        <!-- 提供给AI助手检索按钮 -->
        <el-button
          v-if="showKbSearchButton"
          type="primary"
          :icon="Search"
          plain
          @click="handleMountKnowledgeBase"
        >
          {{ $t('resource.action.mountKbSearch') }}
        </el-button>

        <el-button
          v-if="showAppendButton"
          type="default"
          @click="handleAppend"
          :disabled="selectedResources.length === 0"
        >
          {{ $t('resource.action.append', { count: selectedResources.length }) }}
        </el-button>

        <!-- 挂载按钮：在Settings场景下选中知识库时隐藏 -->
        <el-button
          v-if="showMountButton"
          type="primary"
          @click="handleMount"
          :disabled="selectedResources.length === 0"
        >
          {{ $t('resource.action.mount', { count: selectedResources.length }) }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { ElTree, ElMessage } from 'element-plus';
import type { TreeNodeData } from 'element-plus/es/components/tree/src/tree.type';
import type Node from 'element-plus/es/components/tree/src/model/node';
import { Folder, Document, Memo, Loading, Picture, Download, Search, Collection } from '@element-plus/icons-vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { useResourceStore } from '@/stores/resourceStore';
import { searchResources } from '@/api/resourceService';
import type { Resource, ResourceNode, ResourceType, ResourceSearchResultItem, KBSearchResultItem } from '@/api/types';
import KnowledgeBaseSearchDialog from './KnowledgeBaseSearchDialog.vue';

// --- Component Interface ---
const props = defineProps<{
  visible: boolean;
  resourceTypeFilter?: string | null;
  source: 'settings' | 'toolbar';
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'mount-resources', resources: Resource[]): void;
  (e: 'append-resources', resources: Resource[]): void;
  (e: 'mount-knowledge-base', resources: Resource[]): void;
}>();

// --- Store & I18n ---
const resourceStore = useResourceStore();
const { resourceTree, isResourcesLoading, loadingFolders, resources } = storeToRefs(resourceStore);
const { t } = useI18n();

// --- Local State ---
const selectorMode = ref<'resource' | 'kb'>('resource');
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

// Helper for single file preview
const currentFileInfo = computed(() => {
  return selectedResources.value[0]?.latest_version?.file_info || null;
});

const isImage = computed(() => {
  const mime = currentFileInfo.value?.mime_type;
  return mime ? mime.startsWith('image/') : false;
});

// 按钮显示逻辑
const showMountButton = computed(() => {
  if (selectedResources.value.length === 0) return false;

  // [Change] 在 Settings 场景下，如果选中的全是知识库，隐藏“挂载”按钮
  // 避免知识库进入 Settings 的挂载预览区
  if (props.source === 'settings') {
    const allKb = selectedResources.value.every(r => r.resourceType === 'knowledge_base');
    if (allKb) return false;
  }

  if (props.source === 'settings') return true;

  // Toolbar: 允许挂载 submessage_template 和 file
  return selectedResources.value.some(r =>
    r.resourceType === 'submessage_template' || r.resourceType === 'file'
  );
});

const showAppendButton = computed(() => {
  if (selectedResources.value.length === 0) return false;
  if (props.source === 'settings') return false;

  // Toolbar: 允许追加 system_prompt 和 submessage_template
  return selectedResources.value.some(r =>
    r.resourceType === 'system_prompt' || r.resourceType === 'submessage_template'
  );
});

// 判断是否显示知识库检索按钮
const showKbSearchButton = computed(() => {
  if (selectorMode.value !== 'resource') return false;
  if (selectedResources.value.length === 0) return false;
  // 仅当选中资源全为知识库时显示
  return selectedResources.value.every(r => r.resourceType === 'knowledge_base');
});

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
    // Reset mode to resource on open
    selectorMode.value = 'resource';
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
  if (!type) return t('resource.types.unknown');
  const map: Record<string, string> = {
    'system_prompt': 'system_prompt',
    'submessage_template': 'submessage_template',
    'knowledge_base': 'knowledge_base',
    'file': 'file'
  };
  const key = map[type];
  return key ? t(`resource.types.${key}`) : type;
};

const isResourceSelected = (resourceId: string): boolean => {
  return selectedResources.value.some(r => r.id === resourceId);
};

const isNodeDisabled = (data: ResourceNode): boolean => {
  if (!isMultiSelectMode.value || !selectionType.value) return false;

  // 普通文件夹永远不禁用（允许展开导航）
  if (data.itemType === 'folder' && data.resourceType !== 'knowledge_base') return false;

  // 知识库既是容器也是可选项，如果当前已选类型不匹配，则禁用选中
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
    name: t('resource.meta.name'),
    description: t('resource.meta.description'),
    content: t('resource.editor.contentLabel')
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

// Helper to check if a resource is an image (used in multi-select loop)
const isResourceImage = (resource: Resource): boolean => {
  const mime = resource.latest_version?.file_info?.mime_type;
  return mime ? mime.startsWith('image/') : false;
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
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
    ElMessage.error(t('resource.msg.searchFailed'));
  } finally {
    isSearching.value = false;
  }
};

const loadMore = () => {
  searchPage.value++;
  triggerSearch(false);
};

// --- Selection Logic (Shared) ---

const selectResourceById = async (resourceId: string, resourceType?: ResourceType | null, initialResourceObj?: Resource) => {
  let targetResource: Resource | undefined = resources.value.find(r => r.id === resourceId);

  if (!targetResource && initialResourceObj) {
    targetResource = initialResourceObj;
  }

  if (targetResource && props.resourceTypeFilter && targetResource.resourceType !== props.resourceTypeFilter) {
    ElMessage.warning(t('resource.msg.typeMismatch', { type: getReadableResourceType(props.resourceTypeFilter) }));
    return;
  }

  const typeToCheck = targetResource?.resourceType || resourceType;
  if (isMultiSelectMode.value && selectionType.value && typeToCheck && typeToCheck !== selectionType.value) {
     return;
  }

  if (!isMultiSelectMode.value) {
    if (targetResource) {
      selectedResources.value = [targetResource];
    }
    await loadResourcePreview(resourceId);
  } else {
    const index = selectedResources.value.findIndex(r => r.id === resourceId);
    if (index > -1) {
      selectedResources.value.splice(index, 1);
      if (selectedResources.value.length === 0) {
        selectionType.value = null;
      }
    } else {
      if (selectedResources.value.length === 0) {
        selectionType.value = typeToCheck || null;
      }
      if (targetResource) {
        selectedResources.value.push(targetResource);
      } else {
        selectedResources.value.push({
          id: resourceId,
          name: t('common.status.loading'),
          description: null,
          itemType: 'resource',
          resourceType: typeToCheck || null,
          parentId: null,
          sortOrder: 0,
          createdAt: '',
          updatedAt: '',
          latest_version: null,
          kb_id: null,
          kb_config: null
        });
      }
      loadResourcePreview(resourceId);
    }
  }
};

const handleSearchResultClick = (item: ResourceSearchResultItem) => {
  selectResourceById(item.resource_id, null, {
    id: item.resource_id,
    name: item.resource_name,
    description: null,
    itemType: 'resource',
    resourceType: null,
    parentId: null,
    sortOrder: 0,
    createdAt: item.updated_at,
    updatedAt: item.updated_at,
    latest_version: null,
    kb_id: null,
    kb_config: null
  });
};

// --- Tree Interaction Methods ---
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

  // 允许选中：资源类型为 'resource'，或者 (类型为 'folder' 且 是知识库)
  const isSelectable = resource.itemType === 'resource' || (resource.itemType === 'folder' && resource.resourceType === 'knowledge_base');

  if (!isSelectable || isNodeDisabled(resource)) return;

  selectResourceById(resource.id, resource.resourceType, resource);
};

async function loadResourcePreview(resourceId: string) {
  isPreviewLoading.value = true;
  try {
    await resourceStore.fetchResourceDetails(resourceId);
    const updatedResource = resources.value.find(r => r.id === resourceId);
    if (updatedResource) {
      const index = selectedResources.value.findIndex(r => r.id === resourceId);
      if (index !== -1) {
        selectedResources.value.splice(index, 1, updatedResource);
        if (isMultiSelectMode.value && selectedResources.value.length === 1) {
          selectionType.value = updatedResource.resourceType;
        }
      } else if (selectedResources.value.length === 0 && !isMultiSelectMode.value) {
        selectedResources.value = [updatedResource];
      }
    }
  } catch(e) {
    console.error("Failed to load resource content", e);
  } finally {
    isPreviewLoading.value = false;
  }
}

// --- Action Handlers ---

function handleMount() {
  if (selectedResources.value.length === 0) return;
  emit('mount-resources', selectedResources.value);
  emit('update:visible', false);
}

function handleAppend() {
  if (selectedResources.value.length === 0) return;
  emit('append-resources', selectedResources.value);
  emit('update:visible', false);
}

// 处理知识库挂载
function handleMountKnowledgeBase() {
  if (selectedResources.value.length === 0) return;
  emit('mount-knowledge-base', selectedResources.value); // 传递数组
  emit('update:visible', false);
}

// --- KB Selection Logic ---

const handleKBSelection = (items: KBSearchResultItem[]) => {
  // 将 KB 切片转换为 Resource 对象
  const resources: Resource[] = items.map(item => ({
    id: item.chunk_id,
    name: `片段: ${item.resource_name}`,
    description: `来自知识库: ${item.kb_name} (相似度: ${item.score.toFixed(4)})`,
    itemType: 'resource',
    resourceType: 'knowledge_base_chunk',
    parentId: item.kb_id,
    sortOrder: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    latest_version: {
      id: item.chunk_id,
      resourceId: item.chunk_id,
      name: 'v1',
      commitMessage: null,
      content: item.chunk_content,
      attributes: { score: item.score },
      sortOrder: 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      file_info: null
    },
    kb_id: null,
    kb_config: null
  }));

  emit('append-resources', resources);
  emit('update:visible', false);
};

function handleDialogClose() {
  searchText.value = '';
  selectedResources.value = [];
  selectionType.value = null;
  isPreviewLoading.value = false;
  expandedKeys.value.clear();
  searchResult.value = [];
  searchPage.value = 1;
  searchTotal.value = 0;
  selectorMode.value = 'resource';
}

const handleScroll = ({ scrollTop, scrollHeight, clientHeight }: any) => {
  if (scrollTop + clientHeight > scrollHeight - 50 && hasMore.value && !isSearching.value) {
    loadMore();
  }
};
</script>

<style scoped>
/* Reset & Layout */
.resource-selector-body { display: flex; flex-direction: column; height: 60vh; }
.toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-shrink: 0; }
.toolbar-divider { height: 20px; }
.mode-switch { flex-shrink: 0; }

.search-wrapper { display: flex; align-items: center; gap: 8px; flex-grow: 1; }
.search-input { flex-grow: 1; }
.regex-btn { font-family: monospace; font-weight: bold; padding: 8px; }

.multi-select-switch { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--el-text-color-regular); flex-shrink: 0; }
.kb-toolbar-placeholder { flex-grow: 1; display: flex; align-items: center; }
.info-text { font-size: 13px; color: var(--el-text-color-secondary); }

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

/* KB Preview Styles */
.kb-preview-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
  height: 100%;
}

.kb-desc {
  color: var(--el-text-color-secondary);
  margin-top: 10px;
  max-width: 80%;
}

/* --- File Preview Styles (Adapted from ResourceEditor) --- */
.file-preview-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  gap: 16px;
  width: 100%;
}

.file-preview-image {
  width: 100%;
  max-height: 400px;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f5f5f5;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}

.preview-img {
  width: 100%;
  height: 100%;
}

.file-generic {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background-color: var(--el-fill-color-lighter);
  width: 100%;
  max-width: 300px;
  text-align: center;
}

.file-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.file-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.file-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--el-text-color-secondary);
  gap: 12px;
}

.image-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  gap: 8px;
}

/* Mini styles for multi-select */
.file-preview-wrapper.mini {
  padding: 10px;
  flex-direction: row;
  justify-content: flex-start;
  align-items: flex-start;
  background-color: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.file-preview-image.mini {
  width: 80px;
  height: 80px;
  flex-shrink: 0;
  margin-right: 12px;
}

.file-generic.mini {
  flex-direction: row;
  padding: 8px;
  width: auto;
  max-width: none;
  background: none;
  border: none;
  gap: 8px;
  font-size: 13px;
}

.mini-empty {
  color: var(--el-text-color-placeholder);
  font-style: italic;
  font-size: 13px;
  padding: 8px 0;
}

/* Multi-select Preview Styles */
.multi-preview-item { margin-bottom: 10px; }
.multi-preview-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; font-weight: bold; }

/* Footer Actions */
.action-buttons {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

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
