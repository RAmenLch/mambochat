<template>
  <div class="chat-list-container">
    <!-- 简洁的列表头部 -->
    <div class="chat-list-header" @contextmenu.prevent="handleContextMenu($event, null)">
      <h4>会话列表</h4>
    </div>

    <!-- 会话列表树 -->
    <el-scrollbar
      class="chat-list-scrollbar"
      @contextmenu.prevent="handleContextMenu($event, null)"
    >
      <div v-if="isChatListLoading" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>
      <el-tree
        v-else-if="treeData.length > 0"
        ref="treeRef"
        :data="treeData"
        node-key="id"
        :current-node-key="currentChatId"
        highlight-current
        default-expand-all
        :expand-on-click-node="false"
        draggable
        :allow-drop="allowDrop"
        @node-click="handleNodeClick"
        @node-drop="handleNodeDrop"
        @node-contextmenu="handleContextMenu"
        class="chat-tree"
        :props="{ label: 'name', children: 'children' }"
      >
        <template #default="{ node, data }">
          <span class="custom-tree-node">
            <el-icon class="node-icon">
              <Folder v-if="data.itemType === 'folder'" />
              <ChatDotRound v-else />
            </el-icon>
            <el-tooltip
              :content="node.label"
              placement="top"
              :show-after="500"
              effect="dark"
              :disabled="!node.label || node.label.length < 15"
            >
              <span class="node-label">{{ node.label }}</span>
            </el-tooltip>
          </span>
        </template>
      </el-tree>
      <el-empty v-else description="右键新建会话" />
    </el-scrollbar>

    <el-divider />

    <!-- 底部操作区 -->
    <div class="footer">
      <el-button :icon="Setting" circle @click="goToSettings" />
    </div>

    <!-- 全局右键上下文菜单 -->
    <el-dropdown
      ref="contextMenuRef"
      trigger="manual"
      @command="handleCommand"
      :class="{ 'context-menu-hidden': !isContextMenuVisible }"
    >
      <!-- 这个空的span是必须的,作为dropdown的定位锚点 -->
      <span :style="contextMenuPosition" />
      <template #dropdown>
        <el-dropdown-menu>
          <!-- 针对文件夹的菜单项 -->
          <template v-if="contextMenuItem?.itemType === 'folder'">
            <el-dropdown-item command="newChatInFolder">
              <el-icon><Plus /></el-icon>新建会话
            </el-dropdown-item>
            <el-dropdown-item command="newFolderInFolder">
              <el-icon><FolderAdd /></el-icon>新建文件夹
            </el-dropdown-item>
          </template>

          <!-- 针对空白区域的菜单项 -->
          <template v-if="!contextMenuItem">
            <el-dropdown-item command="newRootChat">
              <el-icon><Plus /></el-icon>新建会话
            </el-dropdown-item>
            <el-dropdown-item command="newRootFolder">
              <el-icon><FolderAdd /></el-icon>新建文件夹
            </el-dropdown-item>
          </template>

          <!-- 通用菜单项 (当有选中项时) -->
          <template v-if="contextMenuItem">
            <el-dropdown-item command="rename" :divided="contextMenuItem.itemType === 'folder'">
              <el-icon><EditPen /></el-icon>重命名
            </el-dropdown-item>
            <el-dropdown-item v-if="contextMenuItem.itemType === 'chat'" command="duplicate">
              <el-icon><CopyDocument /></el-icon>复制会话
            </el-dropdown-item>
            <el-dropdown-item command="delete" class="delete-item">
              <el-icon><Delete /></el-icon>删除
            </el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 新建/重命名 弹窗 -->
    <el-dialog v-model="itemDialogVisible" :title="dialogTitle" width="400px">
       <el-input v-model="itemNameInput" placeholder="请输入名称" @keyup.enter="handleConfirmItemName" />
      <template #footer>
        <el-button @click="itemDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirmItemName">确认</el-button>
      </template>
    </el-dialog>

    <!-- 新建会话弹窗 -->
    <el-dialog v-model="newChatDialogVisible" title="新建会话" width="400px">
      <el-form ref="formRef" :model="newChatForm" :rules="formRules" label-width="80px">
        <el-form-item label="会话名称" prop="name">
          <el-input v-model="newChatForm.name" placeholder="请输入会话名称" />
        </el-form-item>
        <el-form-item label="选择模型" prop="modelId">
          <el-select v-model="newChatForm.modelId" placeholder="请选择一个AI模型" style="width: 100%;">
            <el-option-group v-for="group in groupedModels" :key="group.label" :label="group.label">
              <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
            </el-option-group>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newChatDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateChat">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, nextTick } from 'vue';
