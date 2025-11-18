<template>
  <el-container class="resource-manager-container">
    <!-- Left Panel: Resource Tree -->
    <el-aside width="300px" class="resource-tree-panel" @contextmenu.prevent="openContextMenu($event, null)">
      <div class="panel-header">
        <h4>资源列表</h4>
        <!-- Add buttons for root-level creation if needed -->
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

    <!-- Right Panel: Editor -->
    <el-main class="resource-editor-panel">
      <div v-if="!selectedResource" class="editor-placeholder">
        <el-empty description="从左侧选择一个资源进行编辑" />
      </div>
      <div v-else class="editor-content">
        <el-form :model="form" label-position="top" ref="formRef">
          <el-form-item label="名称" prop="name">
            <el-input v-model="form.name" />
          </el-form-item>
          <el-form-item label="描述" prop="description">
            <el-input v-model="form.description" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item
            v-if="selectedResource.itemType === 'resource'"
            label="内容 (System Prompt)"
            prop="content"
          >
            <el-input v-model="form.content" type="textarea" :rows="15" placeholder="在此处输入System Prompt..." />
          </el-form-item>
        </el-form>
        <div class="editor-footer">
          <el-button @click="resetForm">重置</el-button>
          <el-button type="primary" @click="handleSaveChanges" :disabled="!isFormDirty">保存更改</el-button>
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
          <el-dropdown-item command="newPrompt"><el-icon><DocumentAdd /></el-icon>新建提示</el-dropdown-item>
          <el-dropdown-item command="newFolder"><el-icon><FolderAdd /></el-icon>新建文件夹</el-dropdown-item>
          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" divided><el-icon><EditPen /></el-icon>重命名</el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item"><el-icon><Delete /></el-icon>删除</el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- Dialog for Name Input -->
    <ItemNameDialog
      v-model:visible="itemNameDialog.visible"
      :title="itemNameDialog.title"
      :initial-name="itemNameDialog.initialName"
      @confirm="handleConfirmItemName"
    />

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
import type { Resource, ResourceReorderItem } from '@/api/types';

// --- Store ---
const resourceStore = useResourceStore();
const { isResourcesLoading, resourceTree } = storeToRefs(resourceStore);

// --- Refs and Reactive State ---
const treeRef = ref<InstanceType<typeof ElTree>>();
const formRef = ref<FormInstance>();
const selectedResource = ref<Resource | null>(null);

const form = reactive({
  name: '',
  description: '',
  content: '',
});

const itemNameDialog = reactive({
  visible: false,
  title: '',
  initialName: '',
  action: 'rename' as 'rename' | 'newPrompt' | 'newFolder',
});

// --- Context Menu ---
const contextMenuRef = ref();
const { contextMenuItem, contextMenuPosition, handleContextMenu } = useContextMenu<Resource>();

// --- Computed Properties ---
const isFormDirty = computed(() => {
  if (!selectedResource.value) return false;
  const original = selectedResource.value;
  return (
    form.name !== original.name ||
    form.description !== (original.description || '') ||
    (original.itemType === 'resource' && form.content !== (original.latest_version?.content || ''))
  );
});

// --- Lifecycle ---
onMounted(() => {
  resourceStore.fetchResources();
});

// --- Watchers ---
watch(selectedResource, (newSelection) => {
  if (newSelection) {
    form.name = newSelection.name;
    form.description = newSelection.description || '';
    form.content = newSelection.latest_version?.content || '';
  } else {
    resetForm();
  }
});

// --- Methods ---
function handleNodeClick(data: Resource) {
  selectedResource.value = data;
}

function resetForm() {
  if (selectedResource.value) {
    handleNodeClick(selectedResource.value);
  } else {
    form.name = '';
    form.description = '';
    form.content = '';
  }
}

async function handleSaveChanges() {
  if (!selectedResource.value || !isFormDirty.value) return;

  const resourceId = selectedResource.value.id;
  const original = selectedResource.value;

  // Update basic info if changed
  if (form.name !== original.name || form.description !== (original.description || '')) {
    await resourceStore.updateResourceItem(resourceId, {
      name: form.name,
      description: form.description,
    });
  }

  // Update content if changed
  if (original.itemType === 'resource' && form.content !== (original.latest_version?.content || '')) {
    await resourceStore.updateVersionContent(original, form.content);
  }

  ElMessage.success('保存成功');
  // The store update will reactively update the selectedResource, which will reset the form's dirty state.
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

const handleCommand = (command: 'newPrompt' | 'newFolder' | 'rename' | 'delete') => {
  const item = contextMenuItem.value;
  const parentId = item?.itemType === 'folder' ? item.id : item?.parentId ?? null;

  switch (command) {
    case 'newPrompt':
      itemNameDialog.title = '新建提示';
      itemNameDialog.initialName = '新的 System Prompt';
      itemNameDialog.action = 'newPrompt';
      itemNameDialog.visible = true;
      break;
    case 'newFolder':
      itemNameDialog.title = '新建文件夹';
      itemNameDialog.initialName = '新的文件夹';
      itemNameDialog.action = 'newFolder';
      itemNameDialog.visible = true;
      break;
    case 'rename':
      if (item) {
        itemNameDialog.title = '重命名';
        itemNameDialog.initialName = item.name;
        itemNameDialog.action = 'rename';
        itemNameDialog.visible = true;
      }
      break;
    case 'delete':
      if (item) handleDelete(item);
      break;
  }
};

const handleConfirmItemName = async (name: string) => {
  if (itemNameDialog.action === 'rename' && contextMenuItem.value) {
    await resourceStore.updateResourceItem(contextMenuItem.value.id, { name });
  } else {
    const parentId = contextMenuItem.value?.itemType === 'folder'
      ? contextMenuItem.value.id
      : contextMenuItem.value?.parentId ?? null;
    const sortOrder = resourceStore.resources.filter(r => r.parentId === parentId).length;

    if (itemNameDialog.action === 'newFolder') {
      await resourceStore.addResourceItem({ name, itemType: 'folder', parentId, sortOrder });
    } else if (itemNameDialog.action === 'newPrompt') {
      await resourceStore.addResourceItem({
        name,
        itemType: 'resource',
        resourceType: 'system_prompt',
        initial_content: '',
        parentId,
        sortOrder,
      });
    }
  }
};

const handleDelete = async (item: Resource) => {
  try {
    await ElMessageBox.confirm(`确定要删除 "${item.name}" 吗？此操作不可恢复。`, '警告', {
      confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning'
    });
    await resourceStore.deleteResourceItem(item.id);
    if (selectedResource.value?.id === item.id) {
      selectedResource.value = null;
    }
    ElMessage.success('删除成功');
  } catch { /* User canceled */ }
};
</script>

<style scoped>
.resource-manager-container {
  height: calc(100vh - 200px); /* Adjust based on parent layout */
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
  flex-direction: column;
}
.editor-placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.editor-content {
  padding: 20px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}
.el-form {
  flex-grow: 1;
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
</style>
