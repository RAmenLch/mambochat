<!-- frontend/mambo/src/components/settings/ResourceManager.vue -->
<template>
  <el-container class="resource-manager-container">
    <!-- Left Panel: Resource Tree -->
    <el-aside width="300px" class="resource-tree-panel" @contextmenu.prevent="openContextMenu($event, null)">
      <div class="panel-header">
        <h4>资源列表</h4>
      </div>
      <el-scrollbar class="tree-scrollbar">
        <div v-if="isResourcesLoading" class="loading-container">
          <el-skeleton :rows="8" animated />
        </div>
        <el-tree
          v-else-if="resourceTree.length > 0"
          ref="treeRef"
          :data="resourceTree"
          node-key="id"
          highlight-current
          :current-node-key="selectedResourceId"
          :expand-on-click-node="false"
          draggable
          :allow-drop="allowDrop"
          :indent="12"
          @node-click="handleNodeClick"
          @node-drop="handleNodeDrop"
          @node-contextmenu="openContextMenu"
          class="resource-tree"
          :props="{ label: 'name', children: 'children' }"
        >
          <template #default="{ data }">
            <span class="custom-tree-node">
              <el-icon class="node-icon">
                <Folder v-if="data.itemType === 'folder'" />
                <Memo v-else-if="data.resourceType === 'submessage_template'" />
                <Document v-else />
              </el-icon>
              <span class="node-label">{{ data.name }}</span>
            </span>
          </template>
        </el-tree>
        <el-empty v-else description="右键新建资源或文件夹" />
      </el-scrollbar>
    </el-aside>

    <!-- Right Panel: Editor & Version History -->
    <el-main class="resource-editor-panel">
      <div v-if="!activeResourceDetails" class="editor-placeholder">
        <el-empty description="从左侧选择一个资源进行编辑" />
      </div>
      <div v-else class="editor-container">
        <!-- Main Editor -->
        <div class="editor-content">
          <el-form :model="form" label-position="top" ref="formRef" class="editor-form">
            <el-form-item label="名称" prop="name">
              <el-input v-model="form.name" />
            </el-form-item>
            <el-form-item label="描述" prop="description">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>

            <template v-if="activeResourceDetails.itemType === 'resource'">
              <el-form-item
                :label="contentEditorLabel"
                prop="content"
                class="content-form-item"
              >
                <el-input v-model="form.content" type="textarea" placeholder="在此处输入内容..." />
              </el-form-item>

              <!-- SubMessage Template Attributes -->
              <div v-if="activeResourceDetails.resourceType === 'submessage_template'" class="attributes-section">
                <el-divider>模板配置</el-divider>
                <el-form-item>
                   <template #label>
                    <span>上下文参与长度 (Context Participation Length)</span>
                    <el-tooltip effect="dark" content="0代表参与所有上下文, 1代表仅参与最新一轮对话" placement="top">
                      <el-icon class="label-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </template>
                  <el-input-number v-model="form.attributes.context_participation_length" :min="0" :step="1" controls-position="right" style="width: 100%;" />
                </el-form-item>
                <el-form-item>
                  <template #label>
                    <span>默认折叠 (Is Collapsed)</span>
                    <el-tooltip effect="dark" content="在对话中注入时, 该模板内容是否默认折叠" placement="top">
                      <el-icon class="label-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </template>
                  <el-switch v-model="form.attributes.is_collapsed" />
                </el-form-item>
              </div>
            </template>

          </el-form>
          <div class="editor-footer">
            <el-button @click="resetForm">重置</el-button>
            <el-button v-if="activeResourceDetails.itemType === 'resource'" type="success" @click="openNewVersionDialog">另存为新版本</el-button>
            <el-button type="primary" @click="handleSaveChanges" :disabled="!isFormDirty">保存更改</el-button>
          </div>
        </div>

        <!-- Version History Panel -->
        <div v-if="activeResourceDetails.itemType === 'resource'" class="version-history-panel">
          <h5 class="version-history-title">版本历史</h5>
          <el-scrollbar>
            <el-timeline v-if="activeResourceDetails.versions && activeResourceDetails.versions.length > 0">
              <el-timeline-item
                v-for="version in activeResourceDetails.versions"
                :key="version.id"
                :timestamp="new Date(version.createdAt).toLocaleString()"
                placement="top"
              >
                <el-card class="version-card" shadow="hover" @click="loadVersionIntoEditor(version)">
                  <h4>{{ version.name }}</h4>
                  <p v-if="version.commitMessage" class="commit-message">{{ version.commitMessage }}</p>
                  <div class="version-actions">
                    <el-button
                      type="primary"
                      link
                      :disabled="activeResourceDetails.latest_version?.id === version.id"
                      @click.stop="handleSetActiveVersion(version.id)"
                    >
                      设为当前
                    </el-button>
                  </div>
                </el-card>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无历史版本" />
          </el-scrollbar>
        </div>
      </div>
    </el-main>

    <!-- Context Menu -->
    <el-dropdown
      ref="contextMenuRef"
      trigger="contextmenu"
      @command="handleCommand"
      popper-class="no-animation-popper"
    >
      <span :style="contextMenuPosition" />
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="newResource"><el-icon><DocumentAdd /></el-icon>新建资源</el-dropdown-item>
          <el-dropdown-item command="newFolder"><el-icon><FolderAdd /></el-icon>新建文件夹</el-dropdown-item>
          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" divided><el-icon><EditPen /></el-icon>重命名</el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item"><el-icon><Delete /></el-icon>删除</el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- Dialog for Rename and New Folder -->
    <ItemNameDialog
      v-model:visible="itemNameDialog.visible"
      :title="itemNameDialog.title"
      :initial-name="itemNameDialog.initialName"
      :item-type="itemNameDialog.itemType"
      @confirm="handleItemNameConfirm"
    />

    <!-- Dialog for New Resource -->
    <ResourceCreateDialog
      v-model:visible="resourceCreateDialog.visible"
      title="新建资源"
      :resource-types="creatableResourceTypes"
      @confirm="handleResourceCreateConfirm"
    />

    <!-- Dialog for New Version -->
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
import { ElMessage, ElMessageBox, ElTree, type FormInstance } from 'element-plus';
import type { AllowDropType, NodeDropType } from 'element-plus/es/components/tree/src/tree.type';
import type Node from 'element-plus/es/components/tree/src/model/node';
import { Folder, Document, DocumentAdd, FolderAdd, EditPen, Delete, Memo, QuestionFilled } from '@element-plus/icons-vue';

