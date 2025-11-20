<template>
  <el-container class="resource-manager-container">
    <!-- Left Panel: Resource Tree -->
    <el-aside width="300px" class="resource-tree-panel">
      <ExplorerTree
        ref="treeRef"
        :data="treeData"
        :current-id="selectedResourceId"
        :is-loading="isResourcesLoading"
        folder-item-type="folder"
        persistence-key="mambo_resource_folder_expanded_state"
        @node-click="handleNodeClick"
        @node-contextmenu="handleNodeContextMenu"
        @root-contextmenu="openRootContextMenu"
        @reorder="handleReorder"
      >
        <template #header>
          <div class="panel-header">
            <h4>资源列表</h4>
          </div>
        </template>

        <template #item-icon="{ data }">
          <el-icon>
            <Folder v-if="data.itemType === 'folder'" />
            <Memo v-else-if="data.resourceType === 'submessage_template'" />
            <Document v-else />
          </el-icon>
        </template>
      </ExplorerTree>
    </el-aside>

    <!-- Main Panel: Editor Area -->
    <el-main class="resource-editor-panel">
      <div v-if="!activeResourceDetails" class="editor-placeholder">
        <el-empty description="从左侧选择一个资源进行编辑" />
      </div>
      <div v-else class="editor-container">

        <!-- Top Region: Version History (Horizontal) -->
        <div v-if="activeResourceDetails.itemType === 'resource'" class="version-top-bar">
          <div class="version-bar-header">
            <span class="version-bar-title">版本历史</span>
          </div>
          <el-scrollbar>
            <div class="version-list-horizontal">
              <template v-if="activeResourceDetails.versions && activeResourceDetails.versions.length > 0">
                <div
                  v-for="version in activeResourceDetails.versions"
                  :key="version.id"
                  class="version-card-horizontal"
                  :class="{
                    'is-active': activeResourceDetails.latest_version?.id === version.id,
                    'is-viewing': loadedVersionInEditor?.id === version.id
                  }"
                  @click="loadVersionIntoEditor(version)"
                >
                  <div class="version-card-header">
                    <span class="version-name">{{ version.name }}</span>
                    <span class="version-date">{{ new Date(version.createdAt).toLocaleDateString() }}</span>
                  </div>
                  <div class="version-card-body">
                      <p class="version-msg" :title="version.commitMessage ?? undefined">{{ version.commitMessage || '无描述' }}</p>
                  </div>
                  <div class="version-card-footer">
                    <el-button
                      v-if="activeResourceDetails.latest_version?.id !== version.id"
                      type="primary"
                      link
                      size="small"
                      @click.stop="handleSetActiveVersion(version.id)"
                    >
                      设为当前
                    </el-button>
                    <el-tag v-else type="success" size="small" effect="plain">当前版本</el-tag>
                  </div>
                </div>
              </template>
              <div v-else class="no-versions">暂无历史版本</div>
            </div>
          </el-scrollbar>
        </div>

        <!-- Bottom Region: Split View (Content Left, Meta Right) -->
        <el-form :model="form" label-position="top" ref="formRef" class="editor-split-layout">

          <!-- Left: Content Editor -->
          <div class="content-column">
            <template v-if="activeResourceDetails.itemType === 'resource'">
              <div class="content-header">
                <span class="content-label">{{ contentEditorLabel }}</span>
              </div>
              <el-form-item prop="content" class="content-form-item">
                <el-input
                  v-model="form.content"
                  type="textarea"
                  placeholder="在此处输入 Prompt 或模板内容..."
                  class="content-textarea"
                />
              </el-form-item>
            </template>
            <div v-else class="folder-placeholder">
              <el-empty description="文件夹无需编辑内容" :image-size="100" />
            </div>

            <!-- Footer Actions (Attached to content area) -->
            <div class="editor-footer">
              <el-button @click="resetForm">重置</el-button>
              <el-button v-if="activeResourceDetails.itemType === 'resource'" type="success" @click="openNewVersionDialog">另存为新版本</el-button>
              <el-button type="primary" @click="handleSaveChanges" :disabled="!isFormDirty">保存更改</el-button>
            </div>
          </div>

          <!-- Right: Meta Sidebar -->
          <div class="meta-column">
            <div class="meta-header">基本信息</div>
            <el-form-item label="名称" prop="name">
              <el-input v-model="form.name" placeholder="资源名称" />
            </el-form-item>
            <el-form-item label="描述" prop="description">
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="4"
                placeholder="资源描述"
                resize="none"
              />
            </el-form-item>

            <template v-if="activeResourceDetails.itemType === 'resource' && activeResourceDetails.resourceType === 'submessage_template'">
              <el-divider class="meta-divider" />
              <div class="meta-header">模板配置</div>
              <el-form-item>
                 <template #label>
                  <span>参与长度</span>
                  <el-tooltip effect="dark" content="上下文参与长度 (Context Participation Length)" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input-number
                  v-model="form.attributes.context_participation_length"
                  :min="0"
                  :step="1"
                  controls-position="right"
                  style="width: 100%;"
                />
              </el-form-item>
              <el-form-item>
                <template #label>
                  <span>默认折叠</span>
                  <el-tooltip effect="dark" content="在对话中注入时, 该模板内容是否默认折叠" placement="top">
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-switch v-model="form.attributes.is_collapsed" />
              </el-form-item>
            </template>

            <el-divider class="meta-divider" />
            <div class="meta-info">
               <div class="info-row">
                 <span>类型</span>
                 <el-tag size="small" type="info">{{ activeResourceDetails.resourceType || 'folder' }}</el-tag>
               </div>
               <div class="info-row">
                 <span>ID</span>
                 <span class="info-value" :title="activeResourceDetails.id">{{ activeResourceDetails.id.slice(0, 8) }}...</span>
               </div>
               <div class="info-row" v-if="activeResourceDetails.updatedAt">
                 <span>更新时间</span>
                 <span class="info-value">{{ new Date(activeResourceDetails.updatedAt).toLocaleDateString() }}</span>
               </div>
            </div>
          </div>

        </el-form>
      </div>
    </el-main>

    <!-- Context Menu -->
    <el-dropdown
      ref="contextMenuRef"
      trigger="contextmenu"
      @command="handleMenuCommand"
      popper-class="no-animation-popper"
    >
      <span :style="contextMenuPosition" />
      <template #dropdown>
        <el-dropdown-menu>
          <template v-if="!contextMenuItem || contextMenuItem.itemType === 'folder'">
            <el-dropdown-item command="newResource"><el-icon><DocumentAdd /></el-icon>新建资源</el-dropdown-item>
            <el-dropdown-item command="newFolder"><el-icon><FolderAdd /></el-icon>新建文件夹</el-dropdown-item>
          </template>
          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" :divided="!contextMenuItem || contextMenuItem.itemType === 'folder'"><el-icon><EditPen /></el-icon>重命名</el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item"><el-icon><Delete /></el-icon>删除</el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- Dialogs -->
    <EntityFormDialog
      v-model:visible="dialogState.visible.value"
      :title="dialogProps.title"
      :initial-name="dialogProps.initialName"
      :select-config="dialogProps.selectConfig"
      @confirm="onDialogConfirm"
    />

    <el-dialog v-model="newVersionDialog.visible" title="另存为新版本" width="500px">
      <el-form :model="newVersionDialog.form" label-position="top" ref="newVersionFormRef">
        <el-form-item label="版本名称" prop="name" :rules="{ required: true, message: '版本名称不能为空', trigger: 'blur' }">
          <el-input v-model="newVersionDialog.form.name" placeholder="例如：v1.1 优化了逻辑" />
        </el-form-item>
        <el-form-item label="提交信息 (可选)" prop="commitMessage">
          <el-input v-model="newVersionDialog.form.commitMessage" type="textarea" placeholder="描述本次变更的内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newVersionDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirmNewVersion">确认</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus';
