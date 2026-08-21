<template>
  <div
    class="bubble-section-group"
    :class="{ 'is-inactive': isInactive, 'is-reasoning': isReasoning }"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- 文本内容区域 -->
    <div class="group-text-wrapper" v-if="effectiveTextSubMessage">
      <!-- 悬浮操作栏 -->
      <div class="group-floating-actions" :class="{ 'is-visible': isHovered && !isGenerating }">
        <el-tooltip v-if="showEdit" :content="$t('common.action.edit')" placement="top" :show-after="500">
          <el-button :icon="Edit" circle size="small" @click="handleEdit" />
        </el-tooltip>
        <el-tooltip v-if="showCopy" :content="$t('common.action.copy')" placement="top" :show-after="500">
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>
        <el-tooltip v-if="showCollapse" :content="isTextCollapsed ? $t('common.action.expand') : $t('common.action.collapse')" placement="top" :show-after="500">
          <el-button :icon="isTextCollapsed ? ArrowDownBold : ArrowUpBold" circle size="small" @click="toggleCollapse" />
        </el-tooltip>
      </div>

      <SubMessageItem
        :sub-message="effectiveTextSubMessage"
        :parent-message="parentMessage"
        :show-header="false"
        :is-inline="true"
        @edit="(payload) => $emit('edit', group.textSubMessage!, payload)"
        @copy="$emit('copy', group.textSubMessage!)"
        @edit-file="(file) => $emit('edit-file', file)"
      />
    </div>

    <!-- 文件/图片分组区域（连续多图合并同行展示） -->
    <div class="group-files-wrapper" v-if="group.fileSubMessages && group.fileSubMessages.length > 0">
      <!-- Group 模式：聚合容器 + 左右箭头切换 + 层叠效果 -->
      <div v-if="isGroupMode" class="group-mode-container">
        <div class="group-mode-main" v-if="pinnedFileMsg">
          <div
            v-if="group.fileSubMessages && group.fileSubMessages.length > 1"
            class="group-mode-arrow group-mode-arrow-left"
            @click="pinPrev"
          >
            <el-icon><ArrowLeft /></el-icon>
          </div>
          <div class="group-mode-stack-wrapper">
            <!-- 后面的层（装饰堆叠效果） -->
            <div
              v-for="(fileMsg, idx) in group.fileSubMessages"
              :key="'bg-' + fileMsg.id"
              class="group-mode-stack-bg"
              :class="{ 'is-hidden': pinnedFileId === fileMsg.id }"
              :style="bgLayerStyle(idx)"
            >
              <img
                v-if="fileMsg.file_info?.mime_type?.startsWith('image/')"
                :src="fileMsg.file_info.url"
              />
            </div>
            <!-- 最前面的大图（SubMessageItem） -->
            <div class="group-mode-stack-front">
              <SubMessageItem
                :sub-message="pinnedFileMsg"
                :parent-message="parentMessage"
                :show-header="false"
                :is-inline="false"
                :preview-src-list="fileGroupPreviewList"
                :preview-index="fileGroupPreviewIndex(getPinnedIndex())"
                @edit-file="(file) => $emit('edit-file', file)"
              />
            </div>
          </div>
          <div
            v-if="group.fileSubMessages && group.fileSubMessages.length > 1"
            class="group-mode-arrow group-mode-arrow-right"
            @click="pinNext"
          >
            <el-icon><ArrowRight /></el-icon>
          </div>
        </div>
      </div>

      <!-- 默认模式：原有平铺展示 -->
      <template v-else>
        <SubMessageItem
          v-for="(fileMsg, fileIdx) in group.fileSubMessages"
          :key="fileMsg.id"
          :sub-message="fileMsg"
          :parent-message="parentMessage"
          :show-header="false"
          :is-inline="false"
          :preview-src-list="fileGroupPreviewList"
          :preview-index="fileGroupPreviewIndex(fileIdx)"
          @edit-file="(file) => $emit('edit-file', file)"
        />
      </template>
    </div>

    <!-- 工具调用小气泡 -->
    <div class="group-tools-wrapper" v-if="group.toolSubMessages.length > 0">
      <template v-for="tool in group.toolSubMessages" :key="tool.id">
        <!-- GoalLoop 轮次边界 get_goal：渲染通栏轮次分隔线（点击仍可打开详情） -->
        <div
          v-if="isGoalLoopRoundMarker(tool)"
          class="goal-round-divider"
          @click="$emit('open-tool-dialog', tool.id)"
        >
          <span class="goal-round-divider-line" />
          <span class="goal-round-divider-label">
            {{ goalRoundText(tool) }}
          </span>
          <span class="goal-round-divider-line" />
        </div>
        <div
          v-else
          class="minimized-item"
          :class="{
            'has-review': tool.type === 'ReviewTool',
            'has-ask-user': tool.type === 'AskUser',
            'is-mcp-wrapped': isMcpWrapped(tool),
          }"
          @click="$emit('open-tool-dialog', tool.id)"
        >
          <el-icon>
            <Warning v-if="tool.type === 'ReviewTool'" style="color: var(--el-color-warning)" />
            <QuestionFilled v-else-if="tool.type === 'AskUser'" style="color: var(--el-color-primary)" />
            <Loading v-else-if="tool.status === 'generating'" class="is-loading" />
            <CircleClose v-else-if="isToolError(tool)" style="color: var(--el-color-error)" />
            <CircleCheck v-else style="color: var(--el-color-success)" />
          </el-icon>
          <span class="minimized-item-title">{{ getToolBubbleText(tool) }}</span>
          <span v-if="getSecurityReviewForTool(tool)" class="security-review-badge" :class="{ 'is-failed': !getSecurityReviewForTool(tool)!.passed }">
            🛡️ {{ getSecurityReviewForTool(tool)!.passed ? t('agent.securityReviewPassed') : t('agent.securityReviewFailed') }}
          </span>
        </div>
      </template>
    </div>

    <!-- Zip History 覆盖指示器 -->
    <div v-if="showZipCoverage" class="zip-coverage-indicator">
      <el-tooltip :content="$t('chat.message.zipCoverageTip')" placement="top" :show-after="300">
        <div class="zip-coverage-arrow">
          <svg width="16" height="10" viewBox="0 0 16 10" fill="none">
            <path d="M8 1L14 9H2L8 1Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
          </svg>
        </div>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { Message, SubMessage, McpToolContent, ReviewToolContent, AskUserContent, SecurityReviewContent, FileResponse } from '@/api/types';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import SubMessageItem from '../SubMessageItem.vue';
