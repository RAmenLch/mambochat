<!-- frontend/mambo/src/components/chat/ChatAgentSettingsDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    :title="$t('chat.settings.title', '会话设置')"
    direction="rtl"
    size="500px"
    @update:model-value="handleUpdateModelValue"
    @close="handleDrawerClose"
  >
    <div class="drawer-content">
      <!-- 会话自身的可编辑设置 -->
      <el-form v-if="chatData" :model="form" label-position="top">
        <el-form-item :label="$t('chat.settings.name', '会话名称')">
          <el-input v-model.trim="form.name" :placeholder="$t('chat.settings.namePlaceholder', '请输入会话名称')" />
        </el-form-item>
        <el-form-item :label="$t('chat.settings.bindAgent', '绑定的 Agent')">
          <el-select v-model="form.agentId" style="width: 100%">
            <el-option
              v-for="agent in agentOptions"
              :key="agent.value"
              :label="agent.label"
              :value="agent.value"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <el-divider border-style="dashed">
        <span class="preview-divider-title">{{ $t('chat.settings.agentInfoPreview', 'Agent 配置预览 (只读)') }}</span>
      </el-divider>

      <!-- Agent 详细配置预览区 -->
      <el-scrollbar class="agent-preview-scrollbar" v-if="selectedAgent">
        <div class="agent-preview-container">

          <!-- 1. 基本信息 -->
          <div class="preview-section">
            <div class="agent-header">
              <el-avatar
                :size="48"
                :src="selectedAgent.agentAvatarUrl || ''"
                :icon="User"
                class="agent-avatar"
              />
              <div class="agent-title-info">
                <div class="agent-name-row">
                  <!-- 增加点击事件和可点击样式 -->
                  <span
                    class="agent-name clickable-agent"
                    @click="openAgentSettings(selectedAgent.id)"
                    :title="$t('common.action.edit', '点击前往编辑')"
                  >
                    {{ selectedAgent.name }}
                  </span>
                  <el-tag size="small" type="info" effect="plain">{{ selectedAgent.AgentType }}</el-tag>
                </div>
                <div class="agent-desc" :title="selectedAgent.description || ''">
                  {{ selectedAgent.description || $t('common.none', '暂无描述') }}
                </div>
              </div>
            </div>
          </div>

          <!-- 2. 模型配置 -->
          <div class="preview-section">
            <div class="section-title"><el-icon><Cpu /></el-icon> {{ $t('agent.modelConfig', '模型配置') }}</div>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">{{ $t('agent.bindModel', '绑定模型') }}:</span>
                <span class="info-value">{{ displayModelName }}</span>
              </div>
              <div class="info-item" v-if="selectedAgent.modelParameters?.max_context_messages !== undefined">
                <span class="info-label">{{ $t('agent.contextMessages', '上下文消息数') }}:</span>
                <span class="info-value">{{ selectedAgent.modelParameters.max_context_messages }}</span>
              </div>
              <div class="info-item" v-if="selectedAgent.modelParameters?.stream !== undefined">
                <span class="info-label">{{ $t('agent.streamOutput', '流式输出') }}:</span>
                <span class="info-value">{{ selectedAgent.modelParameters.stream ? '开启' : '关闭' }}</span>
              </div>
              <div class="info-item" v-if="selectedAgent.modelParameters?.temperature !== undefined">
                <span class="info-label">Temperature:</span>
                <span class="info-value">{{ selectedAgent.modelParameters.temperature }}</span>
              </div>
            </div>
          </div>

          <!-- 3. 系统设定 -->
          <div class="preview-section">
            <div class="section-title"><el-icon><Document /></el-icon> {{ $t('agent.systemPrompt', '系统提示词') }}</div>
            <div class="prompt-box">
              {{ selectedAgent.systemPrompt || $t('common.none', '无') }}
            </div>
          </div>

          <!-- 4. 扩展能力 -->
          <div class="preview-section ext-section">
            <div class="section-title"><el-icon><MagicStick /></el-icon> {{ $t('agent.settingsAndResources', '设定与能力') }}</div>

            <!-- 扩展能力: 挂载资源 -->
            <div class="ext-item">
              <div class="ext-label">{{ $t('agent.mountedResources', '挂载资源') }}:</div>
              <div class="ext-tags" v-if="previewResources.length > 0">
                <!-- [修改] 使用 MountedResourceTags 替代手写的 el-tag，开启 color-by-type 和 readonly -->
                <MountedResourceTags :model-value="previewResources" color-by-type readonly />
              </div>
              <div class="ext-empty" v-else>{{ $t('common.none', '无') }}</div>
            </div>

            <!-- MCP 工具 -->
            <div class="ext-item">
              <div class="ext-label">{{ $t('agent.enableMcp', 'MCP 工具') }}:</div>
              <div class="ext-tags" v-if="displayMcpList.length > 0">
                <el-tag v-for="mcp in displayMcpList" :key="mcp.id" size="small" type="info" effect="light">
                  <el-icon><Connection /></el-icon> {{ mcp.name }}
                </el-tag>
              </div>
              <div class="ext-empty" v-else>{{ $t('common.none', '无') }}</div>
            </div>

            <!-- 子 Agent -->
            <div class="ext-item">
              <div class="ext-label">{{ $t('agent.subAgents', '子 Agent') }}:</div>
              <div class="ext-tags" v-if="displaySubAgents.length > 0">
                <!-- 增加点击事件和可点击样式，增加头像显示 -->
                <el-tag
                  v-for="sub in displaySubAgents"
                  :key="sub.id"
                  size="small"
                  type="primary"
                  effect="light"
                  class="clickable-tag custom-agent-tag"
                  @click="openAgentSettings(sub.id)"
                  :title="$t('common.action.edit', '点击前往编辑')"
                >
                  <div class="tag-inner">
                    <el-avatar v-if="sub.avatar" :size="14" :src="sub.avatar" class="tag-avatar" />
                    <el-icon v-else><User /></el-icon>
                    <span>{{ sub.name }}</span>
                  </div>
                </el-tag>
              </div>
              <div class="ext-empty" v-else>{{ $t('common.none', '无') }}</div>
            </div>
          </div>

        </div>
      </el-scrollbar>
      <div v-else class="empty-agent-preview">
        <el-empty :description="$t('common.rule.selectRequired', '请选择 Agent')" :image-size="60" />
      </div>

    </div>
    <template #footer>
      <div style="flex: auto">
        <el-button @click="emit('update:visible', false)">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="handleSaveSettings">{{ $t('common.action.save') }}</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { reactive, watch, computed, ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { User, Cpu, Document, MagicStick, Collection, Connection } from '@element-plus/icons-vue';

import { useAgentStore } from '@/stores/agentStore';
import { useProviderStore } from '@/stores/providerStore';
import { useMcpStore } from '@/stores/mcpStore';
import { getResourceDetails } from '@/api/resourceService';
import type { Chat, ChatUpdate, Resource } from '@/api/types'; // [修改] 引入 Resource 类型
import MountedResourceTags from '@/components/common/MountedResourceTags.vue'; // [新增] 引入组件

const props = defineProps<{
  visible: boolean;
  chatData: Chat | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'close'): void;
  (e: 'save', settings: ChatUpdate): void;
}>();