import { useResourceStore } from '@/stores/resourceStore';
import { useContextMenu } from '@/composables/useContextMenu';
import ItemNameDialog from '@/components/chat/dialogs/ItemNameDialog.vue';
import ResourceCreateDialog from './dialogs/ResourceCreateDialog.vue';
import type { Resource, ResourceReorderItem, ResourceWithVersions, ResourceType, ResourceVersion, ResourceVersionCreate, ResourceItemType } from '@/api/types';

// --- Local Type Definitions ---
interface SubMessageTemplateAttributes {
  context_participation_length: number;
  is_collapsed: boolean;
}

// --- Store ---
const resourceStore = useResourceStore();
const { isResourcesLoading, resources, resourceTree } = storeToRefs(resourceStore);

// --- Constants for Extensibility ---
const creatableResourceTypes: { value: ResourceType, label: string }[] = [
  { value: 'system_prompt', label: 'System Prompt' },
  { value: 'submessage_template', label: 'SubMessage 模板' },
];

const DEFAULT_SUBMESSAGE_ATTRIBUTES: SubMessageTemplateAttributes = {
  context_participation_length: 1, // 默认值已修改为 1
  is_collapsed: false,
};

// --- Refs and Reactive State ---
const treeRef = ref<InstanceType<typeof ElTree>>();
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

const itemNameDialog = reactive({
  visible: false,
  title: '',
  initialName: '',
  itemType: 'folder' as ResourceItemType,
});

const resourceCreateDialog = reactive({
  visible: false,
});

const newVersionDialog = reactive({
  visible: false,
  form: {
    name: '',
    commitMessage: '',
  },
});

// --- Context Menu ---
const contextMenuRef = ref();
const { contextMenuItem, contextMenuPosition, handleContextMenu } = useContextMenu<Resource>();

// --- Computed Properties ---
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
    return `内容 (${loadedVersionInEditor.value.name})`;
  }
  return '内容 (当前版本)';
});

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
    resetForm();
  }
});