import type { BubbleSectionGroup } from '@/composables/useAssistantTimeline';
import { unpackMcpToolCall, getToolArgsSummary, parseGoalLoopRound } from '@/utils/mcpToolUnpack';
import { Edit, CopyDocument, ArrowUpBold, ArrowDownBold, Warning, Loading, CircleClose, CircleCheck, QuestionFilled, Document, ArrowLeft, ArrowRight } from '@element-plus/icons-vue';

const { t } = useI18n();

const props = withDefaults(defineProps<{
  group: BubbleSectionGroup;
  parentMessage: Message;
  isGenerating: boolean;
  isInactive: boolean;
  isReasoning?: boolean;
  showZipCoverage?: boolean;
  showEdit?: boolean;
  showCopy?: boolean;
  showCollapse?: boolean;
  externalCollapsed?: boolean;
}>(), {
  isReasoning: false,
  showZipCoverage: false,
  showEdit: true,
  showCopy: true,
  showCollapse: true,
});

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void;
  (e: 'copy', subMessage: SubMessage): void;
  (e: 'edit-file', file: FileResponse): void;
  (e: 'open-tool-dialog', subMessageId: string): void;
  (e: 'toggle-collapse', subMessageId: string): void;
}>();

const interactionStore = useChatInteractionStore();
const isHovered = ref(false);

/** 外部传入折叠状态时优先使用外部状态，否则从 store 中读取 */
const isTextCollapsed = computed(() => {
  if (props.externalCollapsed !== undefined) {
    return props.externalCollapsed;
  }
  return props.group.textSubMessage?.config?.is_collapsed || false;
});

