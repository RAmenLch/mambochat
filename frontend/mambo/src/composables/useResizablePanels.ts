// frontend/mambo/src/composables/useResizablePanels.ts

import type { Ref } from 'vue';

/**
 * useResizablePanels Composable 的配置选项接口。
 */
export interface ResizablePanelsOptions {
  /** 最小尺寸（宽度或高度），单位为像素。 */
  min: number;
  /** 最大尺寸（宽度或高度），单位为像素。 */
  max: number;
  /** 吸附阈值。当尺寸小于此值并释放鼠标时，触发折叠；否则回弹至 min。 */
  snapThreshold?: number;
  /** 折叠后的固定尺寸。 */
  collapsedWidth?: number;
  /** 拖拽方向。 */
  orientation: 'horizontal' | 'vertical';
  /** 是否反转拖拽方向。例如，对于可调整高度的输入框，向上拖动应该增加高度。 */
  inverted?: boolean;
}

/**
 * 创建一个用于拖拽调整面板尺寸的响应式逻辑，支持吸附折叠功能。
 *
 * @param dimension - 一个响应式的 Ref，用于存储和更新面板的尺寸。
 * @param isCollapsed - 一个响应式的 Ref，用于存储和更新面板的折叠状态。
 * @param options - 包含尺寸限制、方向及折叠阈值的配置对象。
 * @returns 返回包含事件处理函数和手动展开方法的对象。
 */
export function useResizablePanels(
  dimension: Ref<number>,
  isCollapsed: Ref<boolean>,
  options: ResizablePanelsOptions
) {
  const {
    min,
    max,
    orientation,
    inverted = false,
    snapThreshold = min / 2,
    collapsedWidth = 60
  } = options;

  /**
   * 手动展开面板。
   * 将状态置为未折叠，并确保尺寸至少为最小宽度。
   */
  const expand = () => {
    isCollapsed.value = false;
    if (dimension.value < min) {
      dimension.value = min;
    }
  };

  const startResize = (event: MouseEvent) => {
    const isHorizontal = orientation === 'horizontal';

    const startCoordinate = isHorizontal ? event.clientX : event.clientY;
    const startDimension = dimension.value;

    const doResize = (e: MouseEvent) => {
      const currentCoordinate = isHorizontal ? e.clientX : e.clientY;
      let delta = currentCoordinate - startCoordinate;

      if (inverted) {
        delta = -delta;
      }

      const newDimension = startDimension + delta;

      // 在拖拽过程中，允许尺寸小于 min 以提供视觉反馈，
      // 但不应小于 collapsedWidth (或0)，也不应大于 max。
      // 注意：这里暂时打破 min 限制是为了实现“拖拽至吸附区”的手感。
      dimension.value = Math.max(collapsedWidth, Math.min(newDimension, max));
    };

    const stopResize = () => {
      window.removeEventListener('mousemove', doResize);
      window.removeEventListener('mouseup', stopResize);

      // 恢复鼠标样式和文本选择
      document.body.style.cursor = '';
      document.body.style.userSelect = '';

      // 拖拽结束时的吸附与回弹逻辑
      if (dimension.value <= snapThreshold) {
        // 触发吸附折叠
        isCollapsed.value = true;
        dimension.value = collapsedWidth;
      } else if (dimension.value < min) {
        // 未达到吸附阈值，回弹至最小宽度
        isCollapsed.value = false;
        dimension.value = min;
      } else {
        // 正常范围，确认为展开状态
        isCollapsed.value = false;
      }
    };

    // 在拖拽期间阻止文本选择并设置相应的鼠标指针样式
    document.body.style.cursor = isHorizontal ? 'col-resize' : 'ns-resize';
    document.body.style.userSelect = 'none';

    window.addEventListener('mousemove', doResize);
    window.addEventListener('mouseup', stopResize);
  };

  return {
    startResize,
    expand,
  };
}
