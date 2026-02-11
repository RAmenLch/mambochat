<template>
  <el-container class="settings-container">
    <el-header class="settings-header">
      <div class="brand-container">
        <img src="/logo.svg" alt="MamboChat" class="logo" />
        <div class="title-wrapper">
          <h1 class="app-name">{{ t('settings.about.title') }}</h1>
          <span class="divider">|</span>
          <span class="sub-name">{{ t('settings.about.subtitle') }}</span>
        </div>
      </div>

      <div class="header-actions">
        <!-- 新增：关于按钮 -->
        <el-button link @click="aboutDialogVisible = true">
          <template #icon>
            <el-icon :size="18"><InfoFilled /></el-icon>
          </template>
          {{ t('settings.nav.about') }}
        </el-button>
        <el-divider direction="vertical" />
        <router-link to="/chat">
          <el-button type="primary" plain>{{ t('settings.nav.returnToChat') }}</el-button>
        </router-link>
      </div>
    </el-header>

    <el-main class="settings-main">
      <div class="settings-content" :class="{ 'is-full-width': activeTab === 'resourceManager' }">
        <el-tabs v-model="activeTab">
          <el-tab-pane :label="t('settings.tabs.providerModel')" name="providerModel">
            <ProviderModelManager />
          </el-tab-pane>
          <el-tab-pane :label="t('settings.tabs.globalSettings')" name="globalSettings">
            <GlobalSettings />
          </el-tab-pane>
          <el-tab-pane :label="t('settings.tabs.mcpManager')" name="mcpManager">
            <McpManager />
          </el-tab-pane>
          <el-tab-pane :label="t('settings.tabs.resourceManager')" name="resourceManager">
            <ResourceManager />
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-main>

    <!-- 新增：关于弹窗 -->
    <el-dialog
      v-model="aboutDialogVisible"
      width="420px"
      align-center
      append-to-body
      class="about-dialog"
    >
      <div class="about-content">
        <img src="/logo.svg" alt="Logo" class="about-logo" />
        <h2 class="about-title">
          {{ t('settings.about.title') }} <span class="about-subtitle">| {{ t('settings.about.subtitle') }}</span>
        </h2>
        <el-tag type="info" size="small" effect="plain" class="version-tag">v1.1.0</el-tag>

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
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { InfoFilled, Message } from '@element-plus/icons-vue' // 引入图标
import ProviderModelManager from '@/components/settings/ProviderModelManager.vue'
import GlobalSettings from '@/components/settings/GlobalSettings.vue'
import ResourceManager from '@/components/settings/ResourceManager.vue'
import McpManager from '@/components/settings/McpManager.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const activeTab = ref(route.query.tab?.toString() || 'providerModel')
const aboutDialogVisible = ref(false) // 控制关于弹窗显示

watch(activeTab, (newTab) => {
  router.replace({ query: { ...route.query, tab: newTab } })
})

watch(
  () => route.query.tab,
  (newTab) => {
    if (newTab && newTab !== activeTab.value) {
      activeTab.value = newTab.toString()
    }
  },
)
</script>

<style scoped>
.settings-container {
  height: 100vh;
  background-color: #f5f7fa;
  display: flex;
  flex-direction: column;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #ffffff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 24px;
  height: 60px;
  flex-shrink: 0;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
  z-index: 10;
}

.brand-container {
  display: flex;
  align-items: center;
  gap: 12px;
  user-select: none;
}

.logo {
  height: 32px;
  width: 32px;
  object-fit: contain;
}

.title-wrapper {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.app-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  letter-spacing: -0.5px;
  line-height: 1;
}

.divider {
  color: #dcdfe6;
  font-size: 18px;
  font-weight: 300;
  transform: translateY(-1px);
}

.sub-name {
  font-size: 16px;
  font-weight: 400;
  color: #606266;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.settings-main {
  padding: 20px;
  flex-grow: 1;
  overflow-y: auto;
}

.settings-content {
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  background-color: #ffffff;
  padding: 24px;
  border-radius: 8px;
  transition: max-width 0.3s ease-in-out;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}

.settings-content.is-full-width {
  max-width: 98%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.settings-content.is-full-width .el-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.settings-content.is-full-width :deep(.el-tabs__content) {
  flex-grow: 1;
  overflow: hidden;
}

.settings-content.is-full-width :deep(.el-tab-pane) {
  height: 100%;
}

:deep(.el-tabs__content) {
  padding-top: 16px;
}

/* 关于弹窗样式 */
.about-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 10px 0 20px;
}

.about-logo {
  width: 80px;
  height: 80px;
  margin-bottom: 16px;
  filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1));
}

.about-title {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.about-subtitle {
  font-weight: 400;
  color: #606266;
  font-size: 18px;
}

.version-tag {
  margin-bottom: 20px;
  font-family: monospace;
}

.about-desc {
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
  margin: 0 20px 24px;
  text-align: justify;
  text-align-last: center; /* 最后一行居中 */
}

.about-links {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 24px;
}

.link-item {
  display: flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
  color: var(--el-color-primary);
  font-size: 14px;
  transition: opacity 0.2s;
}

.link-item:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.link-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
}

.link-icon-el {
  font-size: 18px;
}

.link-divider {
  width: 1px;
  height: 14px;
  background-color: #dcdfe6;
}

.copyright {
  font-size: 12px;
  color: #909399;
}
</style>
