// frontend/mambo/src/composables/useChatInput.ts

import { ref, watch, computed, reactive } from 'vue';
import { useUndoRedoHistory } from './useUndoRedoHistory';
import { debounce } from 'lodash-es';
import type { Ref } from 'vue';
import type { FileResponse, Resource } from '@/api/types';

/**
 * 定义多部分输入的分区结构。
 */
interface Partition {
  id: number;
  content: string;
}

/**
 * 定义持久化到 localStorage 的单个会话输入状态的结构。
 */
interface ChatInputState {
  isMultiPartMode: boolean;
  uploadedFiles: FileResponse[];
  attachedSubmessageResources: Resource[];
}

const CACHE_STORAGE_KEY = 'mambo_chatInputCache';

/**
 * 管理聊天输入的复杂逻辑，包括多模式切换、草稿状态和撤销/重做功能。
 * 这是一个与UI紧密相关的Composable，旨在简化ChatWindow组件的逻辑。
 *
 * @param currentChatId - 一个响应式的 Ref，代表当前激活会话的ID。
 * @returns 返回一组用于驱动聊天输入区域的响应式状态和方法。
 */
export function useChatInput(currentChatId: Ref<string | null>) {
  // --- 内部状态 ---

  // 1. 底层历史记录引擎 (仅用于文本草稿)，已配置为使用 localStorage
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

  // 3. 用于持久化输入状态的缓存对象
  const chatInputCache = reactive<Record<string, ChatInputState>>({});

  // 初始化时从 localStorage 加载缓存
  try {
    const storedCache = localStorage.getItem(CACHE_STORAGE_KEY);
    if (storedCache) {
      Object.assign(chatInputCache, JSON.parse(storedCache));
    }
  } catch (error) {
    console.error('Failed to load chat input cache from localStorage:', error);
    localStorage.removeItem(CACHE_STORAGE_KEY);
  }

  // --- 核心逻辑 ---

  /**
   * 将当前会话的输入状态（模式、文件、资源）保存到缓存和 localStorage。
   */
  const _saveCurrentChatState = () => {
    const id = currentChatId.value;
    if (!id) return;

    if (!chatInputCache[id]) {
      chatInputCache[id] = {
        isMultiPartMode: false,
        uploadedFiles: [],
        attachedSubmessageResources: [],
      };
    }

    chatInputCache[id].isMultiPartMode = isMultiPartMode.value;
    chatInputCache[id].uploadedFiles = JSON.parse(JSON.stringify(uploadedFiles.value));
    chatInputCache[id].attachedSubmessageResources = JSON.parse(JSON.stringify(attachedSubmessageResources.value));

    try {
      localStorage.setItem(CACHE_STORAGE_KEY, JSON.stringify(chatInputCache));
    } catch (error) {
      console.error('Failed to save chat input cache to localStorage:', error);
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

  // 7. 监听会话ID变化，加载新会话的草稿和输入状态
  watch(currentChatId, (newId, oldId) => {
    if (newId && newId !== oldId) {
      const cachedState = chatInputCache[newId];

      if (cachedState) {
        isMultiPartMode.value = cachedState.isMultiPartMode;
        uploadedFiles.value = cachedState.uploadedFiles;
        attachedSubmessageResources.value = cachedState.attachedSubmessageResources;
      } else {
        isMultiPartMode.value = false;
        uploadedFiles.value = [];
        attachedSubmessageResources.value = [];
      }

      activePartitionIndex.value = 0;
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
    singlePartDraft.value = '';
    multiPartDraft.value = [{ id: Date.now(), content: '' }];
    activePartitionIndex.value = 0;
    uploadedFiles.value = [];
    // attachedSubmessageResources.value = []; //消息模板是不会在发送后清空的,以后记住
    debouncedSave('');
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
      // Fallback to empty string if singlePartDraft is null/undefined
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