const { t } = useI18n();
const router = useRouter();
const agentStore = useAgentStore();
const providerStore = useProviderStore();
const mcpStore = useMcpStore();

const form = reactive({
  name: '',
  agentId: '' as string | null,
});

// [修改] 异步获取的资源列表缓存，类型改为完整的 Resource[]
const previewResources = ref<Resource[]>([]);

// --- Computed ---

const agentOptions = computed(() => {
  return agentStore.allAgents
    .filter(a => a.itemType === 'agent')
    .map(a => ({
      label: a.name,
      value: a.id
    }));
});

const selectedAgent = computed(() => {
  if (!form.agentId) return null;
  return agentStore.allAgents.find(a => a.id === form.agentId) || null;
});

const displayModelName = computed(() => {
  if (!selectedAgent.value?.aiModelId) return t('common.status.unspecified', '未指定');
  const model = providerStore.allModels.find(m => m.id === selectedAgent.value!.aiModelId);
  return model ? model.name : t('common.status.unknownModel', '未知模型');
});

const displayMcpList = computed(() => {
  const mcpIds = selectedAgent.value?.enabledMcpIds || [];
  return mcpIds.map(id => {
    const mcp = mcpStore.activeUserMcpServices.find(m => m.id === id);
    return mcp ? { id, name: mcp.name } : { id, name: 'Unknown MCP' };
  });
});

