<!-- frontend/mambo/src/components/common/dialogs/ResourceSelectorPreview.vue -->
<template>
  <el-main class="resource-preview-main">
    <el-empty v-if="selectedResources.length === 0" :description="$t('resource.editor.placeholder')" />

    <!-- 单选预览 -->
    <div v-else-if="selectedResources.length === 1" class="preview-card">
      <div class="preview-header">
        <strong>{{ $t('resource.selector.previewHeader', { name: selectedResources[0].name }) }}</strong>
      </div>

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

            <!-- 可在线编辑的文本文件：直接预览文件内容 -->
            <template v-else-if="isTextPreviewable(selectedResources[0])">
              <div class="file-text-header">
                <el-icon><Document /></el-icon>
                <span class="file-name" :title="currentFileInfo.filename">{{ currentFileInfo.filename }}</span>
                <span class="file-size">{{ formatFileSize(currentFileInfo.size) }}</span>
                <a :href="currentFileInfo.url" target="_blank" class="download-link">
                  <el-button type="primary" link icon="Download">{{ $t('resource.editor.downloadFile') }}</el-button>
                </a>
              </div>
              <pre v-if="getFileText(selectedResources[0]) !== undefined" class="preview-content">{{ getFileText(selectedResources[0]) }}</pre>
              <div v-else class="file-text-state">
                <el-icon v-if="!isFileTextFailed(selectedResources[0])" class="is-loading"><Loading /></el-icon>
                <span>{{ isFileTextFailed(selectedResources[0]) ? $t('resource.selector.noFileContent') : $t('resource.selector.loadingContent') }}</span>
              </div>
            </template>

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
          <div v-else-if="isPreviewLoading" class="file-empty-state">
            <el-icon :size="48" class="is-loading"><Loading /></el-icon>
            <p>{{ $t('resource.selector.loadingContent') }}</p>
          </div>
          <div v-else class="file-empty-state">
            <el-icon :size="48"><Document /></el-icon>
            <p>{{ $t('resource.selector.noFileContent') }}</p>
          </div>
        </template>

        <!-- Text Resource Preview -->
        <pre v-else class="preview-content">{{ selectedResources[0].latest_version?.content || $t('resource.selector.noContent') }}</pre>
      </el-scrollbar>
    </div>

    <!-- 多选预览 -->
    <div v-else class="preview-card">
      <div class="preview-header">
        <strong>{{ $t('resource.selector.multiPreview', { count: selectedResources.length }) }}</strong>
      </div>

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
            <div v-if="isResourceImage(res) && res.latest_version?.file_info" class="file-preview-wrapper mini">
              <div class="file-preview-image mini">
                <el-image :src="res.latest_version.file_info.url" :preview-src-list="[res.latest_version.file_info.url]" fit="contain" style="width: 100%; height: 100%;" />
              </div>
            </div>

            <!-- 可在线编辑的文本文件：与文本资源一致地展示内容 -->
            <template v-else-if="isTextPreviewable(res)">
              <div class="file-text-header mini">
                <el-icon><Document /></el-icon>
                <span class="file-name" :title="fileInfoOf(res)?.filename || ''">{{ fileInfoOf(res)?.filename }}</span>
                <span class="file-size">{{ formatFileSize(fileInfoOf(res)?.size || 0) }}</span>
              </div>
              <pre v-if="getFileText(res) !== undefined" class="preview-content">{{ getFileText(res) }}</pre>
              <div v-else class="file-text-state">
                <el-icon v-if="!isFileTextFailed(res)" class="is-loading"><Loading /></el-icon>
                <span>{{ isFileTextFailed(res) ? $t('resource.selector.noFileContent') : $t('resource.selector.loadingContent') }}</span>
              </div>
            </template>

            <div v-else-if="res.latest_version?.file_info" class="file-generic mini">
              <el-icon><Document /></el-icon>
              <span>{{ res.latest_version.file_info.filename }}</span>
            </div>
            <div v-else class="mini-empty">
              {{ isPreviewLoading ? $t('resource.selector.loadingContent') : $t('resource.selector.noFile') }}
            </div>
          </template>

          <pre v-else class="preview-content">{{ res.latest_version?.content || $t('resource.selector.noContent') }}</pre>

          <el-divider v-if="index < selectedResources.length - 1" border-style="dashed" />
        </div>
      </el-scrollbar>
    </div>
  </el-main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Document, Picture, Collection, Reading, Loading } from '@element-plus/icons-vue';
import type { FileResponse, Resource } from '@/api/types';
import { getFileContent } from '@/api/fileService';

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

const fileInfoOf = (resource: Resource): FileResponse | null =>
  resource.latest_version?.file_info || null;

/** 仅 DB 存储的可编辑文本文件（非图片）支持内容预览 */
const isTextPreviewable = (resource: Resource): boolean => {
  const info = fileInfoOf(resource);
  return resource.resourceType === 'file' && !!info && info.editable && !isResourceImage(resource);
};

