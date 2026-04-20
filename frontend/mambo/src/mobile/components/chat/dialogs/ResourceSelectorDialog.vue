<!-- frontend/mambo/src/mobile/components/chat/dialogs/ResourceSelectorDialog.vue -->
<template>
  <el-drawer
    :model-value="visible"
    direction="rtl"
    size="100%"
    :before-close="handleDialogClose"
    class="mobile-resource-drawer"
  >
    <template #header>
      <div class="drawer-header">
        <span>{{ $t('resource.selector.title') }}</span>
        <div class="header-actions">
          <template v-if="selectorMode === 'resource'">
            <span class="multi-select-label">{{ $t('resource.selector.multiSelect') }}</span>
            <el-switch v-model="isMultiSelectMode" size="small" />
          </template>
        </div>
      </div>
    </template>

    <div class="drawer-content">
      <el-tabs v-model="selectorMode" class="selector-tabs" @tab-change="handleTabChange">
        <el-tab-pane :label="$t('resource.selector.modeResource')" name="resource">
          <div class="resource-section">
            <div class="search-row">
              <el-input
                v-model="searchText"
                :placeholder="$t('resource.selector.searchPlaceholder')"
                clearable
                @input="handleSearchInput"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
              <el-button
                :type="enableRegex ? 'primary' : 'default'"
                size="small"
                class="regex-btn"
                @click="toggleRegex"
              >
                .*
              </el-button>
            </div>

            <el-scrollbar class="tree-scroll-area" v-loading="isResourcesLoading && !searchText">
              <template v-if="searchText">
                <div v-if="isSearching" class="loading-placeholder">
                  <el-skeleton :rows="3" animated />
                </div>
                <div v-else-if="searchResult.length === 0" class="empty-box">
                  <el-empty :description="$t('chat.search.noResult')" :image-size="60" />
                </div>
                <div v-else class="search-list">
                  <div
                    v-for="item in searchResult"
                    :key="item.resource_id"
                    class="m-search-item"
                    :class="{ active: isResourceSelected(item.resource_id) }"
                    @click="handleSearchResultClick(item)"
                  >
                    <div class="item-info">
                      <div class="item-name">{{ item.resource_name }}</div>
                      <div class="item-meta">
                        <el-tag
                          size="small"
                          effect="plain"
                          :type="getMatchTypeTag(item.match_type)"
                        >
                          {{ getMatchTypeLabel(item.match_type) }}
                        </el-tag>
                        <span class="item-path">{{ item.resource_path }}</span>
                      </div>
                    </div>
                    <el-icon v-if="isResourceSelected(item.resource_id)" class="check-icon"
                      ><Check
                    /></el-icon>
                  </div>
                </div>
              </template>

              <template v-else>
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
                      class="m-tree-node"
                      :class="{
                        active: isResourceSelected(data.id),
                        disabled: isNodeDisabled(data),
                      }"
                    >
                      <div class="node-left">
                        <el-icon>
                          <Reading v-if="data.resourceType === 'skill'" />
                          <Collection v-else-if="data.resourceType === 'knowledge_base'" />
                          <Folder v-else-if="data.itemType === 'folder'" />
                          <Memo v-else-if="data.resourceType === 'submessage_template'" />
                          <Document v-else />
                        </el-icon>
                        <span class="label">{{ data.name }}</span>
                        <el-tag v-if="data.itemType === 'resource' && data.resourceType" size="small" type="info" class="resource-type-tag">
                          {{ getReadableResourceType(data.resourceType) }}
                        </el-tag>
                        <el-tag v-else-if="data.itemType === 'folder' && data.resourceType === 'knowledge_base'" size="small" type="primary" class="resource-type-tag">
                          {{ $t('resource.types.knowledge_base') }}
                        </el-tag>
                        <el-tag v-else-if="data.itemType === 'folder' && data.resourceType === 'skill'" size="small" type="danger" class="resource-type-tag">
                          {{ $t('resource.types.skill') }}
                        </el-tag>
                      </div>
                      <el-icon v-if="loadingFolders.has(data.id)" class="is-loading"
                        ><Loading
                      /></el-icon>
                      <el-icon v-else-if="isResourceSelected(data.id)" class="check-icon"
                        ><Check
                      /></el-icon>
                    </div>
                  </template>
                </el-tree>
              </template>
            </el-scrollbar>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="$t('resource.selector.modeKb')" name="kb">
          <div class="kb-section">
            <MobileKnowledgeBaseSearchDialog
              v-if="selectorMode === 'kb'"
              @selection-change="handleKBSelectionChange"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="drawer-footer-actions">
        <el-button
          v-if="showKbSearchButton"
          type="primary"
          :icon="Search"
          :disabled="selectedResources.length === 0"
          @click="handleMountKnowledgeBase"
          style="width: 100%; margin-bottom: 8px;"
        >
          {{ $t('resource.action.mountKbSearch') }}
        </el-button>

        <div class="action-buttons-row" v-if="showAppendButton || showMountButton">
          <el-button
            v-if="showAppendButton"
            type="primary"
            plain
            :disabled="selectedResources.length === 0"
            @click="handleAppend"
            :style="{ width: showMountButton ? '50%' : '100%' }"
          >
            {{ $t('resource.action.append', { count: selectedResources.length }) }}
          </el-button>

          <el-button
            v-if="showMountButton"
            type="primary"
            :disabled="selectedResources.length === 0"
            @click="handleMount"
            :style="{ width: showAppendButton ? '50%' : '100%' }"
          >
            {{ $t('resource.action.mount', { count: selectedResources.length }) }}
          </el-button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { ElTree, ElMessage } from 'element-plus'
