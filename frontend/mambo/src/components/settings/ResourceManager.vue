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
            <el-form-item
              v-if="activeResourceDetails.itemType === 'resource'"
              :label="contentEditorLabel"
              prop="content"
              class="content-form-item"
            >
              <el-input v-model="form.content" type="textarea" placeholder="在此处输入内容..." />
            </el-form-item>
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

    <!-- Dialog for Name Input (Rename/New) -->
    <ItemNameDialog
      v-model:visible="itemNameDialog.visible"
      :title="itemNameDialog.title"
      :initial-name="itemNameDialog.initialName"
      :item-type="itemNameDialog.itemType"
      :resource-types="creatableResourceTypes"
      @confirm="handleConfirmItemName"
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
import { Folder, Document, DocumentAdd, FolderAdd, EditPen, Delete } from '@element-plus/icons-vue';

import { useResourceStore } from '@/stores/resourceStore';
import { useContextMenu } from '@/composables/useContextMenu';
import ItemNameDialog from '@/components/chat/dialogs/ItemNameDialog.vue';
import type { Resource, ResourceReorderItem, ResourceWithVersions, ResourceType, ResourceVersion, ResourceVersionCreate } from '@/api/types';

// --- Store ---
const resourceStore = useResourceStore();
const { isResourcesLoading, resources, resourceTree } = storeToRefs(resourceStore);

// --- Constants for Extensibility ---
const creatableResourceTypes: { value: ResourceType, label: string }[] = [
  { value: 'system_prompt', label: 'System Prompt' },
];

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
});

const itemNameDialog = reactive({
  visible: false,
  title: '',
  initialName: '',
  itemType: 'folder' as 'folder' | 'resource',
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
  const originalContent = loadedVersionInEditor.value?.content ?? original.latest_version?.content ?? '';

  return (
    form.name !== original.name ||
    form.description !== (original.description || '') ||
    (original.itemType === 'resource' && form.content !== originalContent)
  );
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
  if (activeResourceDetails.value) {
    form.name = activeResourceDetails.value.name;
    form.description = activeResourceDetails.value.description || '';
    form.content = activeResourceDetails.value.latest_version?.content || '';
    loadedVersionInEditor.value = null;
  } else {
    form.name = '';
    form.description = '';
    form.content = '';
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

  if (resource.itemType === 'resource' && form.content !== (resource.latest_version?.content || '')) {
    await resourceStore.updateVersionContent(resource, form.content);
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
      itemNameDialog.title = '新建资源';
      itemNameDialog.initialName = '新的资源';
      itemNameDialog.itemType = 'resource';
      itemNameDialog.visible = true;
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
        itemNameDialog.itemType = item.itemType as 'folder' | 'resource';
        itemNameDialog.visible = true;
      }
      break;
    case 'delete':
      if (item) handleDelete(item);
      break;
  }
};

async function handleConfirmItemName(payload: string | { name: string; resourceType?: ResourceType }) {
  let name: string;
  let resourceType: ResourceType | undefined;

  if (typeof payload === 'string') {
    name = payload;
  } else {
    name = payload.name;
    resourceType = payload.resourceType;
  }

  const parentId = contextMenuItem.value?.itemType === 'folder'
    ? contextMenuItem.value.id
    : contextMenuItem.value?.parentId ?? null;
  const sortOrder = resourceStore.resources.filter(r => r.parentId === parentId).length;

  if (itemNameDialog.title === '重命名' && contextMenuItem.value) {
    await resourceStore.updateResourceItem(contextMenuItem.value.id, { name });
  } else if (itemNameDialog.itemType === 'folder') {
    await resourceStore.addResourceItem({ name, itemType: 'folder', parentId, sortOrder });
  } else if (itemNameDialog.itemType === 'resource') {
    await resourceStore.addResourceItem({
      name,
      itemType: 'resource',
      resourceType,
      parentId,
      sortOrder,
    });
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