import { Folder, Document, DocumentAdd, FolderAdd, EditPen, Delete, Memo, QuestionFilled } from '@element-plus/icons-vue';

import { useResourceStore } from '@/stores/resourceStore';
import { useTreeController, type DialogPayload, type DialogConfirmPayload } from '@/composables/useTreeController';
import ExplorerTree from '@/components/common/ExplorerTree.vue';
import EntityFormDialog from '@/components/common/EntityFormDialog.vue';

import type {
  Resource,
  ResourceCreate,
  ResourceUpdate,
  ResourceWithVersions,
  ResourceType,
  ResourceVersion,
  ResourceVersionCreate,
  BaseTreeItem,
} from '@/api/types';

// --- Local Type Definitions ---
interface SubMessageTemplateAttributes {
  context_participation_length: number;
  is_collapsed: boolean;
}

// --- Store ---
const resourceStore = useResourceStore();
const { isResourcesLoading, resources, resourceTree } = storeToRefs(resourceStore);

// --- Constants ---
const creatableResourceTypes: { value: ResourceType, label: string }[] = [
  { value: 'system_prompt', label: 'System Prompt' },
  { value: 'submessage_template', label: 'SubMessage 模板' },
];

const DEFAULT_SUBMESSAGE_ATTRIBUTES: SubMessageTemplateAttributes = {
  context_participation_length: 1,
  is_collapsed: false,
};