import type { TreeNodeData } from 'element-plus/es/components/tree/src/tree.type'
import { Folder, Document, Memo, Loading, Search, Check, Collection, Reading } from '@element-plus/icons-vue'
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
  context: 'chat-settings' | 'chat-toolbar' | 'agent-toolbar' | 'agent-react' | 'agent-deep';
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

function handleDialogClose() {
  emit('update:visible', false)
}
</script>

<style scoped>

.resource-type-tag {
  flex-shrink: 0;
  margin-left: 8px;
  transform: scale(0.9);
}

.mobile-resource-drawer {
  background-color: var(--color-background);
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding-right: 10px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.multi-select-label {
  font-size: 14px;
  font-weight: normal;
  color: var(--el-text-color-regular);
}

.drawer-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 0 10px;
}

.selector-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

:deep(.el-tab-pane) {
  height: 100%;
}

.resource-section,
.kb-section {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.search-row {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  flex-shrink: 0;
  align-items: center;
}

.regex-btn {
  font-family: monospace;
  font-weight: bold;
}

.tree-scroll-area {
  flex: 1;
  overflow-y: auto;
}

.loading-placeholder {
  padding: 20px;
}

.empty-box {
  padding: 40px 0;
  text-align: center;
}

:deep(.el-tree-node__content) {
  height: auto !important;
  padding: 0 !important;
  align-items: stretch;
}

.m-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.m-tree-node.active {
  color: var(--el-color-primary);
}

.m-tree-node.disabled {
  opacity: 0.5;
}

.node-left {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.check-icon {
  color: var(--el-color-primary);
  margin-right: 5px;
}

.m-search-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.m-search-item.active {
  background-color: var(--el-color-primary-light-9);
  margin: 0 -10px;
  padding: 12px 10px;
  border-radius: 8px;
  border-bottom: none;
}

.item-info {
  flex: 1;
  overflow: hidden;
}

.item-name {
  font-size: 15px;
  font-weight: 500;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-path {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-footer-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 0;
  padding-bottom: calc(10px + env(safe-area-inset-bottom));
  background: var(--color-background);
}

.action-buttons-row {
  display: flex;
  gap: 10px;
  width: 100%;
}
</style>
<style>
.is-hidden-node {
  display: none !important;
}
</style>
