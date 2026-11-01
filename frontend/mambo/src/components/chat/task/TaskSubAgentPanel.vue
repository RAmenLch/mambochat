<!-- frontend/mambo/src/components/chat/task/TaskSubAgentPanel.vue -->
<template>
  <div class="subagent-panel">
    <!-- 步骤数与耗时摘要（耗时取步骤时间戳跨度，进行中实时增长） -->
    <div class="task-summary">
      <span>{{ t('chat.subagent.steps', { count: steps.length }) }}</span>
      <span v-if="durationText" class="task-duration">{{ t('chat.subagent.elapsed', { duration: durationText }) }}</span>
    </div>
    <!-- ========== 堆叠模式（全局配置 message_display_mode = 'stacked'） ========== -->
    <template v-if="messageDisplayMode === 'stacked'">
      <!-- 思考区域 (Reasoning) -->
      <div class="bubble-section reasoning-section" v-if="reasoningSection && !isReasoningMinimized">
        <div class="section-title" @click="isReasoningMinimized = true">
          {{ t('chat.message.reasoning') }}
        </div>
        <div class="section-content">
          <BubbleSectionGroup
            v-for="group in reasoningSection.groups"
            :key="group.id"
            :group="group"
            :parent-message="virtualMessage"
            :is-generating="false"
            :is-inactive="false"
            :show-edit="false"
            :external-collapsed="isSubMsgCollapsed(group.textSubMessage?.id)"
            @copy="handleCopy"
            @toggle-collapse="handleToggleCollapse"
            @open-tool-dialog="handleToolClick"
          />
        </div>
      </div>
      <div v-else-if="reasoningSection" class="reasoning-minimized-block" @click="isReasoningMinimized = false">
        {{ t('chat.message.reasoningCollapsed') }}
      </div>

      <!-- 正文区域 (Normal) -->
      <div class="bubble-section normal-section" v-if="normalSection">
        <div class="section-content">
          <BubbleSectionGroup
            v-for="group in normalSection.groups"
            :key="group.id"
            :group="group"
            :parent-message="virtualMessage"
            :is-generating="false"
            :is-inactive="false"
            :show-edit="false"
            :external-collapsed="isSubMsgCollapsed(group.textSubMessage?.id)"
            @copy="handleCopy"
            @toggle-collapse="handleToggleCollapse"
            @open-tool-dialog="handleToolClick"
          />
        </div>
      </div>
    </template>

    <!-- ========== 交错模式（全局配置 message_display_mode = 'interleaved'，与主代理一致） ========== -->
    <template v-else>
      <div
        v-for="(section, index) in interleavedSections"
        :key="sectionKey(section, index)"
        :class="[
          'bubble-section',
          section.type === 'reasoning' ? 'interleaved-reasoning-section' : 'interleaved-normal-section'
        ]"
      >
        <!-- Reasoning Section（折叠面板：默认展开，便于查看追踪过程） -->
        <template v-if="section.type === 'reasoning'">
          <div class="reasoning-collapsible" :class="{ 'is-collapsed': isSectionCollapsed(section, index) }">
            <div class="reasoning-collapse-header" @click="toggleSectionCollapse(section, index)">
              <el-icon class="collapse-arrow">
                <ArrowRight v-if="isSectionCollapsed(section, index)" />
                <ArrowDown v-else />
              </el-icon>
              <span class="collapse-title">{{ t('chat.message.reasoning') }}</span>
              <span v-if="sectionToolCount(section) > 0" class="collapse-tool-count">{{ sectionToolCount(section) }}</span>
            </div>
            <div class="reasoning-collapse-body" v-show="!isSectionCollapsed(section, index)">
              <div class="section-content">
                <BubbleSectionGroup
                  v-for="group in section.groups"
                  :key="group.id"
                  :group="group"
                  :parent-message="virtualMessage"
                  :is-generating="false"
                  :is-inactive="false"
                  :show-edit="false"
                  :external-collapsed="isSubMsgCollapsed(group.textSubMessage?.id)"
                  @copy="handleCopy"
                  @toggle-collapse="handleToggleCollapse"
                  @open-tool-dialog="handleToolClick"
                />
              </div>
            </div>
          </div>
        </template>

        <!-- Normal Section -->
        <template v-else>
          <div class="section-content">
            <BubbleSectionGroup
              v-for="group in section.groups"
              :key="group.id"
              :group="group"
              :parent-message="virtualMessage"
              :is-generating="false"
              :is-inactive="false"
              :show-edit="false"
              :external-collapsed="isSubMsgCollapsed(group.textSubMessage?.id)"
              @copy="handleCopy"
              @toggle-collapse="handleToggleCollapse"
              @open-tool-dialog="handleToolClick"
            />
          </div>
        </template>
      </div>
    </template>

    <div v-if="interleavedSections.length === 0" class="empty-state">
      {{ t('chat.subagent.noSteps') }}
    </div>

    <McpToolDialog
      v-model:visible="toolDialogVisible"
      :parent-message-id="null"
      :parent-message="toolDialogParentMsg"
      :initial-sub-message-id="toolDialogInitialId"
      mode="single"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import { ElMessage } from 'element-plus';