// --- Editor-Specific State ---
const formRef = ref<FormInstance>();
const newVersionFormRef = ref<FormInstance>();
const selectedResourceId = ref<string | undefined>(undefined);
const loadedVersionInEditor = ref<ResourceVersion | null>(null);

const form = reactive({
  name: '',
  description: '',
  content: '',
  attributes: { ...DEFAULT_SUBMESSAGE_ATTRIBUTES },
});

const newVersionDialog = reactive({
  visible: false,
  form: {
    name: '',
    commitMessage: '',
  },
});

// --- Computed Properties ---
const treeData = resourceTree;

const activeResourceDetails = computed((): ResourceWithVersions | null => {
  if (!selectedResourceId.value) return null;
  return resources.value.find(r => r.id === selectedResourceId.value) || null;
});

const isFormDirty = computed(() => {
  if (!activeResourceDetails.value) return false;
  const original = activeResourceDetails.value;
  const originalVersion = loadedVersionInEditor.value ?? original.latest_version;

  const isMetaDirty = form.name !== original.name || form.description !== (original.description || '');

  if (original.itemType === 'resource') {
    const isContentDirty = form.content !== (originalVersion?.content || '');

    let isAttributesDirty = false;
    if (original.resourceType === 'submessage_template') {
      const originalAttributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES, ...(originalVersion?.attributes as Partial<SubMessageTemplateAttributes> || {}) };
      isAttributesDirty = JSON.stringify(form.attributes) !== JSON.stringify(originalAttributes);
    }

    return isMetaDirty || isContentDirty || isAttributesDirty;
  }

  return isMetaDirty;
});

const contentEditorLabel = computed(() => {
  if (loadedVersionInEditor.value) {
    return `内容 (正在查看: ${loadedVersionInEditor.value.name})`;
  }
  return '内容 (当前版本)';
});

