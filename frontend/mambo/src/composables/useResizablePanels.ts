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
  /** 拖拽方向。 */
  orientation: 'horizontal' | 'vertical';
  /** 是否反转拖拽方向。例如，对于可调整高度的输入框，向上拖动应该增加高度。 */
  inverted?: boolean;
}

/**
 * 创建一个用于拖拽调整面板尺寸的响应式逻辑。
 * 它返回一个 `startResize` 方法，该方法应被绑定到拖拽手柄的 `mousedown` 事件上。
 *
 * @param dimension - 一个响应式的 Ref，用于存储和更新面板的尺寸（宽度或高度）。
 * @param options - 包含最小/最大尺寸和方向的配置对象。
 * @returns 返回一个包含 `startResize` 事件处理函数的对象。
 */
export function useResizablePanels(dimension: Ref<number>, options: ResizablePanelsOptions) {
  const { min, max, orientation, inverted = false } = options;

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

      // 将新尺寸限制在 min 和 max 之间
      dimension.value = Math.max(min, Math.min(newDimension, max));
    };

    const stopResize = () => {
      window.removeEventListener('mousemove', doResize);
      window.removeEventListener('mouseup', stopResize);

      // 恢复鼠标样式和文本选择
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    // 在拖拽期间阻止文本选择并设置相应的鼠标指针样式
    document.body.style.cursor = isHorizontal ? 'col-resize' : 'ns-resize';
    document.body.style.userSelect = 'none';

    window.addEventListener('mousemove', doResize);
    window.addEventListener('mouseup', stopResize);
  };

  return {
    startResize,
  };
}