import { ArrowRight, ArrowDown } from '@element-plus/icons-vue';
import type { Message, SubMessage, SecurityReviewContent } from '@/api/types';
import { useAssistantTimeline, type BubbleSection } from '@/composables/useAssistantTimeline';
import { buildSubAgentVirtualMessage, useTaskDuration, type ReviewToolMapEntry } from '@/composables/useTaskSubSteps';
import { useSettingsStore } from '@/stores/settingsStore';
import { copyToClipboard } from '@/utils/clipboard';
import BubbleSectionGroupComponent from '../message/BubbleSectionGroup.vue';
import McpToolDialog from '../dialogs/McpToolDialog.vue';

const BubbleSectionGroup = BubbleSectionGroupComponent;
const { t } = useI18n();

const settingsStore = useSettingsStore();
const { globalSettings } = storeToRefs(settingsStore);

/** 消息显示模式：与主代理（AssistantBubble）读取同一份全局配置 */
const messageDisplayMode = computed(() => globalSettings.value.message_display_mode ?? 'interleaved');

const props = defineProps<{
  steps: SubMessage[];
  /** 子代理任务是否仍在进行（耗时实时增长） */
  isRunning?: boolean;
  /** 子代理工具调用 → SecurityReview 映射，key=sub_tool_call_id */
  securityReviewMap?: Map<string, SecurityReviewContent>;
  /** 子代理工具调用 → {content, sub_message_id} 映射，key=sub_tool_call_id */
  reviewToolMap?: Map<string, ReviewToolMapEntry>;
}>();

const { durationText } = useTaskDuration(
  computed(() => props.steps),
  computed(() => props.isRunning === true),
);


/** 本地折叠状态：子代理追踪面板内子消息的折叠与展开 */
const collapsedSubMsgIds = ref<Set<string>>(new Set());

function isSubMsgCollapsed(id: string | undefined): boolean | undefined {
  if (!id) return undefined;
  // 返回 undefined 会让 BubbleSectionGroup 走默认 store 逻辑，
  // 但这里我们总是需要外部控制折叠状态
  return collapsedSubMsgIds.value.has(id);
}

function handleToggleCollapse(subMsgId: string) {
  const next = new Set(collapsedSubMsgIds.value);
  if (next.has(subMsgId)) {
    next.delete(subMsgId);
  } else {
    next.add(subMsgId);
  }
  collapsedSubMsgIds.value = next;
}

async function handleCopy(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content);
    ElMessage.success(t('common.msg.copySuccess'));
  } catch {
    ElMessage.error(t('common.msg.copyFailed'));
  }
}

/** 将 TaskSubStep 数组转换为虚拟 Message（映射实现见 composables/useTaskSubSteps） */
const virtualMessage = computed<Message>(() =>
  buildSubAgentVirtualMessage(props.steps, props.securityReviewMap, props.reviewToolMap),
);