import { useChatStore } from '@/stores/chatStore';
import { useProviderStore } from '@/stores/providerStore';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox, ElTree } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import type { NodeDropType } from 'element-plus/es/components/tree/src/tree.type';
import type { Chat, ChatReorderItem } from '@/api/types';
import { Plus, Delete, Setting, Folder, ChatDotRound, FolderAdd, EditPen, CopyDocument } from '@element-plus/icons-vue';

// -- Stores & Router --
const chatStore = useChatStore();
const providerStore = useProviderStore();
const router = useRouter();

const { chatList, currentChatId, isChatListLoading } = storeToRefs(chatStore);
const { providers, globalSettings } = storeToRefs(providerStore);
const treeRef = ref<InstanceType<typeof ElTree>>();

// -- Data Transformation (Flat to Tree) --
const treeData = computed(() => {
  const list = JSON.parse(JSON.stringify(chatList.value)) as (Chat & { children?: Chat[] })[];
  const map: Record<string, Chat & { children?: Chat[] }> = {};
  list.forEach(item => (map[item.id] = item));

  const tree: (Chat & { children?: Chat[] })[] = [];
  list.forEach(item => {
    if (item.parentId && map[item.parentId]) {
      (map[item.parentId].children = map[item.parentId].children || []).push(item);
    } else {
      tree.push(item);
    }
  });

  const sortNodes = (nodes: (Chat & { children?: Chat[] })[]) => {
    nodes.sort((a, b) => a.sortOrder - b.sortOrder);
    nodes.forEach(node => {
      if (node.children) {
        sortNodes(node.children);
      }
    });
  };
  sortNodes(tree);

  return tree;
});

// -- Lifecycle --
onMounted(async () => {
  await providerStore.fetchProviders();
  await chatStore.fetchChatList();

  if (chatList.value.length > 0) {
    let lastOpenedChat: Chat | null = null;
    for (const chat of chatList.value) {
      if (chat.itemType === 'chat' && chat.lastOpenedAt) {
        if (!lastOpenedChat || new Date(chat.lastOpenedAt) > new Date(lastOpenedChat.lastOpenedAt!)) {
          lastOpenedChat = chat;
        }
      }
    }
    if (lastOpenedChat) {
      await handleSelectChat(lastOpenedChat.id);
    }
  }
});

// -- Tree Operations --
const handleNodeClick = async (data: Chat) => {
  if (data.itemType === 'chat') {
    await handleSelectChat(data.id);
  }
};

const handleSelectChat = async (chatId: string) => {
  await chatStore.selectChat(chatId);
  if (chatStore.currentChat) {
    router.push(`/chat/${chatId}`);
  }
};

/**
 * 选中指定ID的会话并滚动到视图中
 * @param chatId 要滚动到的会话ID
 */
