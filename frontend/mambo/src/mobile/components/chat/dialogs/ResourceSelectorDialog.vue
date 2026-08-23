<!-- ResourceSelectorDialog.vue — 移动端资源选择器（底部弹出面板） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="rs-overlay" @click="handleDialogClose">
        <div class="rs-sheet" @click.stop>
          <div class="sheet-handle"></div>

          <!-- Header -->
          <div class="rs-header">
            <span class="rs-title">{{ $t('resource.selector.title') }}</span>
            <label class="multi-toggle" v-if="selectorMode === 'resource'">
              <span>{{ $t('resource.selector.multiSelect') }}</span>
              <input type="checkbox" v-model="isMultiSelectMode" />
              <span class="toggle-track"></span>
            </label>
          </div>

          <!-- Tab bar -->
          <div class="rs-tabs">
            <button
              class="rs-tab"
              :class="{ active: selectorMode === 'resource' }"
              @click="selectorMode = 'resource'; selectedResources = []; selectionType = null"
            >资源</button>
            <button
              class="rs-tab"
              :class="{ active: selectorMode === 'kb' }"
              @click="selectorMode = 'kb'; selectedResources = []; selectionType = null"
            >知识库</button>
          </div>

          <!-- Search -->
          <div class="rs-search" v-if="selectorMode === 'resource'">
            <el-icon :size="16" class="search-icon"><Search /></el-icon>
            <input
              v-model="searchText"
              :placeholder="$t('resource.selector.searchPlaceholder')"
              class="search-input"
              @input="handleSearchInput"
            />
            <button v-if="searchText" class="search-clear" @click="searchText = ''; searchResult = []">
              <el-icon :size="14"><Close /></el-icon>
            </button>
          </div>

          <!-- Content -->
          <div class="rs-body">
            <!-- Resource Tree -->
            <template v-if="selectorMode === 'resource'">
              <div class="rs-list" v-if="searchText">
                <div v-if="isSearching" class="rs-loading">搜索中...</div>
                <div v-else-if="searchResult.length === 0" class="rs-empty">无结果</div>
                <button
                  v-for="item in searchResult"
                  :key="item.resource_id"
                  class="rs-item"
                  :class="{ selected: isResourceSelected(item.resource_id) }"
                  @click="handleSearchResultClick(item)"
                >
                  <el-icon :size="18"><Document /></el-icon>
                  <div class="rs-item-info">
                    <span class="rs-item-name">{{ item.resource_name }}</span>
                    <span class="rs-item-meta">{{ getMatchTypeLabel(item.match_type) }} · {{ item.resource_path }}</span>
                  </div>
                  <el-icon v-if="isResourceSelected(item.resource_id)" class="rs-check"><Select /></el-icon>
                </button>
              </div>

              <div v-else class="rs-tree-wrap" v-loading="isResourcesLoading">
                <el-tree
                  ref="treeRef"
                  :data="filteredTreeData"
                  node-key="id"
                  :props="treeProps"
                  :expand-on-click-node="false"
                  :highlight-current="!isMultiSelectMode"
                  @node-click="handleNodeClick"
                  @node-expand="handleNodeExpand"
                  @node-collapse="handleNodeCollapse"
                >
                  <template #default="{ data }">
                    <div
                      class="rs-tree-node"
                      :class="{
                        selected: isResourceSelected(data.id),
                        disabled: isNodeDisabled(data),
                      }"
                    >
                      <el-icon :size="18">
                        <Reading v-if="data.resourceType === 'skill'" />
                        <Collection v-else-if="data.resourceType === 'knowledge_base'" />
                        <Folder v-else-if="data.itemType === 'folder'" />
                        <Memo v-else-if="data.resourceType === 'submessage_template'" />
                        <Document v-else />
                      </el-icon>
                      <span class="rs-node-name">{{ data.name }}</span>
                      <el-tag v-if="data.itemType === 'resource' && data.resourceType" size="small" type="info" class="rs-type-tag">
                        {{ getReadableResourceType(data.resourceType) }}
                      </el-tag>
                      <el-icon v-if="loadingFolders.has(data.id)" class="is-loading"><Loading /></el-icon>
                      <el-icon v-else-if="isResourceSelected(data.id)" class="rs-check"><Select /></el-icon>
                    </div>
                  </template>
                </el-tree>
              </div>
            </template>

            <!-- KB Section -->
            <div class="rs-kb-wrap" v-if="selectorMode === 'kb'">
              <MobileKnowledgeBaseSearchDialog @selection-change="handleKBSelectionChange" @confirm="handleKBConfirm" />
            </div>
          </div>

          <!-- Footer -->
          <div class="rs-footer" v-if="selectedResources.length > 0">
            <span class="rs-selected-count">已选 {{ selectedResources.length }} 项</span>
            <div class="rs-footer-actions">
              <button
                v-if="showKbSearchButton"
                class="rs-btn primary"
                @click="handleMountKnowledgeBase"
              >挂载知识库检索</button>
              <button
                v-if="showAppendButton"
                class="rs-btn outline"
                @click="handleAppend"
              >追加到输入</button>
              <button
                v-if="showMountButton"
                class="rs-btn primary"
                @click="handleMount"
              >挂载</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { ElTree, ElMessage } from 'element-plus'
