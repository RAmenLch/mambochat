// frontend/mambo/src/composables/useContextMenu.ts

import { ref, reactive, nextTick } from 'vue';
import type { Ref, CSSProperties, UnwrapNestedRefs } from 'vue';

/**
 * 定义一个可以显示上下文菜单的组件实例的类型接口。
 * El-dropdown 组件暴露了 `handleOpen` 和 `handleClose` 方法。
 */
interface ContextMenuInstance {
  handleOpen: () => void;
  handleClose: () => void;
}

/**
 * useContextMenu 的返回值类型。
 */
interface UseContextMenuReturn<T> {
  /** 响应式的引用，指向当前被右键点击的数据项。 */
  contextMenuItem: Ref<T | null>;
  /** 用于 el-dropdown 的 DOM 定位样式。 */
  contextMenuPosition: UnwrapNestedRefs<CSSProperties>;
  /**
   * mousedown 事件处理器，用于触发上下文菜单。
   * @param event - 鼠标事件对象。
   * @param item - 与事件关联的数据项。
   * @param menuRef - El-dropdown 组件的模板引用 (template ref)。
   */
  handleContextMenu: (event: MouseEvent, item: T | null, menuRef: Ref<ContextMenuInstance | undefined>) => void;
}

/**
 * 创建一个用于管理右键上下文菜单的响应式逻辑。
 *
 * @returns 返回一个包含菜单项、位置和事件处理函数的对象。
 */
export function useContextMenu<T>(): UseContextMenuReturn<T> {
  // 核心修复：使用类型断言来解决泛型 T 导致的 ref 类型推断不匹配问题。
  const contextMenuItem = ref<T | null>(null) as Ref<T | null>;

  const contextMenuPosition = reactive<CSSProperties>({
    position: 'fixed',
    top: '0px',
    left: '0px',
    zIndex: 9999,
  });

  const handleContextMenu = async (
    event: MouseEvent,
    item: T | null,
    menuRef: Ref<ContextMenuInstance | undefined>
  ) => {
    // 阻止浏览器默认的右键菜单
    event.preventDefault();

    if (!menuRef.value) return;

    // 如果在已有菜单的组件上右键，但没有获取到具体的数据项，则判定为无效操作
    if (!item && (event.target as HTMLElement).closest('.el-tree-node')) {
      return;
    }

    // 立即关闭任何已打开的菜单以重置其状态
    menuRef.value.handleClose();

    await nextTick();

    // 更新菜单所需的数据和锚点位置
    contextMenuItem.value = item;
    contextMenuPosition.left = `${event.clientX}px`;
    contextMenuPosition.top = `${event.clientY}px`;

    // 将打开操作推迟到DOM更新后，确保 Popper.js 能在正确的位置上重新计算并打开菜单
    menuRef.value.handleOpen();
  };

  return {
    contextMenuItem,
    contextMenuPosition,
    handleContextMenu,
  };
}
