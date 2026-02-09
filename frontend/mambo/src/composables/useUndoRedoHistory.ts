import { reactive, computed, watch } from 'vue';
import type { Ref } from 'vue';
import {
  getHistoryByChatId,
  addHistoryEntry,
  updateHistoryEntry,
  deleteHistoryEntry,
  getHistoryCountByChatId,
  getOldestHistoryEntryByChatId,
  getGlobalHistoryCount,
  getOldestGlobalHistoryEntry,
  getNonLatestHistoryEntries,
} from '@/services/indexedDBService';

// --- Constants ---
const GLOBAL_HISTORY_LIMIT = 200;
const CHAT_HISTORY_LIMIT = 50;
const MAX_TOTAL_HISTORY_SIZE = 50 * 1024 * 1024; // 50MB

/**
 * 内存中的历史记录条目结构
 * 包含 dbId 以便在发生分叉(Fork)时清理数据库中的无效"未来"记录
 */
interface HistoryEntry {
  itemId: string;
  content: string;
  dbId?: number; // 对应 IndexedDB 的主键
}

/**
 * 创建一个响应式的、基于 IndexedDB 持久化的历史记录管理器。
 *
 * @param currentItemId - 一个响应式的 Ref，代表当前激活项的ID（例如，当前会话的ID）。
 * @returns 返回一组用于操作历史记录的方法和一个计算属性。
 */
