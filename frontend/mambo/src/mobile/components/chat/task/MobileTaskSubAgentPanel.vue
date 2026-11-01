<!-- frontend/mambo/src/mobile/components/chat/task/MobileTaskSubAgentPanel.vue — 移动端子 Agent 追踪步骤面板 -->
<template>
  <div class="mobile-task-panel">
    <div v-if="groups.length === 0" class="empty-hint">{{ t('chat.subagent.noSteps') }}</div>
    <template v-else>
      <MobileBubbleSectionGroup
        v-for="group in groups"
        :key="group.id"
        :group="group"
        :parent-message="virtualMessage"
        :is-generating="false"
        :is-inactive="false"
        @copy="handleCopy"
        @open-tool-dialog="openToolDialog"
      />
    </template>

    <MobileToolDialog
      v-model:visible="toolDialogVisible"
      :parent-message-id="virtualMessage.id"
      :parent-message="virtualMessage"
      :initial-sub-message-id="toolDialogInitialId"
      mode="single"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import type { Message, SecurityReviewContent, SubMessage } from '@/api/types'
import { useAssistantTimeline } from '@/composables/useAssistantTimeline'
import { buildSubAgentVirtualMessage, type ReviewToolMapEntry } from '@/composables/useTaskSubSteps'
import { useSettingsStore } from '@/stores/settingsStore'
import { copyToClipboard } from '@/utils/clipboard'
import MobileBubbleSectionGroup from '../message/MobileBubbleSectionGroup.vue'
import MobileToolDialog from '../dialogs/MobileToolDialog.vue'

const props = defineProps<{
  steps: SubMessage[]
  /** 子代理工具调用 → SecurityReview 映射，key = sub_tool_call_id */
  securityReviewMap?: Map<string, SecurityReviewContent>
  /** 子代理工具调用 → { content, sub_message_id } 映射，key = sub_tool_call_id */
  reviewToolMap?: Map<string, ReviewToolMapEntry>
}>()

const { t } = useI18n()
const settingsStore = useSettingsStore()
const { globalSettings } = storeToRefs(settingsStore)

const messageDisplayMode = computed(() => globalSettings.value.message_display_mode ?? 'interleaved')

const virtualMessage = computed<Message>(() =>
  buildSubAgentVirtualMessage(props.steps, props.securityReviewMap, props.reviewToolMap),
)

const messageRef = computed(() => virtualMessage.value)
const { interleavedSections } = useAssistantTimeline(messageRef, messageDisplayMode)

/** 按时间顺序展平为分组列表（Reasoning 与正文交错） */
const groups = computed(() => interleavedSections.value.flatMap(section => section.groups))

const toolDialogVisible = ref(false)
const toolDialogInitialId = ref<string | undefined>(undefined)

function openToolDialog(subMessageId: string) {
  toolDialogInitialId.value = subMessageId
  toolDialogVisible.value = true
}

async function handleCopy(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content)
    ElMessage.success(t('common.msg.copySuccess'))
  } catch {
    ElMessage.error(t('common.msg.copyFailed'))
  }
}
</script>

<style scoped>
.mobile-task-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-hint {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  font-style: italic;
  padding: 6px 0;
}
</style>
