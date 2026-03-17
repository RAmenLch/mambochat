// frontend/mambo/src/composables/useAssistantTimeline.ts

import { computed, type Ref } from 'vue';
import type { Message, SubMessage, ReviewToolContent } from '@/api/types';

/** 时间线中的一个分组：一段文本 + 跟随的工具调用 */
export interface BubbleSectionGroup {
  id: string;
  textSubMessage: SubMessage | null; // 主文本(Reasoning/Normal)。若工具先于文本出现，则可能为 null
  toolSubMessages: SubMessage[];     // 紧随其后的 McpTool 或 待审核的 ReviewTool
}

/** 大气泡内的一个区域（思考 或 正文） */
export interface BubbleSection {
  type: 'reasoning' | 'normal';
  groups: BubbleSectionGroup[];
}

/**
 * 判断一个 ReviewTool 是否已经完成审批
 */
function isReviewToolDecided(sm: SubMessage): boolean {
  if (sm.type !== 'ReviewTool') return false;
  try {
    const content = JSON.parse(sm.content) as ReviewToolContent;
    return !!content.decision;
  } catch {
    return false;
  }
}

export function useAssistantTimeline(message: Ref<Message>) {

  // 1. 过滤掉无需在时间线主轴显示的独立组件，以及已审批的 ReviewTool
  const timelineSubMessages = computed(() => {
    return message.value.sub_messages.filter(sm => {
      // 排除独立显示的类型
      if (['Usage', 'ZipHistory', 'Suggest'].includes(sm.type)) {
        return false;
      }
      // 排除已审批的 ReviewTool (审批后后端通常会生成对应的 McpTool，所以隐藏原 ReviewTool 避免重复)
      if (sm.type === 'ReviewTool' && isReviewToolDecided(sm)) {
        return false;
      }
      return true;
    }).sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  });

  // 2. 核心分组算法
  const timeline = computed(() => {
    const reasoningGroups: BubbleSectionGroup[] = [];
    const normalGroups: BubbleSectionGroup[] = [];

    let currentSection: 'reasoning' | 'normal' = 'reasoning';
    let currentGroup: BubbleSectionGroup | null = null;

    const pushCurrentGroup = () => {
      if (currentGroup) {
        if (currentSection === 'reasoning') {
          reasoningGroups.push(currentGroup);
        } else {
          normalGroups.push(currentGroup);
        }
      }
    };

    for (const sm of timelineSubMessages.value) {
      if (sm.type === 'Reasoning') {
        pushCurrentGroup();
        currentSection = 'reasoning';
        currentGroup = { id: sm.id, textSubMessage: sm, toolSubMessages: [] };
      }
      else if (sm.type === 'Normal') {
        pushCurrentGroup();
        currentSection = 'normal';
        currentGroup = { id: sm.id, textSubMessage: sm, toolSubMessages: [] };
      }
      else if (sm.type === 'McpTool' || sm.type === 'ReviewTool') {
        if (!currentGroup) {
          // 边缘情况：如果工具调用先于任何文本出现，创建一个虚拟的文本分组来容纳它
          currentGroup = { id: `${sm.id}_group`, textSubMessage: null, toolSubMessages: [] };
        }
        currentGroup.toolSubMessages.push(sm);
      }
    }

    // 推入最后一个 group
    pushCurrentGroup();

    return { reasoningGroups, normalGroups };
  });

  // 3. 导出结构化的 Section
  const reasoningSection = computed<BubbleSection | null>(() => {
    return timeline.value.reasoningGroups.length > 0
      ? { type: 'reasoning', groups: timeline.value.reasoningGroups }
      : null;
  });

  const normalSection = computed<BubbleSection | null>(() => {
    return timeline.value.normalGroups.length > 0
      ? { type: 'normal', groups: timeline.value.normalGroups }
      : null;
  });

  // 4. 导出独立的 SubMessages
  const usageSubMessages = computed(() =>
    message.value.sub_messages.filter(sm => sm.type === 'Usage')
  );

  const zipHistorySubMessage = computed(() =>
    message.value.sub_messages.find(sm => sm.type === 'ZipHistory') || null
  );

  const suggestSubMessage = computed(() =>
    message.value.sub_messages.find(sm => sm.type === 'Suggest') || null
  );

  // 5. 导出气泡状态

  /**
   * 判断整个 Reasoning 区域是否应该被最小化。
   * 规则：当且仅当所有 Reasoning 类型的子消息的 is_minimal 都为 true 时，整体才最小化。
   */
  const isReasoningMinimized = computed(() => {
    const reasoningMsgs = message.value.sub_messages.filter(sm => sm.type === 'Reasoning');
    if (reasoningMsgs.length === 0) return false;
    return reasoningMsgs.every(sm => sm.config?.is_minimal === true);
  });

  /**
   * 检查是否包含待审批的工具调用（用于控制自动最小化逻辑和 UI 提示）
   */
  const hasPendingReviews = computed(() => {
    return message.value.sub_messages.some(
      sm => sm.type === 'ReviewTool' && sm.status === 'pending_review'
    );
  });

  return {
    reasoningSection,
    normalSection,
    usageSubMessages,
    zipHistorySubMessage,
    suggestSubMessage,
    isReasoningMinimized,
    hasPendingReviews,
  };
}