/** 当外部控制折叠时，将折叠状态注入到 subMessage.config 中一并传给 SubMessageItem */
const effectiveTextSubMessage = computed(() => {
  if (!props.group.textSubMessage) return undefined;
  if (props.externalCollapsed !== undefined) {
    return {
      ...props.group.textSubMessage,
      config: {
        ...props.group.textSubMessage.config,
        is_collapsed: props.externalCollapsed,
      },
    };
  }
  return props.group.textSubMessage;
});

function handleEdit() {
  if (props.group.textSubMessage) {
    emit('edit', props.group.textSubMessage, { content: props.group.textSubMessage.content });
  }
}

function handleCopy() {
  if (props.group.textSubMessage) {
    emit('copy', props.group.textSubMessage);
  }
}

function toggleCollapse() {
  if (props.group.textSubMessage) {
    if (props.externalCollapsed !== undefined) {
      emit('toggle-collapse', props.group.textSubMessage.id);
    } else {
      interactionStore.updateSubMessage({
        subMessageId: props.group.textSubMessage.id,
        data: { config: { ...props.group.textSubMessage.config, is_collapsed: !isTextCollapsed.value } }
      });
    }
  }
}

// --- Group 模式：文件图片聚合 + 置顶 ---

/** 当前 group 中所有 File 子消息是否都是 Group 模式 */
const isGroupMode = computed(() => {
  if (!props.group.fileSubMessages || props.group.fileSubMessages.length <= 1) return false
  return props.group.fileSubMessages.every(
    sm => sm.type === 'File' && sm.config?.show_tool_mode === 'Group'
  )
})

/** 当前置顶的文件 ID（默认第一张） */
const pinnedFileId = ref<string | null>(null)

/** 置顶的 File 子消息 */
const pinnedFileMsg = computed(() => {
  const targetId = pinnedFileId.value || props.group.fileSubMessages?.[0]?.id || null
  return props.group.fileSubMessages?.find(sm => sm.id === targetId) || null
})

/** 置顶图片在预览列表中的索引 */
function getPinnedIndex(): number {
  if (!props.group.fileSubMessages || !pinnedFileMsg.value) return 0
  let imgIdx = 0
  for (const sm of props.group.fileSubMessages) {
    if (sm.type === 'File' && sm.file_info?.mime_type?.startsWith('image/')) {
      if (sm.id === pinnedFileMsg.value.id) return imgIdx
      imgIdx++
    }
  }
  return 0
}

function pinFile(fileId: string) {
  pinnedFileId.value = fileId
}

function pinNext() {
  if (!props.group.fileSubMessages || props.group.fileSubMessages.length === 0) return
  const currentId = pinnedFileId.value || props.group.fileSubMessages[0].id
  const idx = props.group.fileSubMessages.findIndex(sm => sm.id === currentId)
  const nextIdx = (idx + 1) % props.group.fileSubMessages.length
  pinnedFileId.value = props.group.fileSubMessages[nextIdx].id
}

function pinPrev() {
  if (!props.group.fileSubMessages || props.group.fileSubMessages.length === 0) return
  const currentId = pinnedFileId.value || props.group.fileSubMessages[0].id
  const idx = props.group.fileSubMessages.findIndex(sm => sm.id === currentId)
  const prevIdx = (idx - 1 + props.group.fileSubMessages.length) % props.group.fileSubMessages.length
  pinnedFileId.value = props.group.fileSubMessages[prevIdx].id
}

function bgLayerStyle(idx: number) {
  if (!props.group.fileSubMessages) return {}
  const total = props.group.fileSubMessages.length
  const isActive = pinnedFileId.value === props.group.fileSubMessages[idx].id
  return {
    zIndex: isActive ? total + 1 : total - idx,
  }
}

function getParsedContent(tool: SubMessage): McpToolContent | ReviewToolContent | null {
  try {
    return JSON.parse(tool.content);
  } catch {
    return null;
  }
}

