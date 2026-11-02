import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CSSProperties, Ref } from 'vue'

interface ImageAspectBoxOptions {
  /** 预览框高度上限（px）；未提供容器测量时即为唯一上限 */
  maxHeight?: number
  /** 滚动容器元素，提供后按容器实际可用高度计算预览尺寸，避免出现滚动条 */
  container?: Ref<HTMLElement | null>
  /** 预览框以外需要预留的高度（px）：信息栏、操作按钮、内边距等 */
  reservedHeight?: number
  /** 预览框高度下限（px） */
  minHeight?: number
}

/**
 * 依据图片原始宽高比计算预览框样式，使预览框与图片同比例并完整展示图片：
 * 宽度同时受容器宽度、可用高度反推宽度与图片原始像素宽度限制，高度由比例自动推导。
 */
export function useImageAspectBox(
  source: Ref<string | null | undefined>,
  options: ImageAspectBoxOptions = {}
) {
  const { maxHeight = 460, container, reservedHeight = 0, minHeight = 120 } = options

  const naturalSize = ref<{ width: number; height: number } | null>(null)
  const availableHeight = ref<number | null>(null)

  const onImageLoad = (event: Event) => {
    const img = event.target as HTMLImageElement | null
    if (img?.naturalWidth && img?.naturalHeight) {
      naturalSize.value = { width: img.naturalWidth, height: img.naturalHeight }
    }
  }

  watch(source, () => {
    naturalSize.value = null
  })

  let observer: ResizeObserver | null = null

  const measure = () => {
    const el = container?.value
    if (!el) return
    availableHeight.value = Math.max(minHeight, el.clientHeight - reservedHeight)
  }

  const stopObserve = () => {
    observer?.disconnect()
    observer = null
  }

  if (container) {
    watch(
      container,
      (el) => {
        stopObserve()
        if (!el) return
        observer = new ResizeObserver(measure)
        observer.observe(el)
        measure()
      },
      { immediate: true }
    )
    onMounted(measure)
    onBeforeUnmount(stopObserve)
  }

  const boxStyle = computed<CSSProperties>(() => {
    const size = naturalSize.value
    if (!size) return {}
    const ratio = size.width / size.height
    const limitHeight = Math.min(availableHeight.value ?? maxHeight, maxHeight)
    return {
      width: `min(100%, ${Math.round(ratio * limitHeight)}px, ${size.width}px)`,
      height: 'auto',
      aspectRatio: String(ratio),
    }
  })

  return { boxStyle, onImageLoad }
}
