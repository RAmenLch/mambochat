<!-- frontend/mambo/src/mobile/views/SettingsView.vue -->
<template>
  <div class="mobile-settings-view">
    <!-- 顶部导航栏 -->
    <div class="settings-header">
      <div class="header-left">
        <el-button
          v-if="activeSection"
          link
          :icon="ArrowLeft"
          @click="activeSection = ''"
          class="back-btn"
        />
        <span class="title">
          {{ activeSection ? currentTitle : t('settings.about.title') }}
        </span>
      </div>
      <div class="header-right">
        <el-button v-if="!activeSection" link @click="aboutDialogVisible = true">
          <el-icon :size="20"><InfoFilled /></el-icon>
        </el-button>
        <el-button v-if="!activeSection" type="primary" size="small" @click="goToChat">
          {{ t('settings.nav.returnToChat') }}
        </el-button>
      </div>
    </div>

    <!-- 内容区域 -->
    <div class="settings-content">
      <!-- 主菜单列表 -->
      <transition name="slide-left">
        <div v-if="!activeSection" class="menu-list">
          <div
            v-for="item in menuItems"
            :key="item.id"
            class="menu-item"
            @click="activeSection = item.id"
          >
            <el-icon class="menu-icon"><component :is="item.icon" /></el-icon>
            <span class="menu-label">{{ item.label }}</span>
            <el-icon class="menu-arrow"><ArrowRight /></el-icon>
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
          <!-- [新增] Agent 管理视图 -->
          <MobileAgentManager v-else-if="activeSection === 'agent'" class="mobile-setting-component" />
        </div>
      </transition>
    </div>

    <!-- 关于弹窗 -->
    <el-dialog
      v-model="aboutDialogVisible"
      width="90%"
      align-center
      append-to-body
      class="about-dialog"
      :style="{ maxWidth: '400px' }"
    >
      <div class="about-content">
        <img src="/logo.svg" alt="Logo" class="about-logo" />
        <h2 class="about-title">
          {{ t('settings.about.title') }} <span class="about-subtitle">| {{ t('settings.about.subtitle') }}</span>
        </h2>
        <el-tag type="info" size="small" effect="plain" class="version-tag">v1.2.2</el-tag>

        <p class="about-desc">
          {{ t('settings.about.desc') }}
        </p>

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

        <div class="copyright">
          {{ t('settings.about.copyright', { year: new Date().getFullYear() }) }}
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft,
  ArrowRight,
  InfoFilled,
  User,
  Monitor,
  Connection,
  FolderOpened,
  Message,
  Service // [新增] 引入 Service 图标用于 Agent
} from '@element-plus/icons-vue'

import GlobalSettings from '@/components/settings/GlobalSettings.vue'
import MobileProviderModelManager from '@/mobile/components/settings/MobileProviderModelManager.vue'
import MobileMcpManager from '@/mobile/components/settings/MobileMcpManager.vue'
import MobileResourceManager from '@/mobile/components/settings/MobileResourceManager.vue'
// [新增] 引入移动端 Agent 管理组件
import MobileAgentManager from '@/mobile/components/settings/MobileAgentManager.vue'

const router = useRouter()
const { t } = useI18n()

const activeSection = ref('')
const aboutDialogVisible = ref(false)

// [修改] 在菜单列表中加入 Agent 管理
const menuItems = computed(() => [
  { id: 'global', icon: User, label: t('settings.tabs.globalSettings') },
  { id: 'provider', icon: Monitor, label: t('settings.tabs.providerModel') },
  { id: 'mcp', icon: Connection, label: t('settings.tabs.mcpManager') },
  { id: 'resource', icon: FolderOpened, label: t('settings.tabs.resourceManager') },
  { id: 'agent', icon: Service, label: 'Agent 管理' }, // 与桌面端保持一致的文本
])

const currentTitle = computed(() => {
  const item = menuItems.value.find(m => m.id === activeSection.value)
  return item ? item.label : ''
})

const goToChat = () => {
  router.push('/chat')
}
</script>

<style scoped>
.mobile-settings-view {
  height: 100vh;
  width: 100vw;
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header Styles */
.settings-header {
  height: 50px;
  padding: 0 15px;
  background-color: var(--color-background-soft);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
}

.back-btn {
  margin-right: 5px;
  padding: 5px;
}

.title {
  font-size: 17px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Content Styles */
.settings-content {
  flex: 1;
  overflow: hidden;
  position: relative;
  width: 100%;
}

.menu-list, .detail-view {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: var(--color-background);
  overflow-y: auto;
}

/* Menu List Item */
.menu-item {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  background-color: var(--color-background-soft);
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background-color 0.2s;
}

.menu-item:active {
  background-color: var(--el-fill-color-dark);
}

.menu-icon {
  font-size: 20px;
  margin-right: 15px;
  color: var(--el-text-color-regular);
}

.menu-label {
  flex: 1;
  font-size: 16px;
  color: var(--el-text-color-primary);
}

.menu-arrow {
  color: var(--el-text-color-secondary);
}

/* Detail View Adjustments */
.mobile-setting-component {
  padding: 0;
  height: 100%;
}

.mobile-setting-component :deep(.header) {
  display: none;
}

.mobile-setting-component :deep(.panel-header .title) {
  display: none;
}

.mobile-setting-component :deep(.panel-header) {
  justify-content: flex-end;
}

.mobile-setting-component :deep(.settings-form-container) {
  border: none;
  padding: 0;
}

/* Transitions */
.slide-left-enter-active,
.slide-left-leave-active,
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s ease;
}

.slide-left-enter-from { transform: translateX(-100%); }
.slide-left-leave-to { transform: translateX(-100%); }
.slide-right-enter-from { transform: translateX(100%); }
.slide-right-leave-to { transform: translateX(100%); }

/* About Dialog Styles */
.about-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0 20px;
  text-align: center;
}

.about-logo {
  width: 60px;
  height: 60px;
  margin-bottom: 15px;
}

.about-title {
  margin: 0 0 10px;
  font-size: 18px;
}

.about-subtitle {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  font-weight: normal;
}

.version-tag {
  margin-bottom: 15px;
}

.about-desc {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin: 0 0 20px;
  line-height: 1.5;
  padding: 0 10px;
}

.about-links {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
}

.link-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--el-color-primary);
  text-decoration: none;
}

.link-icon {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.link-icon-el {
  font-size: 20px;
}

.link-divider {
  width: 1px;
  height: 14px;
  background-color: var(--el-border-color);
}

.copyright {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