function getToolName(tool: SubMessage): string {
  if (tool.type === 'AskUser') {
    return t('chat.askUser.toolName');
  }
  const content = getParsedContent(tool);
  if (!content) return t('chat.message.mcp.unknownTool');
  const unpacked = unpackMcpToolCall(content);
  return unpacked.displayName;
}

function getToolArgsSummaryText(tool: SubMessage): string {
  const content = getParsedContent(tool);
  if (!content) return '';
  return getToolArgsSummary(content);
}

function getToolBubbleText(tool: SubMessage): string {
  const name = getToolName(tool);
  const args = getToolArgsSummaryText(tool);
  return args ? `${name} ${args}` : name;
}

function isMcpWrapped(tool: SubMessage): boolean {
  if (tool.type === 'AskUser') return false;
  const content = getParsedContent(tool);
  if (!content) return false;
  return unpackMcpToolCall(content).isMcpWrapped;
}

/** tool_call_id → SecurityReviewContent 映射 */
const securityReviewMap = computed(() => {
  const map = new Map<string, SecurityReviewContent>();
  for (const sm of props.parentMessage.sub_messages) {
    if (sm.type === 'SecurityReview') {
      try {
        const content = JSON.parse(sm.content) as SecurityReviewContent;
        map.set(content.tool_call_id, content);
      } catch { /* ignore */ }
    }
  }
  return map;
});

function getSecurityReviewForTool(tool: SubMessage): SecurityReviewContent | undefined {
  try {
    if (tool.type === 'McpTool') {
      const content = JSON.parse(tool.content) as McpToolContent;
      return securityReviewMap.value.get(content.tool_call_id);
    }
    if (tool.type === 'ReviewTool') {
      const content = JSON.parse(tool.content) as ReviewToolContent;
      return securityReviewMap.value.get(content.tool_call_id);
    }
  } catch { /* ignore */ }
  return undefined;
}

function isToolError(tool: SubMessage): boolean {
  if (tool.type !== 'McpTool') return false;
  const content = getParsedContent(tool) as McpToolContent | null;
  return content?.is_error || false;
}

/** 是否为 GoalLoopMiddleware 注入的轮次边界 get_goal（config.is_goal_loop_round 标志） */
function isGoalLoopRoundMarker(tool: SubMessage): boolean {
  return tool.type === 'McpTool' && tool.config?.is_goal_loop_round === true;
}

/** 轮次分隔线文案：优先从 result 解析"第 X/Y 轮"，解析不到则显示通用文案 */
function goalRoundText(tool: SubMessage): string {
  if (tool.type !== 'McpTool') return '';
  const content = getParsedContent(tool) as McpToolContent | null;
  const info = content ? parseGoalLoopRound(content.result) : null;
  if (info) {
    return t('chat.message.goalLoopRound', { round: info.round, max: info.max });
  }
  return t('chat.message.goalLoopRoundUnknown');
}

/** 文件组中所有图片的聚合预览列表（用于键盘导航） */
const fileGroupPreviewList = computed(() => {
  if (!props.group.fileSubMessages) return [];
  return props.group.fileSubMessages
    .filter(sm => sm.type === 'File' && sm.file_info?.mime_type?.startsWith('image/'))
    .map(sm => sm.file_info!.url);
});

/** 计算当前图片在聚合预览列表中的索引 */
function fileGroupPreviewIndex(fileIdx: number): number {
  if (!props.group.fileSubMessages) return 0;
  let imgIdx = 0;
  for (let i = 0; i <= fileIdx; i++) {
    const sm = props.group.fileSubMessages[i];
    if (sm.type === 'File' && sm.file_info?.mime_type?.startsWith('image/')) {
      if (i === fileIdx) return imgIdx;
      imgIdx++;
    }
  }
  return imgIdx;
}
</script>

<style scoped>
.bubble-section-group {
  position: relative;
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-extra-light);
  transition: opacity 0.3s;
}
.bubble-section-group:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.bubble-section-group.is-inactive {
  opacity: 1;
  padding-left: 8px;
}

/* 思考区域内的分隔线 */
.bubble-section-group.is-reasoning {
  border-bottom-color: var(--el-border-color-extra-light);
}