const scrollToChat = async (chatId: string) => {
  // 选中会话并导航
  await handleSelectChat(chatId);
  // 等待DOM更新，确保 'is-current' class 已应用
  await nextTick();

  if (treeRef.value) {
    const treeElement = treeRef.value.$el as HTMLElement;
    const currentNodeElement = treeElement.querySelector('.el-tree-node.is-current');
    if (currentNodeElement) {
      currentNodeElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
};

const allowDrop = (draggingNode: any, dropNode: any, type: NodeDropType) => {
  if (dropNode.data.itemType === 'chat' && type === 'inner') {
    return false;
  }
  return true;
};

const handleNodeDrop = async (draggingNode: any, dropNode: any, dropType: NodeDropType) => {
  const updates: ChatReorderItem[] = [];
  let parentId: string | null = null;
  let siblings: any[] = [];

  if (dropType === 'inner') {
    parentId = dropNode.data.id;
    siblings = dropNode.childNodes || [];
  } else {
    parentId = dropNode.data.parentId;
    siblings = dropNode.parent.childNodes || [];
  }

  siblings.forEach((node, index) => {
    updates.push({ id: node.data.id, parentId: parentId, sortOrder: index });
  });

  await chatStore.reorderChatItems(updates);
};

// -- Context Menu Logic --
const contextMenuRef = ref();
const contextMenuItem = ref<Chat | null>(null);
const isContextMenuVisible = ref(false);
const contextMenuPosition = reactive({
  position: 'fixed' as const,
  top: '0px',
  left: '0px',
});

// ======================= FINAL FIX (NO FLICKER) =======================
const handleContextMenu = (event: MouseEvent, data: Chat | null) => {
  event.preventDefault();

  if (!data && (event.target as HTMLElement).closest('.el-tree-node')) {
    return;
  }

  // 1. Immediately hide the menu to prevent visual flicker
  isContextMenuVisible.value = false;

  // 2. Update state for the new menu
  contextMenuItem.value = data;
  contextMenuPosition.left = `${event.clientX}px`;
  contextMenuPosition.top = `${event.clientY}px`;

  // 3. Wait for the DOM to update the anchor's position
  nextTick(() => {
    if (contextMenuRef.value) {
      // 4. Force popper to reset and recalculate position (happens invisibly)
      contextMenuRef.value.handleClose(); // Resets internal state
      contextMenuRef.value.handleOpen(); // Recalculates position

      // 5. Make the menu visible at the new, correct position
      isContextMenuVisible.value = true;
    }
  });
};
// ======================================================================

// -- Item Operations (triggered by Context Menu) --
const itemDialogVisible = ref(false);
const dialogTitle = ref('');
const itemNameInput = ref('');
const currentParentId = ref<string | null>(null);

const handleCommand = (command: string) => {
  const data = contextMenuItem.value;
  switch (command) {
    case 'rename':
      if (data) handleRename(data);
      break;
    case 'delete':
      if (data) handleDelete(data);
      break;
    case 'duplicate':
      if (data) handleDuplicateChat(data);
      break;
    case 'newChatInFolder':
      if (data) openNewChatDialog(data.id);
      break;
    case 'newFolderInFolder':
      if (data) handleNewFolder(data.id);
      break;
    case 'newRootChat':
      openNewChatDialog(null);
      break;
    case 'newRootFolder':
      handleNewFolder(null);
      break;
  }
};

const handleRename = (data: Chat) => {
  dialogTitle.value = '重命名';
  itemNameInput.value = data.name;
  itemDialogVisible.value = true;
};

const handleDelete = (data: Chat) => {
  ElMessageBox.confirm(`确定要删除 "${data.name}" 吗？此操作不可恢复。`, '警告', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    await chatStore.deleteItem(data.id);
    ElMessage.success('删除成功');
  }).catch(() => {});
};

const handleDuplicateChat = async (data: Chat) => {
  if (data.itemType !== 'chat') return;
  const newChat = await chatStore.duplicateChat(data.id);
  if (newChat) {
    ElMessage.success('复制成功');
    await scrollToChat(newChat.id);
  } else {
    ElMessage.error('复制失败');
  }
};

const handleNewFolder = (parentId: string | null) => {
  contextMenuItem.value = null; // 重置，因为这是新建操作
  currentParentId.value = parentId;
  dialogTitle.value = '新建文件夹';
  itemNameInput.value = '新的文件夹';
  itemDialogVisible.value = true;
};

const handleConfirmItemName = async () => {
  if (!itemNameInput.value.trim()) {
    ElMessage.warning('名称不能为空');
    return;
  }

  if (dialogTitle.value === '重命名' && contextMenuItem.value) { // Rename
    await chatStore.updateChatSettings(contextMenuItem.value.id, { name: itemNameInput.value });
  } else { // New Folder
    const parentId = currentParentId.value;
    const sortOrder = chatList.value.filter(item => item.parentId === parentId).length;
    await chatStore.createNewItem({
      name: itemNameInput.value,
      itemType: 'folder',
      parentId: parentId,
      sortOrder: sortOrder,
    });
    if (parentId && treeRef.value) {
      const parentNode = treeRef.value.getNode(parentId);
      if (parentNode) parentNode.expanded = true;
    }
  }
  itemDialogVisible.value = false;
  itemNameInput.value = ''; // 清空输入
  contextMenuItem.value = null;
};


// -- New Chat Dialog --
const newChatDialogVisible = ref(false);
const formRef = ref<FormInstance>();
const newChatForm = reactive({ name: '新的会话', modelId: '' });
const formRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入会话名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请选择一个模型', trigger: 'change' }],
});

