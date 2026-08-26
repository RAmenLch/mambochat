<!-- SettingsView.vue — 移动端设置主页（美化版） -->
<template>
  <div class="mobile-settings-view">
    <!-- 毛玻璃导航栏 -->
    <div class="settings-header">
      <div class="header-left">
        <button v-if="activeSection" class="back-btn" @click="activeSection = ''">
          <el-icon :size="20"><ArrowLeft /></el-icon>
        </button>
        <span class="title">
          {{ activeSection ? currentTitle : t('settings.about.title') }}
        </span>
      </div>
      <div class="header-right">
        <button v-if="activeSection" class="chat-btn" @click="goToChat">
          <el-icon :size="20"><ChatDotRound /></el-icon>
        </button>
        <template v-if="!activeSection">
          <button class="info-btn" @click="aboutSheetVisible = true">
            <el-icon :size="20"><InfoFilled /></el-icon>
          </button>
          <button class="return-btn" @click="goToChat">
            <el-icon :size="16"><ChatDotRound /></el-icon>
            <span>{{ t('settings.nav.returnToChat') }}</span>
          </button>
        </template>
      </div>
    </div>

    <!-- 内容区域 -->
    <div class="settings-content">
      <!-- 主菜单 -->
      <transition name="slide-left">
        <div v-if="!activeSection" class="menu-list">
          <div class="menu-section-label">{{ t('settings.about.configuration') }}</div>
          <div
            v-for="item in menuItems"
            :key="item.id"
            class="menu-card"
            @click="activeSection = item.id"
          >
            <div class="menu-card-icon" :style="{ background: item.color }">
              <el-icon :size="22"><component :is="item.icon" /></el-icon>
            </div>
            <div class="menu-card-info">
              <span class="menu-card-title">{{ item.label }}</span>
              <span class="menu-card-desc">{{ item.desc }}</span>
            </div>
            <el-icon class="menu-card-arrow"><ArrowRight /></el-icon>
          </div>

          <div class="menu-footer">
            <span class="menu-footer-text">{{ t('settings.about.copyright', { year: new Date().getFullYear() }) }}</span>
          </div>
        </div>
      </transition>

      <!-- 详情视图 -->
      <transition name="slide-right">
        <div v-if="activeSection" class="detail-view">
          <GlobalSettings v-if="activeSection === 'global'" class="mobile-setting-component" />
          <MobileProviderModelManager v-else-if="activeSection === 'provider'" class="mobile-setting-component" />
          <MobileMcpManager v-else-if="activeSection === 'mcp'" class="mobile-setting-component" />
          <MobileResourceManager v-else-if="activeSection === 'resource'" class="mobile-setting-component" />
          <MobileAgentManager v-else-if="activeSection === 'agent'" class="mobile-setting-component" />
        </div>
      </transition>
    </div>

    <!-- 关于 Bottom Sheet -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="aboutSheetVisible" class="sheet-overlay" @click="aboutSheetVisible = false">
          <div class="sheet-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="about-content">
              <img src="/logo.svg" alt="Logo" class="about-logo" />
              <h2 class="about-title">
                {{ t('settings.about.title') }}
                <span class="about-subtitle">| {{ t('settings.about.subtitle') }}</span>
              </h2>
              <el-tag type="info" size="small" effect="plain" class="version-tag">v{{ appVersion }}</el-tag>
              <p class="about-desc">{{ t('settings.about.desc') }}</p>
              <div class="about-links">
                <a href="https://github.com/RAmenLch/mambochat" target="_blank" class="link-item">
                  <img src="https://github.com/fluidicon.png" class="link-icon" alt="GitHub" />
                  {{ t('settings.about.github') }}
                </a>
                <div class="link-divider"></div>
                <a href="mailto:ramenlch@qq.com" class="link-item">
                  <el-icon class="link-icon-el"><Message /></el-icon>
                  {{ t('settings.about.contact') }}
                </a>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft, ArrowRight, InfoFilled, User, Monitor, Connection,
  FolderOpened, Message, Service, ChatDotRound, Setting
} from '@element-plus/icons-vue'