.group-text-wrapper {
  position: relative;
}

.group-floating-actions {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  gap: 4px;
  background-color: var(--el-bg-color);
  padding: 2px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s, visibility 0.2s;
  z-index: 10;
}
.group-floating-actions.is-visible {
  opacity: 1;
  visibility: visible;
}

.group-tools-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding-left: 4px;
}

/* GoalLoop 轮次边界分隔线：通栏展示，营造"下一轮开始"的轮次感 */
.goal-round-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  margin: 4px 0;
  padding: 6px 0;
  cursor: pointer;
  user-select: none;
}
.goal-round-divider-line {
  flex: 1;
  height: 1px;
  background: var(--el-border-color-darker);
  opacity: 0.45;
}
.goal-round-divider-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
  padding: 3px 14px;
  border-radius: 999px;
  white-space: nowrap;
  transition: all 0.2s;
}
.goal-round-divider:hover .goal-round-divider-label {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-8);
}

/* 文件/图片分组容器：flex-wrap 同行排布多张图片 */
.group-files-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 【关键修改】工具小气泡设为较浅的灰色 */
.minimized-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background-color: var(--el-fill-color-light); /* 较浅的灰色 */
  border: 1px solid var(--el-border-color-light);
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.minimized-item .is-loading {
  animation: rotating 2s linear infinite;
}
.minimized-item:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background-color: var(--el-fill-color); /* hover 时稍深 */
}
.minimized-item.has-review {
  border-color: var(--el-color-warning-light-3);
  background-color: var(--el-color-warning-light-9);
}
.minimized-item.has-review:hover {
  border-color: var(--el-color-warning);
  color: var(--el-color-warning-dark-2);
}
.minimized-item.has-ask-user {
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}
.minimized-item.has-ask-user:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.minimized-item.is-mcp-wrapped {
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}
.minimized-item.is-mcp-wrapped:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.security-review-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background-color: var(--el-color-success-light-9);
  color: var(--el-color-success);
  white-space: nowrap;
}

.security-review-badge.is-failed {
  background-color: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.minimized-item-title {
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ========== Zip History 覆盖指示器 ========== */
.zip-coverage-indicator {
  display: flex;
  justify-content: flex-start;
  padding-top: 6px;
  margin-top: 4px;
  padding-left: 4px;
}

.zip-coverage-arrow {
  color: var(--el-color-success-light-3);
  cursor: help;
  transition: color 0.2s, transform 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.zip-coverage-arrow:hover {
  color: var(--el-color-success);
  transform: translateY(-1px);
}

/* ========== Group 模式：层叠堆叠效果 + 左右箭头 ========== */
.group-mode-container {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 8px;
  background-color: var(--el-fill-color-lighter);
}

.group-mode-main {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.group-mode-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 20;
  opacity: 0;
  transition: opacity 0.2s;
  font-size: 14px;
}
.group-mode-main:hover .group-mode-arrow {
  opacity: 1;
}
.group-mode-arrow:hover {
  background: rgba(0, 0, 0, 0.65);
}
.group-mode-arrow-left { left: 4px; }
.group-mode-arrow-right { right: 4px; }

/* 层叠堆叠容器 */
.group-mode-stack-wrapper {
  position: relative;
}

/* 后面的装饰层 */
.group-mode-stack-bg {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 100%;
  height: 100%;
  border-radius: 6px;
  overflow: hidden;
  border: 2px solid var(--el-bg-color);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
  background: var(--el-fill-color);
  opacity: 0.5;
  transition: transform 0.25s ease;
}
.group-mode-stack-bg.is-hidden {
  opacity: 0;
}
.group-mode-stack-bg:nth-of-type(1) {
  transform: rotate(-2deg);
}
.group-mode-stack-bg:nth-of-type(2) {
  transform: rotate(1.5deg);
  top: 3px;
  left: 3px;
}
.group-mode-stack-bg img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 最前面的大图 */
.group-mode-stack-front {
  position: relative;
  z-index: 10;
}
</style>
