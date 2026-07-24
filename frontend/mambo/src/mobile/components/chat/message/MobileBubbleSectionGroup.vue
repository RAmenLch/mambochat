<!-- frontend/mambo/src/mobile/components/chat/message/MobileBubbleSectionGroup.vue -->
<template>
  <div
    class="mobile-bubble-section-group"
    :class="{ 'is-inactive': isInactive, 'is-reasoning': isReasoning }"
    @click.stop="$emit('toggle-actions', group.textSubMessage?.id || group.id)"
  >
    <!-- 文本内容区域 -->
    <div class="group-text-wrapper" v-if="group.textSubMessage">
      <SubMessageItem
        :sub-message="group.textSubMessage"
        :parent-message="parentMessage"
        :show-header="false"
        :is-inline="true"
        @edit="(payload) => $emit('edit', group.textSubMessage!, payload)"
        @edit-file="(file) => $emit('edit-file', file)"
        @copy="$emit('copy', group.textSubMessage)"
      />
    </div>

    <!-- 文件/图片分组区域：多张堆叠为轮播 -->
    <div class="group-files-wrapper" v-if="group.fileSubMessages && group.fileSubMessages.length > 0">
      <!-- 单张直接展示 -->
      <template v-if="group.fileSubMessages.length === 1">
        <SubMessageItem
          :sub-message="group.fileSubMessages[0]"
          :parent-message="parentMessage"
          :show-header="false"
          :is-inline="false"
          :preview-src-list="fileGroupPreviewList"
          :preview-index="0"
          @edit-file="(file) => $emit('edit-file', file)"
        />
      </template>

      <!-- 多张：轮播 -->
      <template v-else>
        <div class="file-carousel">
          <div class="carousel-viewport">
            <div
              class="carousel-track"
              :style="{ transform: `translateX(-${carouselIndex * 100}%)` }"
            >
              <div
                v-for="(fileMsg, fileIdx) in group.fileSubMessages"
                :key="fileMsg.id"
                class="carousel-slide"
              >
                <SubMessageItem
                  :sub-message="fileMsg"
                  :parent-message="parentMessage"
                  :show-header="false"
                  :is-inline="false"
                  :preview-src-list="fileGroupPreviewList"
                  :preview-index="fileGroupPreviewIndex(fileIdx)"
                  @edit-file="(file) => $emit('edit-file', file)"
                />
              </div>
            </div>
          </div>

          <button class="carousel-arrow carousel-prev" @click.stop="carouselPrev" v-if="group.fileSubMessages.length > 1">
            <el-icon :size="18"><ArrowLeft /></el-icon>
          </button>
          <button class="carousel-arrow carousel-next" @click.stop="carouselNext" v-if="group.fileSubMessages.length > 1">
            <el-icon :size="18"><ArrowRight /></el-icon>
          </button>

          <div class="carousel-dots" v-if="group.fileSubMessages.length > 1">
            <span
              v-for="(_, dotIdx) in group.fileSubMessages"
              :key="dotIdx"
              class="carousel-dot"
              :class="{ 'is-active': dotIdx === carouselIndex }"
              @click.stop="carouselIndex = dotIdx"
            ></span>
          </div>
        </div>
      </template>
    </div>

    <!-- 工具调用内联标签区域 -->
    <div class="group-tools-wrapper" v-if="group.toolSubMessages.length > 0">
      <div
        v-for="tool in group.toolSubMessages"
        :key="tool.id"
        class="tool-chip"
        :class="{
          'has-review': tool.type === 'ReviewTool',
          'is-mcp-wrapped': isMcpWrapped(tool),
        }"
        @click.stop="$emit('open-tool-dialog', tool.id)"
      >
        <el-icon>
          <Warning v-if="tool.type === 'ReviewTool'" style="color: var(--el-color-warning)" />
          <Loading v-else-if="tool.status === 'generating'" class="is-loading" />
          <CircleClose v-else-if="isToolError(tool)" style="color: var(--el-color-error)" />
          <CircleCheck v-else style="color: var(--el-color-success)" />
        </el-icon>
        <span class="tool-chip-title">
          {{ getToolName(tool) }}
        </span>
        <span v-if="getSecurityReviewForTool(tool)" class="security-review-badge" :class="{ 'is-failed': !getSecurityReviewForTool(tool)!.passed }">
          🛡️ {{ getSecurityReviewForTool(tool)!.passed ? t('agent.securityReviewPassed') : t('agent.securityReviewFailed') }}
        </span>
      </div>
    </div>

    <!-- 操作菜单插槽 (跟随当前 Group 浮现) -->
    <div class="group-actions-container" v-if="$slots.actions">
      <slot name="actions"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import type { Message, SubMessage, McpToolContent, ReviewToolContent, SecurityReviewContent, FileResponse } from '@/api/types'
