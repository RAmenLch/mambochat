import { ref, watch, computed } from 'vue';
import { useUndoRedoHistory } from './useUndoRedoHistory';
import { debounce } from 'lodash-es';
import type { Ref } from 'vue';
import type { FileResponse, Resource } from '@/api/types';
import {
  getInputCache,
  setInputCache,
  deleteInputCache,
  getInputCacheCount,
  getOldestInputCache
} from '@/services/indexedDBService';

/**
 * 定义多部分输入的分区结构。
 */
interface Partition {
  id: number;
  content: string;
}

/**
 * 管理聊天输入的复杂逻辑，包括多模式切换、草稿状态和撤销/重做功能。
 * 使用 IndexedDB 进行持久化存储，并实施 LRU 缓存淘汰策略。
 *
 * @param currentChatId - 一个响应式的 Ref，代表当前激活会话的ID。
 * @returns 返回一组用于驱动聊天输入区域的响应式状态和方法。
 */
export function useChatInput(currentChatId: Ref<string | null>) {
  // --- 内部状态 ---

  // 1. 底层历史记录引擎 (仅用于文本草稿)，已重构为使用 IndexedDB
  const {
    saveDraft: saveHistory,
    undo: undoHistory,
    redo: redoHistory,
    currentDraft: rawDraftFromHistory,
  } = useUndoRedoHistory(currentChatId);

  // 2. 输入模式和各自的草稿状态
  const isMultiPartMode = ref(false);
  const singlePartDraft = ref('');
  const multiPartDraft = ref<Partition[]>([{ id: Date.now(), content: '' }]);
  const activePartitionIndex = ref(0);
  const uploadedFiles = ref<FileResponse[]>([]);
  const attachedSubmessageResources = ref<Resource[]>([]);

  // 3. 缓存容量限制常量
  const CACHE_LIMIT = 10;

  // --- 核心逻辑 ---

  /**
   * 将当前会话的输入状态（模式、文件、资源）保存到 IndexedDB。
   * 包含 LRU 淘汰逻辑：若达到上限且为新记录，删除最旧记录。
   */
  const _saveCurrentChatState = async () => {
    const id = currentChatId.value;
    if (!id) return;

    try {
      // 检查是否已存在记录，以区分新增还是更新
      const existingEntry = await getInputCache(id);

      // 如果是新增记录，且达到容量限制，执行 LRU 淘汰
      if (!existingEntry) {
        const count = await getInputCacheCount();
        if (count >= CACHE_LIMIT) {
          const oldest = await getOldestInputCache();
          if (oldest) {
            await deleteInputCache(oldest.chatId);
          }
        }
      }

      // 保存当前状态，更新时间戳以刷新 LRU 顺序
      await setInputCache({
        chatId: id,
        isMultiPartMode: isMultiPartMode.value,
        uploadedFiles: JSON.parse(JSON.stringify(uploadedFiles.value)),
        attachedSubmessageResources: JSON.parse(JSON.stringify(attachedSubmessageResources.value)),
        timestamp: Date.now(),
      });
    } catch (error) {
      console.error('Failed to save chat input cache to IndexedDB:', error);
    }
  };

  // 4. 防抖保存文本草稿，避免过于频繁地写入历史记录
  const debouncedSave = debounce((content: string) => {
    if (currentChatId.value) {
      saveHistory(currentChatId.value, content);
    }
  }, 300);

  // 5. 监听当前模式下的草稿变化，并触发防抖保存
  watch(singlePartDraft, (newInput) => {
    if (!isMultiPartMode.value) {
      debouncedSave(newInput);
    }
  });
  watch(multiPartDraft, (newPartitions) => {
    if (isMultiPartMode.value) {
      debouncedSave(JSON.stringify(newPartitions));
    }
  }, { deep: true });

  // 6. 监听来自历史记录的变化（例如撤销/重做），并更新UI草稿
  watch(rawDraftFromHistory, (newDraft) => {
    if (isMultiPartMode.value) {
      try {
        const parsed = JSON.parse(newDraft);
        if (Array.isArray(parsed) && JSON.stringify(parsed) !== JSON.stringify(multiPartDraft.value)) {
          multiPartDraft.value = parsed.length > 0 ? parsed : [{ id: Date.now(), content: '' }];
        }
      } catch {
        multiPartDraft.value = [{ id: Date.now(), content: '' }];
      }
    } else {
      if (singlePartDraft.value !== newDraft) {
        singlePartDraft.value = newDraft;
      }
    }
  });

  // 7. 监听会话ID变化，从 IndexedDB 加载新会话的输入状态
  watch(currentChatId, async (newId, oldId) => {
    if (newId && newId !== oldId) {
      // 重置为默认状态，等待异步加载
      isMultiPartMode.value = false;
      uploadedFiles.value = [];
      attachedSubmessageResources.value = [];
      activePartitionIndex.value = 0;

      // 异步加载缓存
      try {
        const cachedState = await getInputCache(newId);
        if (cachedState) {
          isMultiPartMode.value = cachedState.isMultiPartMode;
          uploadedFiles.value = cachedState.uploadedFiles;
          attachedSubmessageResources.value = cachedState.attachedSubmessageResources;
        }
      } catch (error) {
        console.error('Failed to load chat input cache:', error);
      }

      // 处理文本草稿（从历史记录加载）
      // 注意：rawDraftFromHistory 会由 useUndoRedoHistory 内部的 watcher 自动更新
      const draft = rawDraftFromHistory.value;
      if (isMultiPartMode.value) {
        if (draft && draft.startsWith('[')) {
          try {
            multiPartDraft.value = JSON.parse(draft);
          } catch {
            multiPartDraft.value = [{ id: Date.now(), content: '' }];
          }
        } else {
          multiPartDraft.value = [{ id: Date.now(), content: '' }];
        }
        singlePartDraft.value = '';
      } else {
        singlePartDraft.value = (draft && draft.startsWith('[')) ? '' : draft;
        multiPartDraft.value = [{ id: Date.now(), content: '' }];
      }
    }
  }, { immediate: true });

  // 8. 监听输入状态的变化并自动持久化
  // 注意：resetDraft 修改 uploadedFiles 时也会触发此 watcher，从而更新 DB
  watch([isMultiPartMode, uploadedFiles, attachedSubmessageResources], _saveCurrentChatState, { deep: true });

  // 9. 封装模式切换的业务逻辑
  const toggleMultiPartMode = () => {
    if (!currentChatId.value) return;

    const nextMode = !isMultiPartMode.value;
    if (nextMode) {
      multiPartDraft.value = [{ id: Date.now(), content: singlePartDraft.value }];
    } else {
      singlePartDraft.value = multiPartDraft.value.map(p => p.content).join('\n--------------------------\n');
    }
    isMultiPartMode.value = nextMode;
    activePartitionIndex.value = 0;

    debouncedSave.cancel();
    debouncedSave(nextMode ? JSON.stringify(multiPartDraft.value) : singlePartDraft.value);
  };

  // 10. 封装撤销/重做，自动绑定当前会话ID
  const undo = () => {
    if (currentChatId.value) undoHistory(currentChatId.value);
  };
  const redo = () => {
    if (currentChatId.value) redoHistory(currentChatId.value);
  };

  // 11. 暴露一个重置方法，在消息发送后调用
  const resetDraft = () => {
    // 清空文本草稿和文件
    singlePartDraft.value = '';
    multiPartDraft.value = [{ id: Date.now(), content: '' }];
    activePartitionIndex.value = 0;
    uploadedFiles.value = [];

    // 注意：attachedSubmessageResources (消息模板) 不在此处清空，需保留以便连续使用

    // 清空历史记录中的当前草稿
    debouncedSave('');

    // 这里的状态变更(uploadedFiles清空)会触发 watcher，
    // 进而调用 _saveCurrentChatState 将最新的"空文件+保留模板"状态同步到 IndexedDB
  };

  // 12. 文件管理方法
  const addUploadedFile = (file: FileResponse) => {
    uploadedFiles.value.push(file);
  };

  const removeUploadedFile = (fileId: string) => {
    const index = uploadedFiles.value.findIndex(f => f.id === fileId);
    if (index !== -1) {
      uploadedFiles.value.splice(index, 1);
    }
  };

  // 13. SubMessage 模板管理方法
  const addAttachedResource = (resource: Resource) => {
    if (!attachedSubmessageResources.value.some(r => r.id === resource.id)) {
      attachedSubmessageResources.value.push(resource);
    }
  };

  const removeAttachedResource = (resourceId: string) => {
    const index = attachedSubmessageResources.value.findIndex(r => r.id === resourceId);
    if (index !== -1) {
      attachedSubmessageResources.value.splice(index, 1);
    }
  };

  /**
   * 将内容追加到当前激活的输入框草稿中。
   * @param content - 要追加的文本内容。
   */
  const appendContentToDraft = (content: string) => {
    if (isMultiPartMode.value) {
      if (multiPartDraft.value.length === 0) {
        multiPartDraft.value.push({ id: Date.now(), content: '' });
        activePartitionIndex.value = 0;
      }
      const currentPartition = multiPartDraft.value[activePartitionIndex.value];
      if (currentPartition) {
        const currentContent = currentPartition.content.trim();
        const separator = currentContent.length > 0 ? '\n' : '';
        currentPartition.content += separator + content;
      }
    } else {
      const currentContent = singlePartDraft.value.trim();
      const separator = currentContent.length > 0 ? '\n' : '';
      singlePartDraft.value += separator + content;
    }
  };

  // --- 对外暴露的API ---
  return {
    // 状态
    isMultiPartMode,
    singlePartDraft,
    multiPartDraft,
    activePartitionIndex,
    uploadedFiles,
    attachedSubmessageResources,

    // 计算属性
    currentUserInputText: computed((): string => isMultiPartMode.value
      ? multiPartDraft.value.map(p => p.content).join('\n')
      : singlePartDraft.value ?? ''
    ),
    isReadyToSend: computed((): boolean =>
      (isMultiPartMode.value
        ? multiPartDraft.value.some(p => p.content.trim() !== '')
        : (singlePartDraft.value ?? '').trim() !== '')
      || uploadedFiles.value.length > 0
    ),

    // 方法
    toggleMultiPartMode,
    undo,
    redo,
    resetDraft,
    addUploadedFile,
    removeUploadedFile,
    addAttachedResource,
    removeAttachedResource,
    appendContentToDraft,
  };
}