import type { TreeNodeData } from 'element-plus/es/components/tree/src/tree.type'
import { Folder, Document, Memo, Loading, Search, Select, Collection, Reading, Close } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useResourceStore } from '@/stores/resourceStore'
import { searchResources } from '@/api/resourceService'
import type {
  Resource,
  ResourceNode,
  ResourceType,
  ResourceSearchResultItem,
  KBSearchResultItem,
} from '@/api/types'
import MobileKnowledgeBaseSearchDialog from './KnowledgeBaseSearchDialog.vue'

const props = defineProps<{
  visible: boolean;
  context: 'chat-settings' | 'chat-toolbar' | 'agent-toolbar' | 'agent-react' | 'agent-deep' | 'agent-memory';
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'mount-resources', resources: Resource[]): void
  (e: 'append-resources', resources: Resource[]): void
  (e: 'mount-knowledge-base', resources: Resource[]): void
}>()

const resourceStore = useResourceStore()
const { resourceTree, isResourcesLoading, loadingFolders, resources } = storeToRefs(resourceStore)
const { t } = useI18n()

const selectorMode = ref<'resource' | 'kb'>('resource')
const searchText = ref('')
const treeRef = ref<InstanceType<typeof ElTree>>()
const selectedResources = ref<Resource[]>([])
const isMultiSelectMode = ref(false)
const selectionType = ref<ResourceType | null>(null)
const expandedKeys = ref<Set<string>>(new Set())
const STORAGE_KEY = 'resource_selector_multi_select_mode'

const isSearching = ref(false)
const enableRegex = ref(false)
const searchResult = ref<ResourceSearchResultItem[]>([])
const searchPage = ref(1)
const searchTotal = ref(0)
const searchDebounceTimer = ref<number | undefined>(undefined)

const contextConfig = computed(() => {
  switch (props.context) {
    case 'chat-settings':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'knowledge_base'],
        canMount: ['system_prompt', 'submessage_template'],
        canAppend: [],
        canMountKb: ['knowledge_base']
      };
    case 'chat-toolbar':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'file', 'knowledge_base'],
        canMount: ['submessage_template', 'file'],
        canAppend: ['system_prompt', 'submessage_template'],
        canMountKb: ['knowledge_base']
      };
    case 'agent-toolbar':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'file'],
        canMount: ['submessage_template', 'file'],
        canAppend: ['system_prompt', 'submessage_template'],
        canMountKb: []
      };
    case 'agent-react':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'knowledge_base'],
        canMount: ['system_prompt', 'submessage_template', 'knowledge_base'],
        canAppend: [],
        canMountKb: []
      };
    case 'agent-deep':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'knowledge_base', 'skill'],
        canMount: ['system_prompt', 'submessage_template', 'knowledge_base', 'skill'],
        canAppend: [],
        canMountKb: []
      };
    case 'agent-memory':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'knowledge_base', 'file'],
        canMount: ['system_prompt', 'submessage_template', 'knowledge_base', 'file'],
        canAppend: [],
        canMountKb: ['knowledge_base']
      };
    default:
      return { allowedTypes: [], canMount: [], canAppend: [], canMountKb: [] };
  }
});