const displaySubAgents = computed(() => {
  const subIds = selectedAgent.value?.subAgents || [];
  return subIds.map(id => {
    const agent = agentStore.allAgents.find(a => a.id === id);
    return agent ? { id, name: agent.name, avatar: agent.agentAvatarUrl } : { id, name: 'Unknown Agent', avatar: null };
  });
});

// --- Lifecycle ---
// 组件挂载时确保 Agent 列表已加载
onMounted(() => {
  if (agentStore.allAgents.length === 0) {
    agentStore.fetchAllAgents();
  }
});

// --- Watchers ---

watch(() => props.chatData, (newData) => {
  if (newData) {
    form.name = newData.name;
    form.agentId = newData.agentId || null;
  }
}, { immediate: true, deep: true });

// 监听选中的 Agent 变化，异步拉取资源名称
watch(() => selectedAgent.value?.resourcePromptList, async (resourceIds) => {
  if (!resourceIds || resourceIds.length === 0) {
    previewResources.value = [];
    return;
  }
  try {
    const promises = resourceIds.map(id => getResourceDetails(id).catch(() => null));
    const results = await Promise.all(promises);
    // [修改] 直接保留完整的 Resource 对象，不再 map 截断属性
    previewResources.value = results.filter(r => r !== null) as Resource[];
  } catch (error) {
    console.error('Failed to load preview resources:', error);
    previewResources.value = [];
  }
}, { immediate: true });

// --- Methods ---

const handleUpdateModelValue = (val: boolean) => {
  emit('update:visible', val);
};

const handleDrawerClose = () => {
  emit('close');
};

const handleSaveSettings = () => {
  if (!props.chatData) return;
  if (!form.name?.trim()) {
    ElMessage.warning(t('chat.settings.namePlaceholder'));
    return;
  }
  if (!form.agentId) {
    ElMessage.warning(t('common.rule.selectRequired', '请选择 Agent'));
    return;
  }

  emit('save', {
    name: form.name,
    agentId: form.agentId,
  });
};

// 打开 Agent 设置新标签页
const openAgentSettings = (agentId: string) => {
  const routeUrl = router.resolve({
    path: '/settings',
    query: { tab: 'agentManager', agentId }
  });
  window.open(routeUrl.href, '_blank');
};
</script>

<style scoped>
.drawer-content {
  padding: 0 20px;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.preview-divider-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.agent-preview-scrollbar {
  flex-grow: 1;
  margin: 0 -20px;
  padding: 0 20px;
}

.agent-preview-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 20px;
}

.preview-section {
  background-color: var(--color-background-soft);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 1. 基本信息样式 */
.agent-header {
  display: flex;
  align-items: center;
  gap: 16px;
}
.agent-avatar {
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.agent-title-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}
.agent-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-name {
  font-size: 16px;
  font-weight: bold;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Agent 名称可点击样式 */
.clickable-agent {
  cursor: pointer;
  color: var(--el-color-primary);
  transition: opacity 0.3s, text-decoration 0.3s;
}
.clickable-agent:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.agent-desc {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 2. 模型配置样式 */
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.info-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.info-value {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

/* 3. 系统提示词样式 */
.prompt-box {
  font-size: 13px;
  color: var(--el-text-color-regular);
  background-color: var(--el-bg-color);
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.5;
}

/* 4. 扩展能力样式 */
.ext-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ext-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ext-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}
.ext-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 子 Agent 标签可点击样式 */
.clickable-tag {
  cursor: pointer;
  transition: opacity 0.3s;
}
.clickable-tag:hover {
  opacity: 0.8;
}

.custom-agent-tag {
  height: 24px;
  padding: 0 8px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
}

.tag-inner {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tag-avatar {
  background-color: transparent;
}

.ext-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  font-style: italic;
}

.empty-agent-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
}
</style>