// --- Methods ---
async function handleNodeClick(data: ResourceWithVersions) {
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
  } else {
    form.name = '';
    form.description = '';
    form.content = '';
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
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

// --- Tree Drag & Drop ---
const allowDrop = (draggingNode: Node, dropNode: Node, dropType: AllowDropType) => {
  return !((dropNode.data as Resource).itemType === 'resource' && dropType  === 'inner');
};

const handleNodeDrop = async (draggingNode: Node, dropNode: Node, dropType: NodeDropType) => {
  let parentId: string | null = null;
  let siblings: Node[] = [];

  if (dropType === 'inner') {
    parentId = (dropNode.data as Resource).id;
    siblings = dropNode.childNodes || [];
  } else {
    parentId = (dropNode.data as Resource).parentId;
    siblings = dropNode.parent?.childNodes || treeRef.value?.root.childNodes || [];
  }

  const updates: ResourceReorderItem[] = siblings.map((node, index) => ({
    id: (node.data as Resource).id,
    parentId,
    sortOrder: index,
  }));

  if (updates.length > 0) {
    await resourceStore.reorderResourceItems(updates);
  }
};

// --- Context Menu & Dialog Logic ---
const openContextMenu = (event: MouseEvent, data: Resource | null) => {
  handleContextMenu(event, data, contextMenuRef);
};

const handleCommand = (command: 'newResource' | 'newFolder' | 'rename' | 'delete') => {
  const item = contextMenuItem.value;
  switch (command) {
    case 'newResource':
      resourceCreateDialog.visible = true;
      break;
    case 'newFolder':
      itemNameDialog.title = '新建文件夹';
      itemNameDialog.initialName = '新的文件夹';
      itemNameDialog.itemType = 'folder';
      itemNameDialog.visible = true;
      break;
    case 'rename':
      if (item) {
        itemNameDialog.title = '重命名';
        itemNameDialog.initialName = item.name;
        itemNameDialog.itemType = item.itemType;
        itemNameDialog.visible = true;
      }
      break;
    case 'delete':
      if (item) handleDelete(item);
      break;
  }
};

async function handleResourceCreateConfirm(payload: { name: string; resourceType: ResourceType }) {
  const { name, resourceType } = payload;
  const parentId = contextMenuItem.value?.itemType === 'folder'
    ? contextMenuItem.value.id
    : contextMenuItem.value?.parentId ?? null;
  const sortOrder = resourceStore.resources.filter(r => r.parentId === parentId).length;

  let initial_attributes: Partial<SubMessageTemplateAttributes> | undefined;
  if (resourceType === 'submessage_template') {
      initial_attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
  }

  await resourceStore.addResourceItem({
    name,
    itemType: 'resource',
    resourceType,
    parentId,
    sortOrder,
    initial_content: '',
    initial_attributes,
  });
}

async function handleItemNameConfirm(name: string) {
  if (itemNameDialog.title === '重命名' && contextMenuItem.value) {
    await resourceStore.updateResourceItem(contextMenuItem.value.id, { name });
  } else if (itemNameDialog.itemType === 'folder') {
    const parentId = contextMenuItem.value?.itemType === 'folder'
      ? contextMenuItem.value.id
      : contextMenuItem.value?.parentId ?? null;
    const sortOrder = resourceStore.resources.filter(r => r.parentId === parentId).length;
    await resourceStore.addResourceItem({ name, itemType: 'folder', parentId, sortOrder });
  }
}

const handleDelete = async (item: Resource) => {
  try {
    await ElMessageBox.confirm(`确定要删除 "${item.name}" 吗？此操作不可恢复。`, '警告', {
      confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning'
    });
    await resourceStore.deleteResourceItem(item.id);
    if (selectedResourceId.value === item.id) {
      selectedResourceId.value = undefined;
    }
    ElMessage.success('删除成功');
  } catch { /* User canceled */ }
};

// --- Versioning Methods ---
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
  height: calc(100vh - 200px);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
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
}
.panel-header h4 {
  margin: 0;
  font-size: 16px;
}
.tree-scrollbar {
  flex-grow: 1;
  padding: 8px;
}
.loading-container {
  padding: 10px;
}
.resource-tree {
  background-color: transparent;
}
.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  overflow: hidden;
}
.node-icon {
  margin-right: 8px;
}
.node-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.resource-editor-panel {
  padding: 0;
  display: flex;
}
.editor-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.editor-container {
  display: flex;
  width: 100%;
  height: 100%;
}
.editor-content {
  flex: 1;
  padding: 20px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.editor-form {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  min-height: 0;
}
.content-form-item {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
:deep(.content-form-item .el-form-item__content) {
  flex-grow: 1;
}
:deep(.el-textarea) {
  height: 100%;
}
:deep(.el-textarea__inner) {
  height: 100% !important;
  resize: none;
}
.editor-footer {
  flex-shrink: 0;
  text-align: right;
  padding-top: 20px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.delete-item {
  color: var(--el-color-danger);
}

.attributes-section {
  margin-top: -10px;
}
.label-icon {
  margin-left: 8px;
  color: #909399;
  cursor: help;
}

/* Version History Panel Styles */
.version-history-panel {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color);
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft);
}
.version-history-title {
  margin: 0;
  padding: 16px;
  font-size: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.version-history-panel .el-scrollbar {
  flex-grow: 1;
  padding: 16px;
}
.version-card {
  border: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
}
.version-card h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
}
.commit-message {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 10px 0;
  white-space: pre-wrap;
  word-break: break-all;
}
.version-actions {
  text-align: right;
  margin-top: 8px;
}
.version-actions .el-button {
  padding: 0;
}
</style>