onMounted(() => {
  const persistedMode = localStorage.getItem(STORAGE_KEY)
  isMultiSelectMode.value = persistedMode === 'true'
})

const filteredTreeData = computed(() => filterTreeByType(resourceTree.value))

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: (data: TreeNodeData) => (data as ResourceNode).itemType !== 'folder',
  class: (data: TreeNodeData) =>
    (data as ResourceNode).itemType === 'stub' ? 'is-hidden-node' : '',
}

const showMountButton = computed(() => {
  if (selectedResources.value.length === 0) return false;
  return selectedResources.value.every(r => contextConfig.value.canMount.includes(r.resourceType as string));
});

const showAppendButton = computed(() => {
  if (selectedResources.value.length === 0) return false;
  return selectedResources.value.every(r => contextConfig.value.canAppend.includes(r.resourceType as string));
});

const showKbSearchButton = computed(() => {
  if (selectorMode.value !== 'resource' || selectedResources.value.length === 0) return false;
  return selectedResources.value.every(r => contextConfig.value.canMountKb.includes(r.resourceType as string));
});

watch(
  () => props.visible,
  (isVisible) => {
    if (isVisible) {
      resourceStore.initializeList()
      expandedKeys.value.clear()
      selectorMode.value = 'resource'
      searchText.value = ''
      searchResult.value = []
      selectedResources.value = []
      selectionType.value = null
    } else {
      selectedResources.value = []
      selectionType.value = null
    }
  },
)

watch(isMultiSelectMode, (newMode) => {
  localStorage.setItem(STORAGE_KEY, String(newMode))
  selectedResources.value = []
  selectionType.value = null
})

watch(filteredTreeData, () => {
  nextTick(() => {
    if (!treeRef.value) return
    expandedKeys.value.forEach((key) => {
      treeRef.value!.getNode(key)?.expand()
    })
  })
})

const getReadableResourceType = (type: string | null) => {
  if (!type) return t('resource.types.unknown')
  const map: Record<string, string> = {
    system_prompt: 'system_prompt',
    submessage_template: 'submessage_template',
    knowledge_base: 'knowledge_base',
    file: 'file',
    skill: 'skill'
  }
  const key = map[type]
  return key ? t(`resource.types.${key}`) : type
}

const isResourceSelected = (resourceId: string): boolean => {
  return selectedResources.value.some((r) => r.id === resourceId)
}

const isNodeDisabled = (data: ResourceNode): boolean => {
  if (!isMultiSelectMode.value || !selectionType.value) return false;
  if (data.itemType === 'folder' && data.resourceType !== 'knowledge_base' && data.resourceType !== 'skill') return false;
  return data.resourceType !== selectionType.value;
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

const getMatchTypeTag = (type: string): TagType => {
  const map: Record<string, TagType> = {
    name: 'primary',
    description: 'info',
    content: 'success',
  }
  return map[type] || 'info'
}

const getMatchTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    name: t('resource.meta.name'),
    description: t('resource.meta.description'),
    content: t('resource.editor.contentLabel'),
  }
  return map[type] || type
}