const messageRef = computed(() => virtualMessage.value);
const { reasoningSection, normalSection, interleavedSections } = useAssistantTimeline(messageRef, messageDisplayMode);
const isReasoningMinimized = ref(true);

/** 交错模式：被用户折叠的 reasoning 区块键集合（默认全部展开，便于查看追踪过程） */
const collapsedSectionKeys = ref<Set<string>>(new Set());

function sectionKey(section: BubbleSection, index: number): string {
  return `${section.groups[0]?.id ?? 'section'}_${index}`;
}

function isSectionCollapsed(section: BubbleSection, index: number): boolean {
  return collapsedSectionKeys.value.has(sectionKey(section, index));
}

function toggleSectionCollapse(section: BubbleSection, index: number) {
  const key = sectionKey(section, index);
  const next = new Set(collapsedSectionKeys.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  collapsedSectionKeys.value = next;
}

/** 交错模式：reasoning 区块内包含的工具调用数量（用于折叠态提示） */
function sectionToolCount(section: BubbleSection): number {
  return section.groups.reduce((sum, group) => sum + group.toolSubMessages.length, 0);
}

// ── 子代理工具调用弹窗 ──
const toolDialogVisible = ref(false);
const toolDialogParentMsg = ref<Message | null>(null);
const toolDialogInitialId = ref('');

function handleToolClick(subMessageId: string) {
  toolDialogParentMsg.value = virtualMessage.value;
  toolDialogInitialId.value = subMessageId;
  toolDialogVisible.value = true;
}
</script>

<style scoped>
.subagent-panel {
  padding: 4px 0;
}

.task-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.task-duration {
  font-variant-numeric: tabular-nums;
}

/* 思考区域 */
.reasoning-section {
  position: relative;
  margin-bottom: 16px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-weight: bold;
  margin-bottom: 8px;
  cursor: pointer;
  user-select: none;
}
.section-title:hover {
  color: var(--el-text-color-primary);
}

/* 推理最小化态 */
.reasoning-minimized-block {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  margin-bottom: 16px;
  background-color: #fafafa;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}
.reasoning-minimized-block:hover {
  background-color: #f5f5f5;
  border-color: var(--el-border-color);
}

/* 推理区文字深色 */
.reasoning-section :deep(.message-content) {
  color: var(--el-text-color-primary) !important;
}

/* 正文区域 */
.normal-section {
  /* 继承白色背景 */
}

.empty-state {
  text-align: center;
  color: var(--el-text-color-placeholder);
  padding: 24px;
  font-size: 14px;
}

/* ========== 交错模式（与主代理 AssistantBubble 对齐） ========== */
.interleaved-reasoning-section {
  position: relative;
}

.reasoning-collapsible {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background-color: #fafafa;
}

.reasoning-collapse-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.reasoning-collapse-header:hover {
  background-color: #f0f0f0;
}

.reasoning-collapse-header .collapse-arrow {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.reasoning-collapse-header .collapse-title {
  font-weight: 600;
  flex: 1;
}

.reasoning-collapse-header .collapse-tool-count {
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background-color: var(--el-fill-color-dark);
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.reasoning-collapse-body {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 16px;
  border-left: 3px solid var(--el-border-color);
  background-color: #f5f5f5;
  margin: 0 8px 8px 8px;
  border-radius: 0 6px 6px 0;
}

.reasoning-collapsible.is-collapsed .reasoning-collapse-body {
  display: none;
}

.interleaved-reasoning-section :deep(.message-content) {
  color: var(--el-text-color-primary) !important;
}

.interleaved-reasoning-section :deep(.content-block strong),
.interleaved-reasoning-section :deep(.content-block b) {
  color: var(--el-text-color-primary) !important;
}

.interleaved-normal-section :deep(.message-content) {
  color: var(--el-text-color-primary);
}
</style>