import GlobalSettings from '@/mobile/components/settings/MobileGlobalSettings.vue'
import MobileProviderModelManager from '@/mobile/components/settings/MobileProviderModelManager.vue'
import MobileMcpManager from '@/mobile/components/settings/MobileMcpManager.vue'
import MobileResourceManager from '@/mobile/components/settings/MobileResourceManager.vue'
import MobileAgentManager from '@/mobile/components/settings/MobileAgentManager.vue'

const router = useRouter()
const { t } = useI18n()

const CACHE_KEY = 'mambo_settings_last_section'

const activeSection = ref('')
const aboutSheetVisible = ref(false)
const appVersion = __APP_VERSION__

onMounted(() => {
  const cachedSection = localStorage.getItem(CACHE_KEY)
  const cachedQuery = localStorage.getItem(CACHE_KEY + '_query')
  if (cachedSection && menuItems.value.some(m => m.id === cachedSection)) {
    activeSection.value = cachedSection
    if (cachedQuery) {
      try {
        const q = JSON.parse(cachedQuery)
        router.replace({ query: { ...router.currentRoute.value.query, ...q } })
      } catch {}
    }
  }
})

watch(activeSection, (val) => {
  if (val) { localStorage.setItem(CACHE_KEY, val) }
  else { localStorage.removeItem(CACHE_KEY); localStorage.removeItem(CACHE_KEY + '_query') }
})

watch(() => router.currentRoute.value.query, (q) => {
  if (activeSection.value) {
    const relevant: Record<string, any> = {}
    for (const key of ['agentId', 'resourceId', 'tab']) { if (q[key]) relevant[key] = q[key] }
    if (Object.keys(relevant).length > 0) localStorage.setItem(CACHE_KEY + '_query', JSON.stringify(relevant))
  }
}, { deep: true })

const menuItems = computed(() => [
  { id: 'global', icon: Setting, label: t('settings.tabs.globalSettings'), desc: t('settings.about.globalDesc') || '语言、模型、编辑器偏好', color: '#6366f1' },
  { id: 'provider', icon: Monitor, label: t('settings.tabs.providerModel'), desc: t('settings.about.providerDesc') || '服务商与模型管理', color: '#0891b2' },
  { id: 'mcp', icon: Connection, label: t('settings.tabs.mcpManager'), desc: t('settings.about.mcpDesc') || 'MCP 工具服务配置', color: '#059669' },
  { id: 'resource', icon: FolderOpened, label: t('settings.tabs.resourceManager'), desc: t('settings.about.resourceDesc') || '资源与知识库', color: '#d97706' },
  { id: 'agent', icon: Service, label: 'Agent 管理', desc: '智能体配置与 Backend 挂载', color: '#dc2626' },
])

const currentTitle = computed(() => menuItems.value.find(m => m.id === activeSection.value)?.label || '')

const goToChat = () => router.push('/chat')
</script>

<style scoped>
.mobile-settings-view {
  height: 100vh; width: 100vw;
  background: var(--color-background);
  display: flex; flex-direction: column; overflow: hidden;
}

/* ===== Header ===== */
.settings-header {
  display: flex; align-items: center; justify-content: space-between;
  height: 50px; padding: 0 12px;
  padding-top: env(safe-area-inset-top);
  background: rgba(255,255,255,0.72);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0,0,0,0.08);
  flex-shrink: 0; z-index: 10;
}
.header-left { display: flex; align-items: center; gap: 4px; min-width: 0; }
.back-btn {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border: none; border-radius: 50%;
  background: transparent; color: var(--el-color-primary); cursor: pointer;
  flex-shrink: 0;
}
.back-btn:active { background: rgba(0,0,0,0.06); }
.title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.chat-btn, .info-btn {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border: none; border-radius: 50%;
  background: var(--el-fill-color-light); color: var(--el-text-color-secondary); cursor: pointer;
}
.chat-btn:active, .info-btn:active { background: var(--el-fill-color); }