function filterTreeByType(nodes: ResourceNode[]): ResourceNode[] {
  const allowed = contextConfig.value.allowedTypes;
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

const toggleRegex = () => {
  enableRegex.value = !enableRegex.value
  if (searchText.value) triggerSearch()
}

const handleSearchInput = () => {
  clearTimeout(searchDebounceTimer.value)
  searchDebounceTimer.value = window.setTimeout(() => {
    triggerSearch()
  }, 300)
}

const triggerSearch = async (resetPage = true) => {
  if (!searchText.value.trim()) {
    searchResult.value = []
    return
  }
  if (resetPage) {
    searchPage.value = 1
    searchResult.value = []
  }

  isSearching.value = true
  try {
    const res = await searchResources({
      keyword: searchText.value.trim(),
      enable_regex: enableRegex.value,
      page_num: searchPage.value,
      page_size: 20,
    })
    if (resetPage) {
      searchResult.value = res.items
    } else {
      searchResult.value = [...searchResult.value, ...res.items]
    }
    searchTotal.value = res.total
  } catch (e) {
    console.error('Search failed:', e)
    ElMessage.error(t('resource.msg.searchFailed'))
  } finally {
    isSearching.value = false
  }
}

const selectResourceById = async (
  resourceId: string,
  resourceType?: ResourceType | null,
  initialResourceObj?: Resource,
) => {
  let targetResource: Resource | undefined = resources.value.find((r) => r.id === resourceId)
  if (!targetResource && initialResourceObj) {
    targetResource = initialResourceObj
  }

  const typeToCheck = targetResource?.resourceType || resourceType

  if (typeToCheck && !contextConfig.value.allowedTypes.includes(typeToCheck as string)) {
    ElMessage.warning(
      t('resource.msg.typeMismatch', { type: getReadableResourceType(typeToCheck as string) })
    )
    return
  }

  if (
    isMultiSelectMode.value &&
    selectionType.value &&
    typeToCheck &&
    typeToCheck !== selectionType.value
  ) {
    return
  }

  if (!isMultiSelectMode.value) {
    if (targetResource) {
      selectedResources.value = [targetResource]
    }
  } else {
    const index = selectedResources.value.findIndex((r) => r.id === resourceId)
    if (index > -1) {
      selectedResources.value.splice(index, 1)
      if (selectedResources.value.length === 0) selectionType.value = null
    } else {
      if (selectedResources.value.length === 0) selectionType.value = typeToCheck || null
      if (targetResource) {
        selectedResources.value.push(targetResource)
      }
    }
  }

  if (targetResource && !targetResource.latest_version?.content) {
    try {
      await resourceStore.fetchResourceDetails(resourceId)
      const updatedResource = resources.value.find((r) => r.id === resourceId)
      if (updatedResource) {
        const idx = selectedResources.value.findIndex((r) => r.id === resourceId)
        if (idx !== -1) {
          selectedResources.value[idx] = updatedResource
        }
      }
    } catch (error) {
      console.error(`Failed to fetch resource details for ${resourceId}`, error)
      ElMessage.error(t('common.error.loadingFailed'))
    }
  }
}

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
    kb_config: null,
  })
}

const handleNodeClick = async (data: TreeNodeData) => {
  const resource = data as ResourceNode
  const isSelectable =
    resource.itemType === 'resource' ||
    (resource.itemType === 'folder' && (resource.resourceType === 'knowledge_base' || resource.resourceType === 'skill'))
  if (!isSelectable || isNodeDisabled(resource)) return

  selectResourceById(resource.id, resource.resourceType, resource)
}

const handleNodeExpand = (data: ResourceNode) => {
  expandedKeys.value.add(data.id)
  if (data.itemType === 'folder') {
    resourceStore.fetchResourceChildren(data.id)
  }
}

const handleNodeCollapse = (data: ResourceNode) => {
  expandedKeys.value.delete(data.id)
}

const handleTabChange = () => {
  selectedResources.value = []
  selectionType.value = null
}

const handleKBSelectionChange = (items: KBSearchResultItem[]) => {
  const kbResources: Resource[] = items.map((item) => ({
    id: item.chunk_id,
    name: `Chunk: ${item.resource_name}`,
    description: `From: ${item.kb_name}`,
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
      file_info: null,
    },
    kb_id: null,
    kb_config: null,
  }))

  selectedResources.value = kbResources
}

function handleMount() {
  if (selectedResources.value.length === 0) return
  emit('mount-resources', selectedResources.value)
  emit('update:visible', false)
}

function handleAppend() {
  if (selectedResources.value.length === 0) return
  emit('append-resources', selectedResources.value)
  emit('update:visible', false)
}

function handleMountKnowledgeBase() {
  if (selectedResources.value.length === 0) return
  emit('mount-knowledge-base', selectedResources.value)
  emit('update:visible', false)
}

function handleKBConfirm(items: KBSearchResultItem[]) {
  const kbResources: Resource[] = items.map((item) => ({
    id: item.chunk_id,
    name: `Chunk: ${item.resource_name}`,
    description: `From: ${item.kb_name}`,
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
      file_info: null,
    },
    kb_id: null,
    kb_config: null,
  }))
  emit('append-resources', kbResources)
  emit('update:visible', false)
}

