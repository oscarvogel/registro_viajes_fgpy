import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export const useInstallPrompt = () => {
  const deferredPrompt = ref(null)
  const showIOSInstructions = ref(false)
  const isInstalled = ref(false)

  const userAgent = globalThis.navigator?.userAgent || ''
  const platform = computed(() => {
    if (/iPad|iPhone|iPod/.test(userAgent)) return 'ios'
    if (/Android/.test(userAgent)) return 'android'
    return 'desktop'
  })

  const isIOSSafari = computed(() => {
    return platform.value === 'ios' && /Safari/.test(userAgent) && !/CriOS|FxiOS|EdgiOS/.test(userAgent)
  })

  const canInstall = computed(() => {
    if (isInstalled.value) return false
    if (platform.value === 'ios') return true
    return Boolean(deferredPrompt.value)
  })

  const detectInstalled = () => {
    isInstalled.value = Boolean(
      globalThis.matchMedia?.('(display-mode: standalone)')?.matches ||
      globalThis.navigator?.standalone
    )
  }

  const onBeforeInstallPrompt = (event) => {
    event.preventDefault()
    deferredPrompt.value = event
  }

  const onAppInstalled = () => {
    isInstalled.value = true
    deferredPrompt.value = null
  }

  const promptInstall = async () => {
    if (platform.value === 'ios') {
      showIOSInstructions.value = true
      return { outcome: 'ios-instructions' }
    }

    if (!deferredPrompt.value) return { outcome: 'unavailable' }

    const promptEvent = deferredPrompt.value
    deferredPrompt.value = null
    await promptEvent.prompt()
    return promptEvent.userChoice || { outcome: 'dismissed' }
  }

  const closeIOSInstructions = () => {
    showIOSInstructions.value = false
  }

  onMounted(() => {
    detectInstalled()
    globalThis.addEventListener?.('beforeinstallprompt', onBeforeInstallPrompt)
    globalThis.addEventListener?.('appinstalled', onAppInstalled)
  })

  onBeforeUnmount(() => {
    globalThis.removeEventListener?.('beforeinstallprompt', onBeforeInstallPrompt)
    globalThis.removeEventListener?.('appinstalled', onAppInstalled)
  })

  return {
    canInstall,
    isInstalled,
    platform,
    showIOSInstructions,
    promptInstall,
    closeIOSInstructions,
    isIOSSafari,
  }
}
