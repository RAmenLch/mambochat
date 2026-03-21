<!-- frontend/mambo/src/components/common/dialogs/ResourceSelectorPreview.vue -->
<template>
  <el-main class="resource-preview-main">
    <el-empty v-if="selectedResources.length === 0" :description="$t('resource.editor.placeholder')" />

    <!-- 单选预览 -->
    <el-card v-else-if="selectedResources.length === 1" shadow="never" class="preview-card">
      <template #header>
        <div class="preview-header">
          <strong>{{ $t('resource.selector.previewHeader', { name: selectedResources[0].name }) }}</strong>
        </div>
      </template>
      <el-scrollbar class="preview-scrollbar" v-loading="isPreviewLoading">
        <!-- Knowledge Base Preview -->
        <template v-if="selectedResources[0].resourceType === 'knowledge_base'">
          <div class="kb-preview-wrapper">
            <el-icon :size="64" color="#409EFF"><Collection /></el-icon>
            <h3>{{ selectedResources[0].name }}</h3>
            <p class="kb-desc">{{ selectedResources[0].description || $t('resource.selector.noDesc') }}</p>
            <el-alert
              :title="$t('resource.selector.kbMountTip')"
              type="info"
              :closable="false"
              show-icon
              style="margin-top: 20px; max-width: 80%;"
            >
              {{ $t('resource.selector.kbMountContent') }}
            </el-alert>
          </div>
        </template>

        <!-- Skill Preview -->
        <template v-else-if="selectedResources[0].resourceType === 'skill'">
          <div class="kb-preview-wrapper">
            <el-icon :size="64" color="#F56C6C"><Reading /></el-icon>
            <h3>{{ selectedResources[0].name }}</h3>
            <p class="kb-desc">{{ selectedResources[0].description || $t('resource.selector.noDesc') }}</p>
            <el-alert
              title="技能 (Skill) 挂载"
              type="warning"
              :closable="false"
              show-icon
              style="margin-top: 20px; max-width: 80%;"
            >
              挂载此技能后，Agent 将获得该技能定义的工具和能力。
            </el-alert>
          </div>
        </template>

        <!-- File Resource Preview -->
        <template v-else-if="selectedResources[0].resourceType === 'file'">
          <div v-if="currentFileInfo" class="file-preview-wrapper">
            <div v-if="isImage" class="file-preview-image">
              <el-image :src="currentFileInfo.url" :preview-src-list="[currentFileInfo.url]" fit="contain" class="preview-img">
                <template #error>
                  <div class="image-slot"><el-icon><Picture /></el-icon><span>{{ $t('resource.attachment.imageLoadFailed') }}</span></div>
                </template>
              </el-image>
            </div>
            <div v-else class="file-generic">
              <el-icon :size="48"><Document /></el-icon>
              <div class="file-meta">
                <div class="file-name">{{ currentFileInfo.filename }}</div>
                <div class="file-size">{{ formatFileSize(currentFileInfo.size) }}</div>
              </div>
              <a :href="currentFileInfo.url" target="_blank" class="download-link">
                <el-button type="primary" link icon="Download">{{ $t('resource.editor.downloadFile') }}</el-button>
              </a>
            </div>
          </div>
          <div v-else class="file-empty-state">
            <el-icon :size="48"><Document /></el-icon>
            <p>{{ $t('resource.selector.noFileContent') }}</p>
          </div>
        </template>

        <!-- Text Resource Preview -->
        <pre v-else class="preview-content">{{ selectedResources[0].latest_version?.content || $t('resource.selector.noContent') }}</pre>
      </el-scrollbar>
    </el-card>

    <!-- 多选预览 -->
    <el-card v-else shadow="never" class="preview-card">
      <template #header>
        <div class="preview-header">
          <strong>{{ $t('resource.selector.multiPreview', { count: selectedResources.length }) }}</strong>
        </div>
      </template>
      <el-scrollbar class="preview-scrollbar" v-loading="isPreviewLoading">
        <div v-for="(res, index) in selectedResources" :key="res.id" class="multi-preview-item">
          <div class="multi-preview-label">#{{ index + 1 }} {{ res.name }}</div>

          <template v-if="res.resourceType === 'knowledge_base'">
            <div class="mini-empty">{{ $t('resource.selector.kbContainer') }}</div>
          </template>

          <template v-else-if="res.resourceType === 'skill'">
            <div class="mini-empty">技能 (Skill) 资源</div>
          </template>

          <template v-else-if="res.resourceType === 'file'">
            <div v-if="res.latest_version?.file_info" class="file-preview-wrapper mini">
              <div v-if="isResourceImage(res)" class="file-preview-image mini">
                <el-image :src="res.latest_version.file_info.url" :preview-src-list="[res.latest_version.file_info.url]" fit="contain" style="width: 100%; height: 100%;" />
              </div>
              <div v-else class="file-generic mini">
                <el-icon><Document /></el-icon>
                <span>{{ res.latest_version.file_info.filename }}</span>
              </div>
            </div>
            <div v-else class="mini-empty">{{ $t('resource.selector.noFile') }}</div>
          </template>

          <pre v-else class="preview-content">{{ res.latest_version?.content || $t('resource.selector.noContent') }}</pre>

          <el-divider v-if="index < selectedResources.length - 1" border-style="dashed" />
        </div>
      </el-scrollbar>
    </el-card>
  </el-main>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Document, Picture, Collection, Reading } from '@element-plus/icons-vue';