// --- Tree Controller Logic ---
const {
  treeRef,
  contextMenuRef,
  contextMenuItem,
  contextMenuPosition,
  dialogState,
  dialogProps,
  handleReorder,
  handleNodeContextMenu,
  openRootContextMenu,
  handleMenuCommand,
  onDialogConfirm,
} = useTreeController<Resource, ResourceCreate, ResourceUpdate>({
  items: resources,
  crudHandlers: {
    createItem: resourceStore.addResourceItem,
    updateItem: resourceStore.updateResourceItem,
    deleteItem: async (id: string) => {
      await resourceStore.deleteResourceItem(id);
      if (selectedResourceId.value === id) {
        selectedResourceId.value = undefined;
      }
    },
    reorderItems: resourceStore.reorderResourceItems,
  },
  getDialogProps: (payload: DialogPayload<Resource>) => {
    switch (payload.type) {
      case 'rename':
        return { title: '重命名', initialName: payload.targetItem?.name || '' };
      case 'newResource':
        return {
          title: '新建资源',
          initialName: '新的资源',
          selectConfig: {
            label: '资源类型',
            options: creatableResourceTypes,
            initialValue: creatableResourceTypes[0].value,
          },
        };
      case 'newFolder':
        return { title: '新建文件夹', initialName: '新的文件夹' };
      default:
        return { title: '', initialName: '' };
    }
  },
  handleDialogConfirm: async (
    dialogPayload: DialogPayload<Resource>,
    formPayload: DialogConfirmPayload
  ): Promise<Resource | null> => {
    if (dialogPayload.type === 'rename' && dialogPayload.targetItem) {
      await resourceStore.updateResourceItem(dialogPayload.targetItem.id, { name: formPayload.name });
      return null;
    }

    const sortOrder = calculateSortOrder(dialogPayload.parentId);
    let newItem: Resource | null = null;

    if (dialogPayload.type === 'newResource') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'resource',
        resourceType: formPayload.selectValue as ResourceType,
        parentId: dialogPayload.parentId,
        sortOrder,
        initial_content: '',
        initial_attributes: formPayload.selectValue === 'submessage_template' ? { ...DEFAULT_SUBMESSAGE_ATTRIBUTES } : undefined,
      });
      if (newItem) {
        selectedResourceId.value = newItem.id;
        await resourceStore.fetchResourceDetails(newItem.id);
      }
    } else if (dialogPayload.type === 'newFolder') {
      newItem = await resourceStore.addResourceItem({
        name: formPayload.name,
        itemType: 'folder',
        parentId: dialogPayload.parentId,
        sortOrder
      });
    }
    return newItem;
  }
});

// --- Helper Functions ---
const calculateSortOrder = (parentId: string | null = null): number => {
  return resources.value.filter(r => r.parentId === parentId).length;
};

// --- Lifecycle ---
onMounted(() => {
  resourceStore.fetchResources();
});

// --- Watchers ---
watch(activeResourceDetails, (newSelection) => {
  if (newSelection) {
    form.name = newSelection.name;
    form.description = newSelection.description || '';
    form.content = newSelection.latest_version?.content || '';

    if (newSelection.resourceType === 'submessage_template') {
      form.attributes = {
        ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
        ...(newSelection.latest_version?.attributes as Partial<SubMessageTemplateAttributes> || {}),
      };
    } else {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
    }

    loadedVersionInEditor.value = null;
  } else {
    form.name = '';
    form.description = '';
    form.content = '';
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
  }
});

// --- Handlers ---
async function handleNodeClick(data: BaseTreeItem) {
  selectedResourceId.value = data.id;
  if (data.itemType === 'resource') {
    await resourceStore.fetchResourceDetails(data.id);
  }
}

function resetForm() {
  const selection = activeResourceDetails.value;
  if (selection) {
    form.name = selection.name;
    form.description = selection.description || '';
    form.content = selection.latest_version?.content || '';

    if (selection.resourceType === 'submessage_template') {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES, ...(selection.latest_version?.attributes as Partial<SubMessageTemplateAttributes> || {}) };
    } else {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
    }

    loadedVersionInEditor.value = null;
  }
}

async function handleSaveChanges() {
  if (!activeResourceDetails.value || !isFormDirty.value) return;
  const resource = activeResourceDetails.value;

  if (form.name !== resource.name || form.description !== (resource.description || '')) {
    await resourceStore.updateResourceItem(resource.id, {
      name: form.name,
      description: form.description,
    });
  }

  if (resource.itemType === 'resource') {
    await resourceStore.updateActiveVersionDetails(resource.id, {
      content: form.content,
      attributes: form.attributes,
    });
  }

  ElMessage.success('保存成功');
  loadedVersionInEditor.value = null;
}

function loadVersionIntoEditor(version: ResourceVersion) {
  form.content = version.content || '';
  if (activeResourceDetails.value?.resourceType === 'submessage_template') {
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES, ...(version.attributes as Partial<SubMessageTemplateAttributes> || {}) };
  } else {
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
  }
  loadedVersionInEditor.value = version;
}

