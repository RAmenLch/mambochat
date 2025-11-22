// frontend/mambo/src/composables/useUndoRedoHistory.ts

import { reactive, computed } from 'vue';
import type { Ref } from 'vue';

const GLOBAL_HISTORY_LIMIT = 200;
const CHAT_HISTORY_LIMIT = 50;
const STORAGE_KEY = 'mambo_undoRedoHistory';

/**
 * 历史记录中单个条目的结构。
 */
interface HistoryEntry {
  itemId: string;
  content: string;
}

/**
 * 创建一个响应式的、支持撤销/重做的历史记录管理器。
 *
 * @param currentItemId - 一个响应式的 Ref，代表当前激活项的ID（例如，当前会话的ID）。
 *                        `currentDraft` 计算属性会根据此ID的变化而自动更新。
 * @returns 返回一组用于操作历史记录的方法和一个计算属性。
 */
export function useUndoRedoHistory(currentItemId: Ref<string | null>) {
  const history = reactive<{
    stack: HistoryEntry[];
    pointer: number;
  }>({
    stack: [],
    pointer: -1,
  });

  /**
   * 将当前历史记录状态持久化到 localStorage。
   */
  const _persistHistory = () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
    } catch (error) {
      console.error('Failed to save history to localStorage:', error);
    }
  };

  /**
   * 从 localStorage 加载历史记录状态。
   */
  const _loadHistory = () => {
    try {
      const storedHistory = localStorage.getItem(STORAGE_KEY);
      if (storedHistory) {
        const parsed = JSON.parse(storedHistory);
        history.stack = parsed.stack || [];
        history.pointer = parsed.pointer ?? -1;
      }
    } catch (error) {
      console.error('Failed to load history from localStorage:', error);
      // 如果加载失败，清空存储以防下次出错
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  // 初始化时加载历史记录
  _loadHistory();

  /**
   * 将一个新条目推入历史堆栈。
   * 此操作会清除所有"未来"的重做步骤，并管理堆栈的大小限制。
   */
  const _pushToHistory = (entry: HistoryEntry) => {
    // 如果指针不在栈顶，说明进行过撤销操作，此时新的输入会覆盖掉“未来”的历史
    if (history.pointer < history.stack.length - 1) {
      history.stack.splice(history.pointer + 1);
    }

    history.stack.push(entry);

    // 应用单个会话的历史限制
    const itemEntries = history.stack.filter(e => e.itemId === entry.itemId);
    if (itemEntries.length > CHAT_HISTORY_LIMIT) {
      const oldestIndex = history.stack.findIndex(e => e.itemId === entry.itemId);
      if (oldestIndex !== -1) {
        history.stack.splice(oldestIndex, 1);
      }
    }

    // 应用全局历史限制
    if (history.stack.length > GLOBAL_HISTORY_LIMIT) {
      history.stack.shift();
    }

    // 更新指针到栈顶
    history.pointer = history.stack.length - 1;
    _persistHistory();
  };

  /**
   * 保存指定项的新草稿内容。
   * @param itemId - 草稿所属项的ID。
   * @param content - 新的草稿内容。
   */
  const saveDraft = (itemId: string, content: string) => {
    if (!itemId) return;

    const latestEntry = history.stack[history.pointer];
    // 避免连续存入完全相同的草稿
    if (latestEntry && latestEntry.itemId === itemId && latestEntry.content === content) {
      return;
    }

    _pushToHistory({ itemId, content });
  };

  /**
   * 撤销到指定项的上一个草稿状态。
   * @param itemId - 要执行撤销操作的项的ID。
   */
  const undo = (itemId: string) => {
    if (!itemId || history.pointer < 0) return;

    // 从当前指针的前一个位置开始，向后查找属于同一项的记录
    for (let i = history.pointer - 1; i >= 0; i--) {
      if (history.stack[i].itemId === itemId) {
        history.pointer = i;
        _persistHistory();
        return;
      }
    }
  };

  /**
   * 重做到指定项的下一个草稿状态。
   * @param itemId - 要执行重做操作的项的ID。
   */
  const redo = (itemId: string) => {
    if (!itemId || history.pointer >= history.stack.length - 1) return;

    // 从当前指针的后一个位置开始，向前查找属于同一项的记录
    for (let i = history.pointer + 1; i < history.stack.length; i++) {
        if (history.stack[i].itemId === itemId) {
            history.pointer = i;
            _persistHistory();
            return;
        }
    }
  };

  /**
   * 计算属性，用于获取当前激活项的最新草稿。
   * 如果历史记录为空或找不到对应项的草稿，则返回空字符串。
   */
  const currentDraft = computed((): string => {
    const id = currentItemId.value;
    if (!id || history.pointer < 0) return '';

    // 从当前指针位置向后查找属于当前会话的最新草稿
    for (let i = history.pointer; i >= 0; i--) {
      const entry = history.stack[i];
      if (entry.itemId === id) {
        return entry.content;
      }
    }
    return '';
  });

  return {
    saveDraft,
    undo,
    redo,
    currentDraft,
  };
}