import type { Resource } from '@/api/types';

const props = defineProps<{
  selectedResources: Resource[];
  isPreviewLoading: boolean;
}>();

const currentFileInfo = computed(() => props.selectedResources[0]?.latest_version?.file_info || null);
const isImage = computed(() => {
  const mime = currentFileInfo.value?.mime_type;
  return mime ? mime.startsWith('image/') : false;
});

const isResourceImage = (resource: Resource): boolean => {
  const mime = resource.latest_version?.file_info?.mime_type;
  return mime ? mime.startsWith('image/') : false;
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};
</script>

<style scoped>
.resource-preview-main { padding: 0; background-color: var(--el-bg-color-page); }
.preview-card { height: 100%; border: none; display: flex; flex-direction: column; background-color: transparent; }
:deep(.preview-card .el-card__header) { flex-shrink: 0; background-color: #fff; }
:deep(.preview-card .el-card__body) { flex-grow: 1; padding: 0; overflow: hidden; }
.preview-scrollbar { padding: 20px; }
.preview-content { white-space: pre-wrap; word-wrap: break-word; font-family: var(--el-font-family); font-size: 14px; margin: 0; }

.kb-preview-wrapper { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; text-align: center; height: 100%; }
.kb-desc { color: var(--el-text-color-secondary); margin-top: 10px; max-width: 80%; }

.file-preview-wrapper { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; gap: 16px; width: 100%; }
.file-preview-image { width: 100%; max-height: 400px; display: flex; justify-content: center; align-items: center; background-color: #f5f5f5; border-radius: 4px; overflow: hidden; border: 1px solid var(--el-border-color-lighter); }
.preview-img { width: 100%; height: 100%; }
.file-generic { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 24px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background-color: var(--el-fill-color-lighter); width: 100%; max-width: 300px; text-align: center; }
.file-meta { display: flex; flex-direction: column; gap: 4px; }
.file-name { font-weight: 500; color: var(--el-text-color-primary); word-break: break-all; }
.file-size { font-size: 12px; color: var(--el-text-color-secondary); }
.file-empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: var(--el-text-color-secondary); gap: 12px; }
.image-slot { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; height: 100%; background: var(--el-fill-color-light); color: var(--el-text-color-secondary); font-size: 12px; gap: 8px; }

.file-preview-wrapper.mini { padding: 10px; flex-direction: row; justify-content: flex-start; align-items: flex-start; background-color: var(--el-fill-color-blank); border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.file-preview-image.mini { width: 80px; height: 80px; flex-shrink: 0; margin-right: 12px; }
.file-generic.mini { flex-direction: row; padding: 8px; width: auto; max-width: none; background: none; border: none; gap: 8px; font-size: 13px; }
.mini-empty { color: var(--el-text-color-placeholder); font-style: italic; font-size: 13px; padding: 8px 0; }

.multi-preview-item { margin-bottom: 10px; }
.multi-preview-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; font-weight: bold; }
</style>
