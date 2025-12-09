<!-- frontend/mambo/src/components/settings/resource/ResourceMetaSidebar.vue -->
<template>
  <div class="meta-column">
    <el-scrollbar>
      <div class="meta-content-wrapper">
        <div class="meta-header">基本信息</div>
        <el-form-item label="名称" prop="name">
          <el-input
            :model-value="name"
            @update:model-value="$emit('update:name', $event)"
            placeholder="资源名称"
          />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            :model-value="description"
            @update:model-value="$emit('update:description', $event)"
            type="textarea"
            :rows="3"
            placeholder="资源描述"
            resize="none"
          />
        </el-form-item>

        <template v-if="resource.itemType === 'resource'">
          <el-divider class="meta-divider" />
          <div class="meta-header">版本信息</div>
          <el-form-item label="版本名称" prop="versionName">
            <el-input
              :model-value="versionName"
              @update:model-value="$emit('update:versionName', $event)"
              placeholder="例如：v1.1 优化逻辑"
            />
          </el-form-item>
          <el-form-item label="版本提交信息" prop="versionCommitMessage">
            <el-input
              :model-value="versionCommitMessage ?? ''"
              @update:model-value="$emit('update:versionCommitMessage', $event)"
              type="textarea"
              :rows="3"
              placeholder="描述此版本的具体变更内容"
              resize="none"
            />
          </el-form-item>
        </template>

        <template v-if="resource.itemType === 'resource' && resource.resourceType === 'submessage_template'">
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
              :model-value="attributes.context_participation_length"
              @update:model-value="$emit('update:attributes', { ...attributes, context_participation_length: $event ?? 0})"
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
            <el-switch
              :model-value="attributes.is_collapsed"
              @update:model-value="$emit('update:attributes', { ...attributes, is_collapsed: Boolean($event)})"
            />
          </el-form-item>
          <el-form-item>
            <template #label>
              <span>默认最小化</span>
              <el-tooltip effect="dark" content="在对话中注入时, 该模板内容是否默认最小化" placement="top">
                <el-icon class="label-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-switch
              :model-value="attributes.is_minimal"
              @update:model-value="$emit('update:attributes', { ...attributes, is_minimal: Boolean($event)})"
            />
          </el-form-item>
        </template>

        <el-divider class="meta-divider" />
        <div class="meta-info">
            <div class="info-row">
              <span>类型</span>
              <el-tag size="small" type="info">{{ displayResourceType }}</el-tag>
            </div>
            <div class="info-row">
              <span>ID</span>
              <span class="info-value" :title="resource.id">{{ resource.id.slice(0, 8) }}...</span>
            </div>
            <div class="info-row" v-if="resource.updatedAt">
              <span>更新时间</span>
              <span class="info-value">{{ new Date(resource.updatedAt).toLocaleDateString() }}</span>
            </div>
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { QuestionFilled } from '@element-plus/icons-vue';
import type { ResourceWithVersions } from '@/api/types';

// --- Local Type Definitions ---
interface SubMessageTemplateAttributes {
  context_participation_length: number;
  is_collapsed: boolean;
  is_minimal: boolean;
}

// --- Props & Emits ---
const props = defineProps<{
  resource: ResourceWithVersions;
  name: string;
  description: string;
  attributes: SubMessageTemplateAttributes;
  versionName: string;
  versionCommitMessage: string | null;
}>();

defineEmits<{
  (e: 'update:name', value: string): void;
  (e: 'update:description', value: string): void;
  (e: 'update:attributes', value: SubMessageTemplateAttributes): void;
  (e: 'update:versionName', value: string): void;
  (e: 'update:versionCommitMessage', value: string): void;
}>();

// --- Computed Properties ---
const displayResourceType = computed(() => {
  if (props.resource.itemType === 'folder') {
    return '文件夹';
  }
  switch (props.resource.resourceType) {
    case 'system_prompt':
      return '系统提示词';
    case 'submessage_template':
      return '消息模板';
    default:
      return '未知';
  }
});
</script>

<style scoped>
.meta-column {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color);
  background-color: var(--el-fill-color-extra-light);
  display: flex; /* Use flexbox to manage scrollbar */
  flex-direction: column;
  overflow: hidden; /* Hide default overflow, let el-scrollbar handle it */
}

.meta-content-wrapper {
  padding: 20px;
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

/* Ensure el-scrollbar takes full height */
:deep(.el-scrollbar) {
  height: 100%;
}
:deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}
</style>
