// frontend/mambo/src/composables/useKBFileTask.ts

import { ref, computed, onUnmounted } from 'vue';
import { useResourceStore } from '@/stores/resourceStore';
import { subscribeToKBFileProgress } from '@/api/kbService';
import type {
  KBChunkStatus,
  KBSplitterConfig,
  KBResumeConflictErrorDetail,
  KBRunTaskRequest,
} from '@/api/types';

/**
 * 知识库文件任务管理 Composable
 * 封装文件切分、嵌入任务的流程控制、状态管理及 SSE 进度订阅。
 */
export function useKBFileTask(resourceId: string) {
  const resourceStore = useResourceStore();

  // --- State ---

  /**
   * 任务状态信息
   * 包含切片总数、完成数、失败数及当前文件状态
   */
  const statusInfo = ref<KBChunkStatus | null>(null);

  /**
   * 乐观更新状态
   * 用于在 API 调用发起前立即更新 UI，提升响应速度
   */
  const optimisticStatus = ref<'STARTING' | 'STOPPING' | null>(null);

  /**
   * 提交中状态
   * 用于控制按钮的 loading 状态，防止重复提交
   */
  const isSubmitting = ref(false);

  /**
   * SSE 连接控制器
   * 用于在组件卸载或切换资源时中断连接
   */
  let sseController: AbortController | null = null;

  // --- Computed ---

  /**
   * 是否正在处理中
   * 综合了乐观状态和后端返回的实际状态
   */
  const isProcessing = computed(() => {
    if (optimisticStatus.value === 'STARTING') return true;
    const s = statusInfo.value?.file_status;
    if (!s) return false;
    return ['CLEANING', 'READING', 'SPLITTING', 'EMBEDDING'].includes(s);
  });

  /**
   * 是否已有索引数据
   * 用于判断是否需要提示用户覆盖旧数据
   */
  const hasIndexedData = computed(() => {
    return statusInfo.value?.file_status === 'COMPLETED' || (statusInfo.value?.total_chunks || 0) > 0;
  });

  /**
   * 是否可以恢复任务
   * 仅在失败或停止状态下允许恢复
   */
  const canResume = computed(() => {
    if (optimisticStatus.value) return false;
    if (!statusInfo.value) return false;
    const s = statusInfo.value.file_status;
    return s === 'FAILED' || s === 'STOPPED';
  });

  /**
   * 进度百分比
   */
  const progressPercentage = computed(() => {
    if (!statusInfo.value || statusInfo.value.total_chunks === 0) return 0;
    const percent = (statusInfo.value.completed_chunks / statusInfo.value.total_chunks) * 100;
    return Math.min(Math.round(percent), 100);
  });

  // --- Methods ---

  /**
   * 启动 SSE 进度订阅
   * 自动处理连接建立、消息接收、错误处理及连接关闭
   */
  const startSSE = () => {
    stopSSE();

    sseController = subscribeToKBFileProgress({
      resourceId,
      onMessage: (data) => {
        optimisticStatus.value = null;
        statusInfo.value = data;
      },
      onError: (err) => {
        console.error('[KBFileTask] SSE Error:', err);
        stopSSE();
        optimisticStatus.value = null;
      },
      onClose: () => {
        sseController = null;
      },
    });
  };

  /**
   * 停止 SSE 订阅
   */
  const stopSSE = () => {
    if (sseController) {
      sseController.abort();
      sseController = null;
    }
  };

  /**
   * 保存切分配置
   * 调用 Store 更新配置，并同步本地状态
   */
  const saveConfig = async (config: KBSplitterConfig): Promise<boolean> => {
    isSubmitting.value = true;
    try {
      await resourceStore.updateKBFileConfig(resourceId, config);
      return true;
    } catch (error) {
      console.error('[KBFileTask] Save config failed', error);
      return false;
    } finally {
      isSubmitting.value = false;
    }
  };

  /**
   * 启动任务
   * @param config 当前表单配置
   * @param isDirty 配置是否发生变更
   */
  const startTask = async (config: KBSplitterConfig, isDirty: boolean) => {
    // 1. 如果配置有变更，先保存
    if (isDirty) {
      const saved = await saveConfig(config);
      if (!saved) return;
    }

    // 2. 执行启动逻辑
    optimisticStatus.value = 'STARTING';
    isSubmitting.value = true;

    try {
      await resourceStore.runKBFileTask(resourceId, { action: 'start' });
      // 确保 SSE 连接活跃
      if (!sseController) startSSE();
    } catch (error) {
      console.error('[KBFileTask] Start task failed', error);
      optimisticStatus.value = null;
      throw error; // 抛出错误由组件层处理 Toast
    } finally {
      isSubmitting.value = false;
    }
  };

  /**
   * 恢复任务 (断点续连)
   * 如果遇到配置冲突 (409)，抛出详细错误信息供组件展示
   */
  const resumeTask = async () => {
    optimisticStatus.value = 'STARTING';
    isSubmitting.value = true;

    try {
      await resourceStore.runKBFileTask(resourceId, { action: 'resume' });
      if (!sseController) startSSE();
    } catch (error: any) {
      optimisticStatus.value = null;

      // 专门处理 409 Conflict 错误
      if (error.response?.status === 409) {
        const detail = error.response.data.detail as KBResumeConflictErrorDetail;
        throw detail; // 抛出结构化数据，由组件负责渲染弹窗
      }

      console.error('[KBFileTask] Resume task failed', error);
      throw error;
    } finally {
      isSubmitting.value = false;
    }
  };

  /**
   * 停止任务
   */
  const stopTask = async () => {
    optimisticStatus.value = 'STOPPING';
    isSubmitting.value = true;

    try {
      await resourceStore.runKBFileTask(resourceId, { action: 'stop' });
    } catch (error) {
      console.error('[KBFileTask] Stop task failed', error);
      optimisticStatus.value = null;
      throw error;
    } finally {
      isSubmitting.value = false;
    }
  };

  // --- Lifecycle ---

  /**
   * 组件卸载时清理 SSE 连接
   */
  onUnmounted(() => {
    stopSSE();
  });

  return {
    // State
    statusInfo,
    optimisticStatus,
    isSubmitting,
    // Computed
    isProcessing,
    hasIndexedData,
    canResume,
    progressPercentage,
    // Actions
    startSSE,
    stopSSE,
    saveConfig,
    startTask,
    resumeTask,
    stopTask,
  };
}
