import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'

export function usePageAlert() {
  const sessionStore = useChatSessionStore()
  const { isGenerating, isPendingReview } = storeToRefs(sessionStore)
  const { t } = useI18n()

  const originalTitle = ref(document.title)
  const alertInterval = ref<number | null>(null)
  const isAlerting = ref(false)

  const originalFavicon = ref<string>('')
  let faviconCanvas: HTMLCanvasElement | null = null
  let faviconCtx: CanvasRenderingContext2D | null = null
  let faviconImg: HTMLImageElement | null = null
  let rotationAngle = 0

  const initFaviconCanvas = () => {
    const link = document.querySelector("link[rel~='icon']") as HTMLLinkElement
    if (link) {
      originalFavicon.value = link.href
      faviconImg = new Image()
      faviconImg.crossOrigin = 'anonymous'
      faviconImg.src = link.href

      faviconCanvas = document.createElement('canvas')
      faviconCanvas.width = 32
      faviconCanvas.height = 32
      faviconCtx = faviconCanvas.getContext('2d')
    }
  }

  const animateFavicon = () => {
    if (!faviconCtx || !faviconImg || !faviconCanvas || !faviconImg.complete) return
    faviconCtx.clearRect(0, 0, 32, 32)

    faviconCtx.translate(16, 16)
    rotationAngle = (rotationAngle + 45) % 360
    faviconCtx.rotate((rotationAngle * Math.PI) / 180)
    faviconCtx.drawImage(faviconImg, -16, -16, 32, 32)
    faviconCtx.translate(-16, -16)

    const link = document.querySelector("link[rel~='icon']") as HTMLLinkElement
    if (link) {
      link.href = faviconCanvas.toDataURL('image/png')
    }
  }

  const restoreFavicon = () => {
    const link = document.querySelector("link[rel~='icon']") as HTMLLinkElement
    if (link && originalFavicon.value) {
      link.href = originalFavicon.value
    }
  }

  const requestNotificationPermission = async () => {
    if ('Notification' in window && Notification.permission === 'default') {
      try {
        await Notification.requestPermission()
      } catch (e) {
        console.warn(t('common.alert.permissionFailed'), e)
      }
    }
  }

  const sendSystemNotification = (title: string, body: string) => {
    if ('Notification' in window && Notification.permission === 'granted') {
      const notification = new Notification(title, {
        body,
        icon: originalFavicon.value || '/logo.svg'
      })
      notification.onclick = () => {
        window.focus()
        notification.close()
      }
    }
  }

  const startAlert = (type: 'completed' | 'review') => {
    if (isAlerting.value) return
    isAlerting.value = true

    if (!document.title.startsWith('【')) {
      originalTitle.value = document.title
    }

    const titlePrefix = type === 'review' ? t('common.alert.reviewTitle') : t('common.alert.completedTitle')
    const emptyPrefix = type === 'review' ? t('common.alert.reviewEmpty') : t('common.alert.completedEmpty')
    const notificationBody = type === 'review' ? t('common.alert.reviewBody') : t('common.alert.completedBody')

    sendSystemNotification(titlePrefix.replace(/【|】/g, ''), notificationBody)

    let toggle = false
    alertInterval.value = window.setInterval(() => {
      document.title = (toggle ? titlePrefix : emptyPrefix) + originalTitle.value
      toggle = !toggle
      animateFavicon()
    }, 1000)
  }

  const stopAlert = () => {
    if (!isAlerting.value) return
    isAlerting.value = false
    if (alertInterval.value !== null) {
      clearInterval(alertInterval.value)
      alertInterval.value = null
    }
    document.title = originalTitle.value
    restoreFavicon()
  }

  const handleVisibilityChange = () => {
    if (document.hidden) {
      if (isPendingReview.value) {
        startAlert('review')
      }
    } else {
      stopAlert()
    }
  }

  watch(isGenerating, (newVal, oldVal) => {
    if (document.hidden && oldVal === true && newVal === false) {
      if (isPendingReview.value) {
        startAlert('review')
      } else {
        startAlert('completed')
      }
    }
  })

  watch(isPendingReview, (newVal) => {
    if (document.hidden && newVal === true) {
      startAlert('review')
    }
  })

  onMounted(() => {
    initFaviconCanvas()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    setTimeout(() => {
      requestNotificationPermission()
    }, 3000)
  })

  onUnmounted(() => {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    stopAlert()
  })
}
