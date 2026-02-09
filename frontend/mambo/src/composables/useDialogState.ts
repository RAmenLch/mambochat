// frontend/mambo/src/composables/useDialogState.ts

import { ref, type Ref } from 'vue';

/**
 * useDialogState 的返回值接口。
 */
export interface UseDialogStateReturn<T> {
  /**
   * 控制弹窗的显示状态。
   */
  visible: Ref<boolean>;
  /**
   * 存储弹窗所需的上下文数据（载荷）。
   * 在弹窗关闭时，该数据会被保留直到下一次 open 调用覆盖，或手动设置为 null。
   */
  payload: Ref<T | null>;
  /**
   * 打开弹窗并设置上下文数据。
   * @param data - 传递给弹窗的数据对象。
   */
  open: (data: T) => void;
  /**
   * 关闭弹窗。
   */
  close: () => void;
}

/**
 * 一个通用的组合式函数，用于管理弹窗的显示状态和数据载荷。
 * 旨在消除组件中分散的 visible 变量和临时数据引用。
 *
 * @template T - 弹窗上下文数据（Payload）的类型。
 * @returns 包含 visible, payload, open, close 的对象。
 */
export function useDialogState<T>(): UseDialogStateReturn<T> {
  const visible = ref(false);
  const payload = ref<T | null>(null) as Ref<T | null>;

  const open = (data: T) => {
    payload.value = data;
    visible.value = true;
  };

  const close = () => {
    visible.value = false;
    // 选择不自动清除 payload，以防止弹窗关闭动画期间数据丢失导致 UI 闪烁。
    // 数据将在下一次 open 时被覆盖。
  };

  return {
    visible,
    payload,
    open,
    close,
  };
}
