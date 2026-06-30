// frontend/mambo/src/composables/useAssistantTimeline.ts

import { computed, type Ref } from 'vue';
import type { Message, SubMessage, ReviewToolContent, AskUserContent, TaskSubStepContent } from '@/api/types';

/** 时间线中的一个分组：一段文本 + 跟随的工具调用 */
export interface BubbleSectionGroup {
  id: string;
  textSubMessage: SubMessage | null;  // 主文本(Reasoning/Normal)。若工具先于文本出现，则可能为 null
  toolSubMessages: SubMessage[];      // 紧随其后的 McpTool 或 待审核的 ReviewTool
  /** 连续多个 File 类型子消息会合并到同一个分组中，用于同行展示多张图片 */
  fileSubMessages?: SubMessage[];
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

/**
 * 判断一个 AskUser 是否已经被回答
 */
function isAskUserAnswered(sm: SubMessage): boolean {
  if (sm.type !== 'AskUser') return false;
  try {
    const content = JSON.parse(sm.content) as AskUserContent;
    return content.answers !== null && content.answers !== undefined;
  } catch {
    return false;
  }
}

export function useAssistantTimeline(message: Ref<Message>) {

  // 1. 过滤掉无需在时间线主轴显示的独立组件，以及已审批的 ReviewTool 和已回答的 AskUser，以及子代理追踪步骤
  const timelineSubMessages = computed(() => {
    return message.value.sub_messages.filter(sm => {
      // 排除独立显示的类型
      if (['Usage', 'ZipHistory', 'Suggest', 'Error'].includes(sm.type)) {
        return false;
      }
      // 排除 TaskSubStep：子代理内部步骤绑定到 task 工具气泡显示，不出现在主时间线
      if (sm.type === 'TaskSubStep') {
        return false;
      }
      // 排除已审批的 ReviewTool (审批后后端通常会生成对应的 McpTool，所以隐藏原 ReviewTool 避免重复)
      if (sm.type === 'ReviewTool' && isReviewToolDecided(sm)) {
        return false;
      }
      // 排除已回答的 AskUser (回答后后端会生成对应的 McpTool)
      if (sm.type === 'AskUser' && isAskUserAnswered(sm)) {
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
      else if (sm.type === 'File') {
        // 连续 File 类型合并到同一个分组，以便同行展示多张图片
        if (currentGroup && currentGroup.fileSubMessages && currentGroup.fileSubMessages.length > 0) {
          currentGroup.fileSubMessages.push(sm);
        } else {
          pushCurrentGroup();
          currentSection = 'normal';
          currentGroup = { id: sm.id, textSubMessage: null, toolSubMessages: [], fileSubMessages: [sm] };
        }
      }
      else if (sm.type === 'McpTool' || sm.type === 'ReviewTool' || sm.type === 'AskUser') {
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

  /**
   * 计算需要显示 ZipHistory 覆盖指示器的 group ID 集合
   * 前置条件：有 ZipHistory + 有 target_sub_msg_id
   * 规则：
   *   - McpTool/ReviewTool/AskUser → 只在包含该 tool 的 group 上标记
   *   - Normal → 在该 group + 比它早的最晚 Reasoning group 上各标记
   *   - Reasoning → 在该 group + 比它早的最晚 Normal group 上各标记
   */
  const zipCoverageGroupIds = computed<Set<string>>(() => {
    const set = new Set<string>();

    const zipSub = zipHistorySubMessage.value;
    if (!zipSub) return set;
    const targetSubMsgId = zipSub.config?.target_sub_msg_id;
    if (!targetSubMsgId) return set;

    // 找 target_sub_msg_id 对应的 sub-message
    const targetSub = message.value.sub_messages.find(sm => sm.id === targetSubMsgId);
    if (!targetSub) return set;

    const allGroups = [
      ...timeline.value.reasoningGroups,
      ...timeline.value.normalGroups,
    ];

    // 找到包含 target_sub_msg_id 的 group
    const targetGroup = allGroups.find(g => {
      if (g.textSubMessage?.id === targetSubMsgId) return true;
      if (g.toolSubMessages.some(t => t.id === targetSubMsgId)) return true;
      return false;
    });

    if (!targetGroup) return set;
    set.add(targetGroup.id);

    // McpTool/ReviewTool/AskUser → 只标记所在 group，不额外连线
    const isToolTarget = targetSub.type === 'McpTool'
      || targetSub.type === 'ReviewTool'
      || targetSub.type === 'AskUser';
    if (isToolTarget) return set;

    // Normal 或 Reasoning → 需要找另一个类型中 "比目标早且最晚" 的 group
    const targetIsReasoning = targetSub.type === 'Reasoning';
    const targetCreatedAt = new Date(targetSub.createdAt).getTime();

    const otherGroups = targetIsReasoning
      ? timeline.value.normalGroups
      : timeline.value.reasoningGroups;

    let bestMatch: BubbleSectionGroup | null = null;
    let bestTime = -Infinity;

    for (const g of otherGroups) {
      if (!g.textSubMessage) continue;
      const gTime = new Date(g.textSubMessage.createdAt).getTime();
      if (gTime < targetCreatedAt && gTime > bestTime) {
        bestTime = gTime;
        bestMatch = g;
      }
    }

    if (bestMatch) {
      set.add(bestMatch.id);
    }

    return set;
  });

  const suggestSubMessage = computed(() =>
    message.value.sub_messages.find(sm => sm.type === 'Suggest') || null
  );

  const errorSubMessages = computed(() =>
    message.value.sub_messages.filter(sm => sm.type === 'Error')
  );

  // 6. 子代理追踪步骤：按 task_group_id 分组，供 task 工具气泡的 SubAgentPanel 使用
  const taskSubAgentGroups = computed(() => {
    const map = new Map<string, SubMessage[]>();
    for (const sm of message.value.sub_messages) {
      if (sm.type !== 'TaskSubStep') continue;
      const gid = sm.config?.task_group_id;
      if (!gid) continue;
      if (!map.has(gid)) map.set(gid, []);
      map.get(gid)!.push(sm);
    }
    // 组内按 step_order 排序
    for (const msgs of map.values()) {
      msgs.sort((a, b) => {
        try {
          const ca: TaskSubStepContent = JSON.parse(a.content);
          const cb: TaskSubStepContent = JSON.parse(b.content);
          return ca.step_order - cb.step_order;
        } catch {
          return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
        }
      });
    }
    return map;
  });

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
    zipCoverageGroupIds,
    suggestSubMessage,
    errorSubMessages,
    isReasoningMinimized,
    hasPendingReviews,
    taskSubAgentGroups,
  };
}