const groupedModels = computed(() => providers.value.map(p => ({ label: p.name, options: p.models })));

const openNewChatDialog = (parentId: string | null) => {
  currentParentId.value = parentId;
  newChatForm.name = '新的会话';
  newChatForm.modelId = globalSettings.value.default_model_id || '';
  formRef.value?.clearValidate();
  newChatDialogVisible.value = true;
};

const handleCreateChat = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      const parentId = currentParentId.value;
      const sortOrder = chatList.value.filter(item => item.parentId === parentId).length;
      const newChat = await chatStore.createNewItem({
        name: newChatForm.name,
        aiModelId: newChatForm.modelId,
        itemType: 'chat',
        parentId: parentId,
        sortOrder: sortOrder,
      });
      if (newChat) {
        ElMessage.success('创建成功');
        newChatDialogVisible.value = false;
        if (parentId && treeRef.value) {
            const parentNode = treeRef.value.getNode(parentId);
            if (parentNode) parentNode.expanded = true;
        }
        await scrollToChat(newChat.id);
      } else {
        ElMessage.error('创建失败');
      }
    }
  });
};

// -- Navigation --
const goToSettings = () => router.push('/settings');
</script>

<style>


.chat-tree {
  background-color: transparent;
}
.chat-tree .el-tree-node__content {
  height: 40px;
  border-radius: 6px;
  margin: 0 4px 4px 4px;
}
.chat-tree .el-tree-node.is-current > .el-tree-node__content {
    background-color: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-7);
}
.chat-tree .el-tree-node__content:hover {
    background-color: var(--color-background-mute);
}
</style>

<style scoped>
.context-menu-hidden {
  visibility: hidden;
}

.chat-list-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.chat-list-header {
  flex-shrink: 0;
  padding: 16px 16px 8px 16px;
  cursor: default; /* 增加一个默认光标，提升体验 */
}

/* ... 其余 scoped 样式保持不变 ... */
.chat-list-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.el-divider {
  margin: 12px 0;
  flex-shrink: 0;
}

.chat-list-scrollbar {
  flex-grow: 1;
  padding: 0 12px;
}

.loading-container {
  padding: 0 10px;
}
.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  padding-right: 8px;
  overflow: hidden;
  width: 100%;
  height: 100%;
}
.node-icon {
  margin-right: 8px;
  font-size: 16px;
}
.node-label {
  flex-grow: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  margin-right: 8px;
}

.delete-item {
  color: var(--el-color-danger);
}
.footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0 12px;
}
</style>