.return-btn {
  display: flex; align-items: center; gap: 4px; height: 32px; padding: 0 14px;
  font-size: 13px; font-weight: 600; color: #fff;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  border: none; border-radius: 16px; box-shadow: 0 2px 8px rgba(64,158,255,0.3); cursor: pointer;
}
.return-btn:active { opacity: 0.85; }

/* ===== Content ===== */
.settings-content { flex: 1; overflow: hidden; position: relative; width: 100%; }
.menu-list, .detail-view {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  background: var(--color-background); overflow-y: auto; -webkit-overflow-scrolling: touch;
}

/* ===== Menu Cards ===== */
.menu-section-label {
  font-size: 12px; font-weight: 600; color: var(--el-text-color-secondary);
  text-transform: uppercase; letter-spacing: 0.5px;
  padding: 16px 20px 8px;
}

.menu-card {
  display: flex; align-items: center; gap: 14px;
  margin: 0 14px 8px; padding: 14px 16px;
  background: var(--color-background-soft); border-radius: 14px;
  border: 0.5px solid rgba(0,0,0,0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.03);
  cursor: pointer; -webkit-tap-highlight-color: transparent;
  transition: transform 0.15s, box-shadow 0.15s;
}
.menu-card:active { transform: scale(0.98); box-shadow: 0 1px 6px rgba(0,0,0,0.08); }

.menu-card-icon {
  width: 44px; height: 44px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0;
}

.menu-card-info { flex: 1; min-width: 0; }
.menu-card-title { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 2px; }
.menu-card-desc { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.menu-card-arrow { color: var(--el-text-color-placeholder); flex-shrink: 0; }

.menu-footer { padding: 24px 20px; text-align: center; }
.menu-footer-text { font-size: 12px; color: var(--el-text-color-placeholder); }

/* ===== Detail ===== */
.mobile-setting-component { padding: 0; height: 100%; }

/* ===== About Sheet ===== */
.sheet-overlay { position: fixed; inset: 0; z-index: 2200; background: rgba(0,0,0,0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 500px; background: var(--el-bg-color); border-radius: 16px 16px 0 0; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0,0,0,0.15); border-radius: 2px; margin: 10px auto 0; }

.about-content { display: flex; flex-direction: column; align-items: center; padding: 20px 20px 36px; text-align: center; }
.about-logo { width: 56px; height: 56px; margin-bottom: 12px; }
.about-title { margin: 0 0 8px; font-size: 18px; font-weight: 700; color: var(--el-text-color-primary); }
.about-subtitle { font-size: 13px; color: var(--el-text-color-secondary); font-weight: 400; }
.version-tag { margin-bottom: 14px; }
.about-desc { font-size: 13px; color: var(--el-text-color-secondary); margin: 0 0 18px; line-height: 1.5; }
.about-links { display: flex; align-items: center; gap: 14px; margin-bottom: 0; }
.link-item { display: flex; align-items: center; gap: 5px; font-size: 14px; color: var(--el-color-primary); text-decoration: none; }
.link-icon { width: 18px; height: 18px; object-fit: contain; }
.link-icon-el { font-size: 18px; }
.link-divider { width: 1px; height: 12px; background: var(--el-border-color); }

/* ===== Transitions ===== */
.slide-left-enter-active, .slide-left-leave-active,
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.3s ease; }
.slide-left-enter-from { transform: translateX(-30%); }
.slide-left-leave-to { transform: translateX(-100%); }
.slide-right-enter-from { transform: translateX(100%); }
.slide-right-leave-to { transform: translateX(30%); }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }

/* ===== Dark Mode ===== */
@media (prefers-color-scheme: dark) {
  .settings-header { background: rgba(30,30,30,0.72); border-bottom-color: rgba(255,255,255,0.08); }
  .menu-card { border-color: rgba(255,255,255,0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
  .back-btn:active { background: rgba(255,255,255,0.08); }
  .sheet-handle { background: rgba(255,255,255,0.2); }
}
</style>