export function useUndoRedoHistory(currentItemId: Ref<string | null>) {
  // 内存中的响应式状态，仅保留当前会话的历史
  const history = reactive<{
    stack: HistoryEntry[];
    pointer: number;
    isLoading: boolean;
  }>({
    stack: [],
    pointer: -1,
    isLoading: false,
  });

  /**
   * 从 IndexedDB 加载当前会话的历史记录到内存
   */
  const _loadHistory = async (id: string) => {
    history.isLoading = true;
    try {
      const dbEntries = await getHistoryByChatId(id);

      // 重建内存堆栈
      history.stack = dbEntries.map(e => ({
        itemId: e.chatId,
        content: e.content,
        dbId: e.id
      }));

      // 将指针移动到堆栈末尾（即最新状态）
      history.pointer = history.stack.length - 1;
    } catch (error) {
      console.error('Failed to load history from IndexedDB:', error);
      // 出错时保持空状态，不阻塞 UI
      history.stack = [];
      history.pointer = -1;
    } finally {
      history.isLoading = false;
    }
  };

  /**
   * 监听 currentItemId 变化，切换会话时重新加载历史
   */
  watch(currentItemId, (newId) => {
    if (newId) {
      _loadHistory(newId);
    } else {
      history.stack = [];
      history.pointer = -1;
    }
  }, { immediate: true });

  /**
   * 计算字符串的 UTF-8 字节大小
   */
  const _getByteSize = (str: string): number => {
    return new Blob([str]).size;
  };

  /**
   * 异步执行容量管理策略
   * 包括：数量限制剔除、50MB 容量限制保护
   */
  const _enforceLimits = async (chatId: string) => {
    try {
      // 1. 单个会话数量限制 (Chat Limit > 50)
      const chatCount = await getHistoryCountByChatId(chatId);
      if (chatCount > CHAT_HISTORY_LIMIT) {
        const oldest = await getOldestHistoryEntryByChatId(chatId);
        if (oldest && oldest.id) {
          await deleteHistoryEntry(oldest.id);
        }
      }

      // 2. 全局数量限制 (Global Limit > 200)
      const globalCount = await getGlobalHistoryCount();
      if (globalCount > GLOBAL_HISTORY_LIMIT) {
        const oldestGlobal = await getOldestGlobalHistoryEntry();
        if (oldestGlobal && oldestGlobal.id) {
          await deleteHistoryEntry(oldestGlobal.id);
        }
      }

      // 3. 50MB 容量限制保护 (仅统计非最新草稿)
      const nonLatestEntries = await getNonLatestHistoryEntries();
      let totalSize = nonLatestEntries.reduce((sum, entry) => sum + entry.size, 0);

      if (totalSize > MAX_TOTAL_HISTORY_SIZE) {
        // 从最旧的记录开始剔除，直到容量满足要求
        for (const entry of nonLatestEntries) {
          if (totalSize <= MAX_TOTAL_HISTORY_SIZE) break;
          if (entry.id) {
            await deleteHistoryEntry(entry.id);
            totalSize -= entry.size;
          }
        }
      }
    } catch (error) {
      console.warn('Failed to enforce history limits:', error);
    }
  };

  /**
   * 保存指定项的新草稿内容。
   * 此操作会异步写入 IndexedDB 并触发容量检查。
   * @param itemId - 草稿所属项的ID。
   * @param content - 新的草稿内容。
   */
  const saveDraft = async (itemId: string, content: string) => {
    if (!itemId) return;

    const latestEntry = history.stack[history.pointer];
    // 避免连续存入完全相同的草稿
    if (latestEntry && latestEntry.itemId === itemId && latestEntry.content === content) {
      return;
    }

    // --- 1. 内存操作 (Optimistic UI Update) ---

    // 如果指针不在栈顶，说明发生了历史分叉(Fork)
    // 需要清理掉被丢弃的"未来"记录，保持历史线性的直观性
    const futureEntries = history.stack.slice(history.pointer + 1);
    if (futureEntries.length > 0) {
      history.stack.splice(history.pointer + 1);

      // 异步清理 DB 中的孤儿记录
      Promise.all(futureEntries.map(e => e.dbId ? deleteHistoryEntry(e.dbId) : Promise.resolve()))
        .catch(err => console.warn('Failed to prune detached history entries:', err));
    }

    // 推入新记录到内存栈
    const newEntryInMemory: HistoryEntry = { itemId, content }; // dbId 暂时未知
    history.stack.push(newEntryInMemory);

    // 内存中维持单个会话的上限，避免 UI 列表无限增长
    if (history.stack.length > CHAT_HISTORY_LIMIT) {
      history.stack.shift();
    }

    history.pointer = history.stack.length - 1;

    // --- 2. 异步持久化 (IndexedDB) ---
    try {
      // 查找并更新旧的 isLatest 记录
      const dbHistory = await getHistoryByChatId(itemId);
      // Fix: Check for strict equality or truthiness, db now stores 1/0
      const oldLatest = dbHistory.find(e => e.isLatest === 1);
      if (oldLatest) {
        oldLatest.isLatest = 0; // Fix: boolean -> number
        await updateHistoryEntry(oldLatest);
      }

      // 写入新记录
      const size = _getByteSize(content);
      const newDbId = await addHistoryEntry({
        chatId: itemId,
        content,
        timestamp: Date.now(),
        size,
        isLatest: 1 // Fix: boolean -> number
      });

      // 回填 ID 到内存对象，以便后续操作（如 undo 后的分叉清理）
      if (newDbId) {
        newEntryInMemory.dbId = newDbId;
      }

      // 执行容量限制策略
      await _enforceLimits(itemId);

    } catch (error) {
      console.error('Failed to persist draft to IndexedDB:', error);
    }
  };

  /**
   * 撤销到指定项的上一个草稿状态。
   * 仅操作内存指针，不产生新记录。
   */
  const undo = (itemId: string) => {
    if (!itemId || history.pointer <= 0) return;
    history.pointer--;
  };

  /**
   * 重做到指定项的下一个草稿状态。
   * 仅操作内存指针，不产生新记录。
   */
  const redo = (itemId: string) => {
    if (!itemId || history.pointer >= history.stack.length - 1) return;
    history.pointer++;
  };

  /**
   * 计算属性，用于获取当前激活项的最新草稿。
   */
  const currentDraft = computed((): string => {
    // 优先返回指针指向的内容
    if (history.pointer >= 0 && history.stack[history.pointer]) {
      return history.stack[history.pointer].content;
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