import SubMessageItem from '../SubMessageItem.vue'
import type { BubbleSectionGroup } from '@/composables/useAssistantTimeline'
import { unpackMcpToolCall } from '@/utils/mcpToolUnpack'
import { Warning, Loading, CircleClose, CircleCheck, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  group: BubbleSectionGroup
  parentMessage: Message
  isGenerating: boolean
  isInactive: boolean
  isReasoning?: boolean
}>(), {
  isReasoning: false,
})

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void
  (e: 'copy', subMessage: SubMessage): void
  (e: 'open-tool-dialog', subMessageId: string): void
  (e: 'toggle-actions', subMessageId: string): void
  (e: 'edit-file', file: FileResponse): void
}>()

const carouselIndex = ref(0)

function carouselPrev() {
  if (!props.group.fileSubMessages) return
  carouselIndex.value = (carouselIndex.value - 1 + props.group.fileSubMessages.length) % props.group.fileSubMessages.length
}

function carouselNext() {
  if (!props.group.fileSubMessages) return
  carouselIndex.value = (carouselIndex.value + 1) % props.group.fileSubMessages.length
}

function getParsedContent(tool: SubMessage): McpToolContent | ReviewToolContent | null {
  try {
    return JSON.parse(tool.content)
  } catch {
    return null
  }
}

function getToolName(tool: SubMessage): string {
  const content = getParsedContent(tool)
  if (!content) return t('chat.message.mcp.unknownTool')
  const unpacked = unpackMcpToolCall(content)
  return unpacked.displayName
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
  if (tool.type !== 'McpTool') return false
  const content = getParsedContent(tool) as McpToolContent | null
  return content?.is_error || false
}

function isMcpWrapped(tool: SubMessage): boolean {
  const content = getParsedContent(tool)
  if (!content) return false
  return unpackMcpToolCall(content).isMcpWrapped
}

/** 文件组中所有图片的聚合预览列表（用于键盘导航） */
const fileGroupPreviewList = computed(() => {
  if (!props.group.fileSubMessages) return []
  return props.group.fileSubMessages
    .filter(sm => sm.type === 'File' && sm.file_info?.mime_type?.startsWith('image/'))
    .map(sm => sm.file_info!.url)
})

/** 计算当前图片在聚合预览列表中的索引 */
function fileGroupPreviewIndex(fileIdx: number): number {
  if (!props.group.fileSubMessages) return 0
  let imgIdx = 0
  for (let i = 0; i <= fileIdx; i++) {
    const sm = props.group.fileSubMessages[i]
    if (sm.type === 'File' && sm.file_info?.mime_type?.startsWith('image/')) {
      if (i === fileIdx) return imgIdx
      imgIdx++
    }
  }
  return imgIdx
}
</script>

<style scoped>
.mobile-bubble-section-group {
  position: relative;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-extra-light);
  display: flex;
  flex-direction: column;
  cursor: pointer;
}

.mobile-bubble-section-group:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.mobile-bubble-section-group.is-inactive {
  opacity: 0.7;
}

.mobile-bubble-section-group.is-reasoning {
  border-bottom-color: var(--el-border-color-lighter);
}

.group-text-wrapper {
  position: relative;
}

.group-files-wrapper {
  margin-top: 6px;
}

/* ========== 轮播 ========== */
.file-carousel {
  position: relative;
  overflow: hidden;
  border-radius: 14px;
  background: var(--el-fill-color-lighter);
}

.carousel-viewport {
  overflow: hidden;
  border-radius: 14px;
}

.carousel-track {
  display: flex;
  transition: transform 0.3s ease;
}

.carousel-slide {
  min-width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.carousel-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 5;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  opacity: 0;
  transition: opacity 0.2s;
}

.file-carousel:active .carousel-arrow,
.file-carousel:hover .carousel-arrow {
  opacity: 1;
}

.carousel-prev {
  left: 6px;
}
.carousel-next {
  right: 6px;
}

.carousel-dots {
  display: flex;
  justify-content: center;
  gap: 6px;
  padding: 8px 0;
}

.carousel-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-border-color);
  cursor: pointer;
  transition: background 0.2s;
  -webkit-tap-highlight-color: transparent;
}

.carousel-dot.is-active {
  background: var(--el-color-primary);
}

.group-tools-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.tool-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  background-color: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  color: var(--el-text-color-regular);
  font-size: 12px;
  cursor: pointer;
}

.tool-chip .is-loading {
  animation: rotating 2s linear infinite;
}

.tool-chip.has-review {
  border-color: var(--el-color-warning-light-3);
  background-color: var(--el-color-warning-light-9);
}

.tool-chip.is-mcp-wrapped {
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}

.tool-chip-title {
  white-space: nowrap;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.security-review-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  background-color: var(--el-color-success-light-9);
  color: var(--el-color-success);
  white-space: nowrap;
}

.security-review-badge.is-failed {
  background-color: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.group-actions-container {
  margin-top: 4px;
  align-self: flex-end; /* 菜单靠右对齐 */
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