// --- 可编辑文件内容 ---
// 注意：File 资源的 version.content 存的是 file_id，不是文本，
// 因此这里直接调用文件内容接口，只在组件内缓存，避免污染 store 数据。
const fileTexts = ref<Record<string, string>>({});
const fileTextErrors = ref<Record<string, boolean>>({});
const pendingIds = new Set<string>();

const getFileText = (resource: Resource): string | undefined => fileTexts.value[resource.id];
const isFileTextFailed = (resource: Resource): boolean => !!fileTextErrors.value[resource.id];

const loadFileText = async (resource: Resource) => {
  const info = fileInfoOf(resource);
  if (!info || !isTextPreviewable(resource)) return;
  if (getFileText(resource) !== undefined || isFileTextFailed(resource) || pendingIds.has(resource.id)) return;

  pendingIds.add(resource.id);
  try {
    const { content } = await getFileContent(info.id);
    fileTexts.value = { ...fileTexts.value, [resource.id]: content };
  } catch (error) {
    console.error(`Failed to load preview content for file ${info.id}:`, error);
    fileTextErrors.value = { ...fileTextErrors.value, [resource.id]: true };
  } finally {
    pendingIds.delete(resource.id);
  }
};

const previewableFileIds = computed(() =>
  props.selectedResources
    .filter((resource) => isTextPreviewable(resource))
    .map((resource) => resource.id)
    .join('|'),
);

watch(
  previewableFileIds,
  () => {
    // 取消选择 / 关闭弹窗后清理缓存，避免下次打开时展示旧内容
    const currentIds = new Set(props.selectedResources.map((resource) => resource.id));

    const retainedTexts: Record<string, string> = {};
    const retainedErrors: Record<string, boolean> = {};
    Object.keys(fileTexts.value).forEach((id) => {
      if (currentIds.has(id)) retainedTexts[id] = fileTexts.value[id];
    });
    Object.keys(fileTextErrors.value).forEach((id) => {
      if (currentIds.has(id)) retainedErrors[id] = fileTextErrors.value[id];
    });
    fileTexts.value = retainedTexts;
    fileTextErrors.value = retainedErrors;

    props.selectedResources.forEach((resource) => void loadFileText(resource));
  },
  { immediate: true },
);

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};
</script>

<style scoped>
.resource-preview-main {
  padding: 0;
  background-color: var(--el-bg-color);
  display: flex;
  flex-direction: column;
}

.preview-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.preview-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 16px;
  color: var(--el-text-color-primary);
  background-color: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(8px);
  z-index: 10;
}

.preview-scrollbar {
  padding: 24px;
}

.preview-content {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Fira Code', var(--el-font-family-monospace), monospace;
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
  padding: 20px;
  background-color: var(--el-fill-color-light);
  border-radius: 8px;
  color: var(--el-text-color-regular);
}

.kb-preview-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.kb-preview-wrapper h3 {
  margin: 16px 0 8px;
  color: var(--el-text-color-primary);
}

.kb-desc {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  max-width: 400px;
  line-height: 1.5;
}

.file-preview-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  gap: 16px;
  width: 100%;
}

.file-preview-image {
  width: 100%;
  max-height: 400px;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f5f5f5;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}

.preview-img {
  width: 100%;
  height: 100%;
}

.file-generic {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 32px;
  border-radius: 12px;
  background-color: var(--el-fill-color-lighter);
  width: 100%;
  max-width: 320px;
  text-align: center;
  margin: 0 auto;
}

.file-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
  word-break: break-all;
}

.file-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.file-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--el-text-color-secondary);
  gap: 12px;
}

.image-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  gap: 8px;
}

.file-preview-wrapper.mini {
  padding: 10px;
  flex-direction: row;
  justify-content: flex-start;
  align-items: flex-start;
  background-color: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.file-preview-image.mini {
  width: 80px;
  height: 80px;
  flex-shrink: 0;
  margin-right: 12px;
}

.file-generic.mini {
  flex-direction: row;
  padding: 8px;
  width: auto;
  max-width: none;
  background: none;
  border: none;
  gap: 8px;
  font-size: 13px;
}

.file-text-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  box-sizing: border-box;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background-color: var(--el-fill-color-lighter);
}

.file-text-header.mini {
  padding: 6px 12px;
  margin-bottom: 8px;
}

.file-text-header .file-name {
  flex: 1;
  min-width: 0;
  text-align: left;
  font-size: 13px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.file-text-header .file-size,
.file-text-header .download-link {
  flex-shrink: 0;
}

.file-text-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 32px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.file-preview-wrapper .preview-content {
  width: 100%;
}

.mini-empty {
  color: var(--el-text-color-placeholder);
  font-style: italic;
  font-size: 13px;
  padding: 8px 0;
}

.multi-preview-item {
  margin-bottom: 24px;
}

.multi-preview-label {
  font-size: 14px;
  color: var(--el-color-primary);
  margin-bottom: 8px;
  font-weight: 600;
  display: flex;
  align-items: center;
}

.multi-preview-label::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 14px;
  background-color: var(--el-color-primary);
  border-radius: 2px;
  margin-right: 8px;
}
</style>
