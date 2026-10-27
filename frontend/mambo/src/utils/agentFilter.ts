// frontend/mambo/src/utils/agentFilter.ts

import type { Chat } from '@/api/types';

export const AGENT_FILTER_ALL = 'all';
export const AGENT_FILTER_NORMAL = 'normal';
export const AGENT_FILTER_UNKNOWN = 'unknown';

export const AGENT_FILTER_STORAGE_KEY = 'mambo_chat_agent_filter';

/**
 * 单个会话节点是否命中筛选档位。
 * - all：全部
 * - normal：未绑定 Agent 的会话
 * - unknown：绑定的 Agent 已不存在（悬空引用）
 * - 其他值：具体 Agent ID
 */
export function isChatMatchedByAgentFilter(
  chat: Chat,
  filter: string,
  knownAgentIds: ReadonlySet<string>
): boolean {
  if (filter === AGENT_FILTER_ALL) {
    return true;
  }

  const agentId = chat.agentId ?? null;

  if (filter === AGENT_FILTER_NORMAL) {
    return !agentId;
  }

  if (filter === AGENT_FILTER_UNKNOWN) {
    return !!agentId && !knownAgentIds.has(agentId);
  }

  return agentId === filter;
}

/**
 * 会话列表是否包含悬空的 Agent 引用（用于决定"已删除 Agent"档位是否出现）。
 */
export function hasDanglingAgentRef(
  list: readonly Chat[],
  knownAgentIds: ReadonlySet<string>
): boolean {
  return list.some(
    item => item.itemType === 'chat' && !!item.agentId && !knownAgentIds.has(item.agentId)
  );
}

/**
 * 按 Agent 筛选会话列表（仅显示层过滤，不裁剪 store 数据）。
 * - 普通文件夹：始终保留（未加载内容在展开后由 computed 重新计算）
 * - 群组文件夹（folderType='group'）：未加载时保留；已加载时仅当存在命中成员才保留
 * - 会话：按档位匹配；群成员会话同样参与匹配
 */
export function filterChatListByAgent(
  list: readonly Chat[],
  filter: string,
  knownAgentIds: ReadonlySet<string>,
  loadedFolderIds: ReadonlySet<string>
): Chat[] {
  if (filter === AGENT_FILTER_ALL) {
    return list as Chat[];
  }

  const matchedChatIds = new Set<string>();
  const groupsWithMatch = new Set<string>();

  for (const item of list) {
    if (item.itemType !== 'chat') {
      continue;
    }
    if (!isChatMatchedByAgentFilter(item, filter, knownAgentIds)) {
      continue;
    }
    matchedChatIds.add(item.id);
    if (item.parentId) {
      groupsWithMatch.add(item.parentId);
    }
  }

  return list.filter(item => {
    if (item.itemType !== 'folder') {
      return matchedChatIds.has(item.id);
    }
    if (item.folderType !== 'group') {
      return true;
    }
    return !loadedFolderIds.has(item.id) || groupsWithMatch.has(item.id);
  });
}