async function handleSetActiveVersion(versionId: string) {
  if (!activeResourceDetails.value) return;
  try {
    await ElMessageBox.confirm('确定要将此版本设为当前活跃版本吗？', '确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'info'
    });
    await resourceStore.setActiveResourceVersion(activeResourceDetails.value.id, versionId);
    ElMessage.success('活跃版本已切换');
  } catch { /* User canceled */ }
}

function openNewVersionDialog() {
  if (!activeResourceDetails.value) return;
  newVersionDialog.form.name = `v${activeResourceDetails.value.versions.length + 1}`;
  newVersionDialog.form.commitMessage = '';
  newVersionDialog.visible = true;
}

async function handleConfirmNewVersion() {
  if (!newVersionFormRef.value || !activeResourceDetails.value) return;
  await newVersionFormRef.value.validate(async (valid) => {
    if (valid) {
      const versionData: ResourceVersionCreate = {
        ...newVersionDialog.form,
        content: form.content,
        attributes: form.attributes,
      };
      await resourceStore.createNewVersion(activeResourceDetails.value!.id, versionData);
      newVersionDialog.visible = false;
      ElMessage.success('新版本创建成功');
    }
  });
}
</script>

<style scoped>
.resource-manager-container {
  height: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background-color: #fff;
}

.resource-tree-panel {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--el-border-color);
  background-color: var(--color-background-soft);
}

.panel-header {
  padding: 16px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: default;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
}

.resource-editor-panel {
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.editor-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

/* --- Top Version Bar --- */
.version-top-bar {
  flex-shrink: 0;
  height: 140px;
  border-bottom: 1px solid var(--el-border-color);
  background-color: var(--el-fill-color-lighter);
  display: flex;
  flex-direction: column;
}

.version-bar-header {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
}

.version-list-horizontal {
  display: flex;
  padding: 0 12px 12px 12px;
  gap: 12px;
}

.version-card-horizontal {
  flex-shrink: 0;
  width: 200px;
  height: 90px;
  background-color: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.version-card-horizontal:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.version-card-horizontal.is-active {
  border-color: var(--el-color-success);
  background-color: var(--el-color-success-light-9);
}

.version-card-horizontal.is-viewing {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

.version-card-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}

.version-date {
  font-weight: normal;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.version-card-body {
  flex-grow: 1;
  overflow: hidden;
}

.version-msg {
  margin: 0;
  font-size: 11px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.version-card-footer {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
}

.no-versions {
  padding: 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

/* --- Split Layout --- */
.editor-split-layout {
  flex-grow: 1;
  display: flex;
  min-height: 0; /* Important for flex child scrolling */
}

/* Left: Content Column */
.content-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 0;
  position: relative;
}

.content-header {
  padding: 12px 20px 0 20px;
  flex-shrink: 0;
}

.content-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.content-form-item {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  margin-bottom: 0 !important;
  padding: 10px 20px 0 20px;
}

:deep(.content-form-item .el-form-item__content) {
  flex-grow: 1;
  height: 100%;
}

:deep(.content-textarea) {
  height: 100%;
}

:deep(.content-textarea .el-textarea__inner) {
  height: 100% !important;
  resize: none;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  line-height: 1.6;
  padding: 12px;
  border-radius: 4px;
}

.folder-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.editor-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 16px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background-color: #fff;
}

/* Right: Meta Sidebar */
.meta-column {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color);
  background-color: var(--el-fill-color-extra-light);
  padding: 20px;
  overflow-y: auto;
}

.meta-header {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
  text-transform: uppercase;
}

.meta-divider {
  margin: 24px 0 16px 0;
}

.meta-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.info-value {
  color: var(--el-text-color-regular);
  font-family: monospace;
}

.label-icon {
  margin-left: 6px;
  color: #909399;
  cursor: help;
}

.delete-item {
  color: var(--el-color-danger);
}
</style>

<style>
.no-animation-popper {
  transition: none !important;
  animation: none !important;
}
</style>
