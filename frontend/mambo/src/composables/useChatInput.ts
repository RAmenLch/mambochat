// frontend/mambo/src/composables/useChatInput.ts

import { ref, watch, computed, reactive } from 'vue';
import { useUndoRedoHistory } from './useUndoRedoHistory';
import { debounce } from 'lodash-es';
import type { Ref } from 'vue';
import type { FileResponse } from '@/api/types';

/**
 * 定义多部分输入的分区结构。
 */
interface Partition {
  id: number;
  content: string;
}

/**
 * 管理聊天输入的复杂逻辑，包括多模式切换、草稿状态和撤销/重做功能。
 * 这是一个与UI紧密相关的Composable，旨在简化ChatWindow组件的逻辑。
 *
 * @param currentChatId - 一个响应式的 Ref，代表当前激活会话的ID。
 * @returns 返回一组用于驱动聊天输入区域的响应式状态和方法。
 */
export function useChatInput(currentChatId: Ref<string | null>) {
  // --- 内部状态 ---

  // 1. 底层历史记录引擎 (仅用于文本草稿)
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
  const uploadedFiles = ref<FileResponse[]>([]);

  // 3. 跨会话记住用户的输入模式偏好
  const chatInputModeState = reactive<Record<string, boolean>>({});

  // --- 核心逻辑 ---

  // 4. 防抖保存，避免过于频繁地写入历史记录
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

  // 7. 监听会话ID变化，加载新会话的草稿和输入模式
  watch(currentChatId, (newId, oldId) => {
    if (newId && newId !== oldId) {
      uploadedFiles.value = [];
      isMultiPartMode.value = chatInputModeState[newId] ?? false;
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
      } else {
        singlePartDraft.value = (draft && draft.startsWith('[')) ? '' : draft;
      }
    }
  }, { immediate: true });

  // 8. 封装模式切换的业务逻辑
  const toggleMultiPartMode = () => {
    if (!currentChatId.value) return;

    const nextMode = !isMultiPartMode.value;
    if (nextMode) {
      multiPartDraft.value = [{ id: Date.now(), content: singlePartDraft.value }];
    } else {
      singlePartDraft.value = multiPartDraft.value.map(p => p.content).join('\n--------------------------\n');
    }
    isMultiPartMode.value = nextMode;
    chatInputModeState[currentChatId.value] = nextMode;

    debouncedSave.cancel();
    debouncedSave(nextMode ? JSON.stringify(multiPartDraft.value) : singlePartDraft.value);
  };

  // 9. 封装撤销/重做，自动绑定当前会话ID
  const undo = () => {
    if (currentChatId.value) undoHistory(currentChatId.value);
  };
  const redo = () => {
    if (currentChatId.value) redoHistory(currentChatId.value);
  };

  // 10. 暴露一个重置方法，在消息发送后调用
  const resetDraft = () => {
    singlePartDraft.value = '';
    multiPartDraft.value = [{ id: Date.now(), content: '' }];
    uploadedFiles.value = [];
    debouncedSave('');
  };

  // 11. 文件管理方法
  const addUploadedFile = (file: FileResponse) => {
    uploadedFiles.value.push(file);
  };

  const removeUploadedFile = (fileId: string) => {
    const index = uploadedFiles.value.findIndex(f => f.id === fileId);
    if (index !== -1) {
      uploadedFiles.value.splice(index, 1);
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
      }
      const lastPartition = multiPartDraft.value[multiPartDraft.value.length - 1];
      const currentContent = lastPartition.content.trim();
      const separator = currentContent.length > 0 ? '\n' : '';
      lastPartition.content += separator + content;
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
    uploadedFiles,

    // 计算属性
    currentUserInputText: computed((): string => isMultiPartMode.value
      ? multiPartDraft.value.map(p => p.content).join('\n')
      : singlePartDraft.value
    ),
    isReadyToSend: computed((): boolean =>
      (isMultiPartMode.value
        ? multiPartDraft.value.some(p => p.content.trim() !== '')
        : singlePartDraft.value.trim() !== '')
      || uploadedFiles.value.length > 0
    ),

    // 方法
    toggleMultiPartMode,
    undo,
    redo,
    resetDraft,
    addUploadedFile,
    removeUploadedFile,
    appendContentToDraft,
  };
}
