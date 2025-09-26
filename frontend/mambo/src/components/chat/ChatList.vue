<template>
  <div class="chat-list-container">
    <!-- 顶部操作区 -->
    <div class="header">
      <el-button type="primary" :icon="Plus" @click="openNewChatDialog" class="new-chat-btn">
        新建会话
      </el-button>
    </div>

    <el-divider />

    <!-- 会话列表 -->
    <el-scrollbar class="chat-list-scrollbar">
      <div v-if="isChatListLoading" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>
      <div v-else-if="chatList.length > 0" class="list-wrapper">
        <div
          v-for="chat in chatList"
          :key="chat.id"
          class="chat-item"
          :class="{ 'is-active': chat.id === currentChatId }"
          @click="handleSelectChat(chat.id)"
        >
          <span class="chat-name">{{ chat.name }}</span>
        </div>
      </div>
      <el-empty v-else description="暂无会话" />
    </el-scrollbar>

    <el-divider />

    <!-- 底部操作区 -->
    <div class="footer">
       <el-button
        type="danger"
        :icon="Delete"
        @click="handleDeleteChat"
        :disabled="!currentChatId"
        plain
      >
        删除当前会话
      </el-button>
      <el-button :icon="Setting" circle @click="goToSettings" />
    </div>

    <!-- 新建会话弹窗 -->
    <el-dialog v-model="newChatDialogVisible" title="新建会话" width="400px">
      <el-form ref="formRef" :model="newChatForm" :rules="formRules" label-width="80px">
        <el-form-item label="会话名称" prop="name">
          <el-input v-model="newChatForm.name" placeholder="请输入会话名称" />
        </el-form-item>
        <el-form-item label="选择模型" prop="modelId">
          <el-select v-model="newChatForm.modelId" placeholder="请选择一个AI模型" style="width: 100%;">
            <el-option-group
              v-for="group in groupedModels"
              :key="group.label"
              :label="group.label"
            >
              <el-option
                v-for="item in group.options"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              />
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
import { ref, reactive, onMounted, computed } from 'vue';
import { useChatStore } from '@/stores/chatStore';
import { useProviderStore } from '@/stores/providerStore';
import { storeToRefs } from 'pinia';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus';
import { Plus, Delete, Setting } from '@element-plus/icons-vue';

// -- 初始化 Store 和 Router --
const chatStore = useChatStore();
const providerStore = useProviderStore();
const router = useRouter();
const route = useRoute();

// -- 从 Store 中获取响应式状态 --
const { chatList, currentChatId, isChatListLoading } = storeToRefs(chatStore);
const { providers } = storeToRefs(providerStore);

// -- 组件挂载时加载数据 --
onMounted(async () => {
  await chatStore.fetchChatList();
  await providerStore.fetchProviders(); // 为新建会话弹窗准备模型数据

  // 关键：处理直接通过 URL 访问特定会话的场景
  const chatIdFromUrl = route.params.chatId as string;
  if (chatIdFromUrl && chatList.value.some(c => c.id === chatIdFromUrl)) {
    await chatStore.selectChat(chatIdFromUrl);
  }
});

// -- 会话操作 --
const handleSelectChat = async (chatId: string) => {
  await chatStore.selectChat(chatId);
  // 同步 URL，方便用户刷新和分享
  router.push(`/chat/${chatId}`);
};

const handleDeleteChat = async () => {
  if (!currentChatId.value) return;
  try {
    await ElMessageBox.confirm('确定要删除当前会话吗？此操作不可恢复。', '警告', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
    await chatStore.deleteSelectedChat();
    ElMessage.success('删除成功');
    router.push('/chat'); // 删除后返回基础聊天页
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败');
    }
  }
};

// -- 新建会话弹窗逻辑 --
const newChatDialogVisible = ref(false);
const formRef = ref<FormInstance>();
const newChatForm = reactive({
  name: '新的会话',
  modelId: '',
});
const formRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入会话名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请选择一个模型', trigger: 'change' }],
});

// 将模型按服务商分组，用于优化 el-select 的显示
const groupedModels = computed(() => {
  return providers.value.map(provider => ({
    label: provider.name,
    options: provider.models,
  }));
});

const openNewChatDialog = () => {
  newChatForm.name = '新的会话';
  newChatForm.modelId = '';
  formRef.value?.clearValidate();
  newChatDialogVisible.value = true;
};

const handleCreateChat = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      const newChat = await chatStore.createNewChat({
        name: newChatForm.name,
        aiModelId: newChatForm.modelId,
      });
      if (newChat) {
        ElMessage.success('创建成功');
        newChatDialogVisible.value = false;
        router.push(`/chat/${newChat.id}`); // 创建成功后，自动跳转到新会话
      } else {
        ElMessage.error('创建失败');
      }
    }
  });
};

// -- 导航 --
const goToSettings = () => {
  router.push('/settings');
};
</script>

<style scoped>
.chat-list-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 12px;
  box-sizing: border-box;
}
.header {
  flex-shrink: 0;
}
.new-chat-btn {
  width: 100%;
}
.el-divider {
  margin: 12px 0;
  flex-shrink: 0;
}
.chat-list-scrollbar {
  flex-grow: 1; /* 占据所有剩余空间 */
}
.loading-container {
  padding: 0 10px;
}
.chat-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  margin-bottom: 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s ease;
  border: 1px solid transparent;
}
.chat-item:hover {
  background-color: var(--color-background-mute);
}
.chat-item.is-active {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
}
.chat-name {
  flex-grow: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
}
.footer {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