function handleDialogClose() {
  emit('update:visible', false)
}
</script>

<style scoped>
.rs-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 2000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.rs-sheet {
  width: 100%;
  max-width: 500px;
  max-height: 85vh;
  background: var(--color-background);
  border-radius: 16px 16px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--el-border-color);
  border-radius: 2px;
  margin: 8px auto 0;
  flex-shrink: 0;
}

.rs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px 8px;
  flex-shrink: 0;
}

.rs-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--color-heading);
}

.multi-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

.multi-toggle input {
  display: none;
}

.toggle-track {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: var(--el-border-color);
  position: relative;
  transition: background 0.2s;
}

.toggle-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}

.multi-toggle input:checked + .toggle-track {
  background: var(--el-color-primary);
}

.multi-toggle input:checked + .toggle-track::after {
  transform: translateX(18px);
}

.rs-tabs {
  display: flex;
  gap: 0;
  padding: 0 16px 8px;
  flex-shrink: 0;
}

.rs-tab {
  flex: 1;
  padding: 8px 0;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  text-align: center;
}

.rs-tab.active {
  color: var(--el-color-primary);
  border-bottom-color: var(--el-color-primary);
}

.rs-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 16px 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 10px;
  flex-shrink: 0;
}

.search-icon {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 15px;
  color: var(--el-text-color-primary);
  outline: none;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--el-text-color-placeholder);
}

.search-clear {
  display: flex;
  align-items: center;
  padding: 2px;
  border: none;
  background: var(--el-text-color-placeholder);
  color: #fff;
  border-radius: 50%;
  cursor: pointer;
  flex-shrink: 0;
}

.rs-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.rs-list {
  padding: 0 16px;
  overflow-y: auto;
  max-height: 100%;
}

.rs-loading,
.rs-empty {
  padding: 32px 0;
  text-align: center;
  font-size: 14px;
  color: var(--el-text-color-placeholder);
}

.rs-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 12px 0;
  border: none;
  border-bottom: 0.5px solid var(--el-border-color-lighter);
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: background 0.15s;
}

.rs-item:active {
  background: var(--el-fill-color-light);
  margin: 0 -16px;
  padding: 12px 16px;
}

.rs-item.selected {
  color: var(--el-color-primary);
}

.rs-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rs-item-name {
  font-size: 15px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rs-item-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rs-check {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.rs-tree-wrap {
  padding: 0 8px;
}

:deep(.el-tree-node__content) {
  height: auto !important;
  padding: 0 !important;
  align-items: stretch;
}

.rs-tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 8px;
  border-radius: 8px;
  font-size: 15px;
  transition: background 0.15s;
}

.rs-tree-node:active {
  background: var(--el-fill-color-light);
}

.rs-tree-node.selected {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.rs-tree-node.disabled {
  opacity: 0.4;
}

.rs-node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rs-type-tag {
  flex-shrink: 0;
  transform: scale(0.85);
}

.rs-kb-wrap {
  height: 100%;
  padding: 0 16px;
  overflow-y: auto;
}

.rs-footer {
  flex-shrink: 0;
  padding: 12px 16px;
  padding-bottom: max(12px, env(safe-area-inset-bottom));
  border-top: 0.5px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rs-selected-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.rs-footer-actions {
  display: flex;
  gap: 8px;
}

.rs-btn {
  flex: 1;
  padding: 12px 8px;
  border: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.rs-btn.primary {
  background: var(--el-color-primary);
  color: #fff;
}

.rs-btn.outline {
  background: transparent;
  color: var(--el-color-primary);
  border: 1.5px solid var(--el-color-primary);
}

.rs-btn:active {
  transform: scale(0.96);
}

/* Transitions */
.sheet-enter-active { transition: all 0.25s ease-out; }
.sheet-leave-active { transition: all 0.2s ease-in; }
.sheet-enter-from .rs-sheet,
.sheet-leave-to .rs-sheet { transform: translateY(100%); }
.sheet-enter-from { opacity: 0; }
.sheet-leave-to { opacity: 0; }
</style>
<style>
.is-hidden-node {
  display: none !important;
}
</style>
