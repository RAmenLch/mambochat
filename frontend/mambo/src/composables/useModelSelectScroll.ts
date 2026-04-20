import { useProviderStore } from '@/stores/providerStore'

/**
 * 当模型下拉框打开时，如果当前选中的是标星模型，
 * 自动将下拉面板滚动到顶部（标星分组的位置）。
 *
 * 使用 setTimeout 确保 Element Plus 自身的 scrollIntoView 执行完毕后再覆盖滚动位置。
 */
export function useModelSelectScroll() {
  function scrollToTopIfStarred(visible: boolean, selectRef: any) {
    if (!visible || !selectRef) return

    const modelId = selectRef.modelValue as string | null
    if (!modelId) return

    // 直接从 store 判断模型是否标星
    const providerStore = useProviderStore()
    const model = providerStore.allModels.find(m => m.id === modelId)
    if (!model?.starred) return

    // setTimeout 0 确保在 Element Plus scrollIntoView 之后执行
    setTimeout(() => {
      try {
        const popperContentRef = selectRef.tooltipRef?.popperRef?.contentRef
        if (!popperContentRef) return
        const wrapEl = popperContentRef.querySelector('.el-select-dropdown__wrap')
        if (wrapEl) {
          wrapEl.scrollTop = 0
        }
      } catch {
        // ignore
      }
    }, 0)
  }

  return { scrollToTopIfStarred }
}
