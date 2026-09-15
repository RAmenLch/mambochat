<!-- frontend/mambo/src/components/chat/message/TailToolPanel.vue -->
<!--
  尾部工具汇总面板（config.is_tail_tool）：这类子消息不参与正文 / 时间线渲染，
  仅在助手消息底部以可折叠面板展示。面板**直接复用正文的分组组件 BubbleSectionGroup**
  （工具=缩略气泡点击打开、文件、文本），因此观感与正文一致。
-->
<template>
  <div
    v-if="hasAny"
    class="tail-tool-panel"
    :class="{ 'is-error': hasError, 'is-expanded': isExpanded }"
  >
    <!-- 头部：点击展开 / 折叠 -->
    <div class="tail-tool-header" @click="isExpanded = !isExpanded">
      <el-icon class="tail-tool-arrow">
        <ArrowRight v-if="!isExpanded" />
        <ArrowDown v-else />
      </el-icon>
      <span class="tail-tool-title">{{ t('chat.message.tailToolPanel.title') }}</span>
      <span v-if="toolCount > 0" class="tail-tool-count">
        · {{ t('chat.message.tailToolPanel.taskCount', { n: toolCount }) }}
      </span>
    </div>

    <!-- 内容区：默认折叠；复用正文分组组件 -->
    <div v-show="isExpanded" class="tail-tool-body">
      <BubbleSectionGroup
        v-for="(item, index) in groups"
        :key="index"
        :group="item.group"
        :parent-message="parentMessage"
        :is-generating="false"
        :is-inactive="false"
        :is-reasoning="item.isReasoning"
        :show-edit="false"
        :show-copy="false"
        :show-collapse="false"
        @open-tool-dialog="(id) => emit('open-tool-dialog', id)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Message, SubMessage } from '@/api/types'
import { ArrowRight, ArrowDown } from '@element-plus/icons-vue'
import BubbleSectionGroup from './BubbleSectionGroup.vue'
import type { BubbleSectionGroup as BubbleSectionGroupType } from '@/composables/useAssistantTimeline'

const props = defineProps<{
  /** 携带 config.is_tail_tool === true 的子消息（可能多条） */
  subMessages: SubMessage[]
  /** 所属助手消息（透传给分组组件） */
  parentMessage: Message
}>()

const emit = defineEmits<{
  (e: 'open-tool-dialog', subMessageId: string): void
}>()

const { t } = useI18n()
const isExpanded = ref(false)

const toolSubMessages = computed(() => props.subMessages.filter(sm => sm.type === 'McpTool'))
// 排除 Mini_Avatar / Gal_Avatar 模式的 File：它们仅在头像 / 侧边栏展示，不在面板内联（与正文时间线一致）
const fileSubMessages = computed(() =>
  props.subMessages.filter(
    sm =>
      sm.type === 'File' &&
      !['Mini_Avatar', 'Gal_Avatar'].includes(sm.config?.show_tool_mode || '')
  )
)
const reasoningSubMessages = computed(() => props.subMessages.filter(sm => sm.type === 'Reasoning'))
const normalSubMessages = computed(() => props.subMessages.filter(sm => sm.type === 'Normal'))

const hasAny = computed(
  () =>
    toolSubMessages.value.length +
      fileSubMessages.value.length +
      reasoningSubMessages.value.length +
      normalSubMessages.value.length >
    0,
)

/** “X 个任务” = 尾部实际执行的工具调用数 */
const toolCount = computed(() => toolSubMessages.value.length)

/** 合成正文同款分组：思考一个分组 + 正文/文件/工具一个分组 */
const groups = computed(() => {
  const result: Array<{ group: BubbleSectionGroupType; isReasoning: boolean }> = []
  if (reasoningSubMessages.value.length) {
    result.push({
      group: {
        id: 'tail-reasoning',
        textSubMessage: reasoningSubMessages.value[0],
        toolSubMessages: [],
      },
      isReasoning: true,
    })
  }
  const text = normalSubMessages.value[0] ?? null
  if (text || toolSubMessages.value.length || fileSubMessages.value.length) {
    result.push({
      group: {
        id: 'tail-main',
        textSubMessage: text,
        toolSubMessages: toolSubMessages.value,
        fileSubMessages: fileSubMessages.value,
      },
      isReasoning: false,
    })
  }
  return result
})

const hasError = computed(() =>
  toolSubMessages.value.some(sm => {
    if (!sm.content) return false
    try {
      return (JSON.parse(sm.content) as { is_error?: boolean }).is_error === true
    } catch {
      return false
    }
  }),
)
</script>

<style scoped>
.tail-tool-panel {
  /* 默认：淡紫色底 + 紫色左边框，与正文视觉区分；折叠态收缩为小块，不占整行 */
  --tail-tool-bg: rgba(146, 128, 214, 0.07);
  --tail-tool-accent: #b3a9d8;

  display: inline-block;
  align-self: flex-start;
  width: fit-content;
  max-width: 100%;
  margin-top: 6px;
  border-left: 2px solid var(--tail-tool-accent);
  background-color: var(--tail-tool-bg);
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  overflow: hidden;
}
.tail-tool-panel.is-expanded {
  width: 100%;
}
.tail-tool-panel.is-error {
  --tail-tool-bg: var(--el-color-error-light-9);
  --tail-tool-accent: var(--el-color-error-light-3);
}

/* ========== 头部 ========== */
.tail-tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  cursor: pointer;
  user-select: none;
  font-weight: 600;
  color: var(--el-text-color-regular);
  transition: color 0.2s;
}
.tail-tool-header:hover {
  color: var(--el-color-primary);
}
.tail-tool-arrow {
  font-size: 12px;
}
.tail-tool-count {
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

/* ========== 内容区（复用正文分组组件） ========== */
.tail-tool-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 10px 10px 10px;
}
</style>
