<!-- frontend/mambo/src/components/chat/group/GroupMailAttachmentViewer.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    width="min(880px, 92vw)"
    top="5vh"
    append-to-body
    destroy-on-close
    :show-close="false"
    class="group-attachment-dialog"
  >
    <template #header="{ close }">
      <div class="gav-header">
        <div class="gav-heading">
          <span class="gav-heading-icon"><el-icon><component :is="typeIcon" /></el-icon></span>
          <div class="gav-heading-text">
            <div class="gav-filename" :title="current?.filename || ''">
              {{ current?.filename || '' }}
            </div>
            <div class="gav-meta">{{ metaText }}</div>
          </div>
        </div>
        <div class="gav-actions">
          <span v-if="total > 1" class="gav-counter">{{ index + 1 }} / {{ total }}</span>
          <a
            v-if="current?.url"
            :href="current.url"
            :download="current.filename || ''"
            class="gav-download"
          >
            <el-button size="small" :icon="Download" text bg>
              {{ t('groupChat.attachment.download') }}
            </el-button>
          </a>
          <el-button :icon="Close" circle text @click="close" />
        </div>
      </div>
    </template>

    <div v-if="current" class="gav-body" :class="{ 'is-image': isImage }">
      <el-image
        v-if="isImage"
        :src="current.url || ''"
        :preview-src-list="imageUrls"
        :initial-index="imageIndexOfCurrent"
        fit="contain"
        hide-on-click-modal
        class="gav-image"
      >
        <template #error>
          <div class="gav-status">{{ t('groupChat.attachment.loadFailed') }}</div>
        </template>
      </el-image>

      <audio
        v-else-if="isAudio"
        :src="current.url || ''"
        controls
        preload="metadata"
        class="gav-audio"
      />

      <video
        v-else-if="isVideo"
        :src="current.url || ''"
        controls
        preload="metadata"
        class="gav-video"
      />

      <iframe v-else-if="isPdf" :src="current.url || ''" class="gav-frame" />

      <template v-else-if="isTextLike">
        <div v-if="loading" class="gav-status">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-else-if="error" class="gav-status">{{ error }}</div>
        <pre v-else class="gav-text">{{ content }}</pre>
      </template>

      <div v-else class="gav-status gav-status-empty">
        <el-icon :size="34"><Document /></el-icon>
        <span>{{ t('groupChat.attachment.noPreview') }}</span>
      </div>
    </div>

    <!-- 多附件切换：底部切换栏（左右按钮 + 缩略图条） -->
    <div v-if="total > 1" class="gav-footer">
      <button
        type="button"
        class="gav-arrow"
        :title="t('groupChat.attachment.prev')"
        @click="step(-1)"
      >
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <div ref="thumbsRef" class="gav-thumbs">
        <button
          v-for="(att, i) in attachments"
          :key="att.fileId"
          type="button"
          class="gav-thumb"
          :class="{ 'is-active': i === index }"
          :title="att.filename || ''"
          @click="select(i)"
        >
          <el-image
            v-if="isImg(att)"
            :src="att.url || ''"
            fit="cover"
            class="gav-thumb-img"
          >
            <template #error><el-icon><Document /></el-icon></template>
          </el-image>
          <el-icon v-else class="gav-thumb-icon"><Document /></el-icon>
        </button>
      </div>
      <button
        type="button"
        class="gav-arrow"
        :title="t('groupChat.attachment.next')"
        @click="step(1)"
      >
        <el-icon><ArrowRight /></el-icon>
      </button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  ArrowLeft,
  ArrowRight,
  Close,
  Document,
  Download,
  Headset,
  Loading,
  Picture,
  VideoCamera,
} from '@element-plus/icons-vue';
import type { GroupMailAttachment } from '@/api/types/groupChatTypes';
import { getFileContent } from '@/api/fileService';

const props = defineProps<{
  visible: boolean;
  attachments: GroupMailAttachment[];
  index: number;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'update:index', value: number): void;
}>();

const { t } = useI18n();

const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
});

const total = computed(() => props.attachments.length);
const current = computed(() => props.attachments[props.index] ?? null);

const mime = computed(() => current.value?.mimeType || '');
const isAudio = computed(() => mime.value.startsWith('audio/'));
const isVideo = computed(() => mime.value.startsWith('video/'));
const isPdf = computed(() => mime.value === 'application/pdf');

function isImg(att: GroupMailAttachment | null | undefined): boolean {
  return !!att && !!att.mimeType?.startsWith('image/') && !!att.url;
}
const isImage = computed(() => isImg(current.value));

const isTextLike = computed(() => {
  const m = mime.value;
  // 先排除图像/音视频：注意 image/svg+xml 也以 "+xml" 结尾，不能按后缀一概判定为文本
  if (m.startsWith('image/') || m.startsWith('audio/') || m.startsWith('video/')) {
    return false;
  }
  return (
    m.startsWith('text/') ||
    m === 'application/json' ||
    m === 'application/xml' ||
    m === 'application/javascript' ||
    m === 'application/x-sh' ||
    (m.startsWith('application/') && (m.endsWith('+json') || m.endsWith('+xml')))
  );
});

const imageUrls = computed(() =>
  props.attachments.filter(isImg).map((a) => a.url as string),
);
const imageIndexOfCurrent = computed(() => {
  if (!isImage.value) return 0;
  return props.attachments
    .filter(isImg)
    .findIndex((a) => a.fileId === current.value?.fileId);
});

const typeIcon = computed(() => {
  if (isImage.value) return Picture;
  if (isVideo.value) return VideoCamera;
  if (isAudio.value) return Headset;
  return Document;
});

const metaText = computed(() => {
  const att = current.value;
  if (!att) return '';
  const parts = [att.mimeType || '', att.sizeBytes ? formatSize(att.sizeBytes) : ''].filter(Boolean);
  return parts.join(' · ');
});

const loading = ref(false);
const error = ref('');
const content = ref('');

function formatSize(size: number): string {
  if (!size) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function select(i: number) {
  if (i < 0 || i >= total.value || i === props.index) return;
  emit('update:index', i);
}

/** 循环切换（自由浏览） */
function step(delta: number) {
  if (total.value <= 1) return;
  const next = (props.index + delta + total.value) % total.value;
  emit('update:index', next);
}

function onKeydown(e: KeyboardEvent) {
  if (!props.visible || total.value <= 1) return;
  if (e.key === 'ArrowLeft') {
    e.preventDefault();
    step(-1);
  } else if (e.key === 'ArrowRight') {
    e.preventDefault();
    step(1);
  }
}

async function loadText() {
  const att = current.value;
  if (!att || !isTextLike.value) return;
  loading.value = true;
  error.value = '';
  content.value = '';
  try {
    const res = await getFileContent(att.fileId);
    content.value = res?.content ?? '';
  } catch (e) {
    console.error('Failed to load attachment content:', e);
    error.value = t('groupChat.attachment.loadFailed');
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.visible, props.index, current.value?.fileId],
  () => {
    if (props.visible && isTextLike.value) {
      loadText();
    } else if (!props.visible) {
      content.value = '';
      error.value = '';
    }
  },
);

onMounted(() => window.addEventListener('keydown', onKeydown));
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown));

// 切换附件时把当前缩略图滚动到可见区域
const thumbsRef = ref<HTMLElement | null>(null);
watch(
  () => props.index,
  async () => {
    await nextTick();
    const el = thumbsRef.value?.querySelector('.gav-thumb.is-active') as HTMLElement | null;
    el?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  },
);
</script>

<style scoped>
/* 头部 */
.gav-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.gav-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.gav-heading-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  flex-shrink: 0;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  font-size: 18px;
}
.gav-heading-text {
  min-width: 0;
}
.gav-filename {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 40vw;
}
.gav-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gav-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.gav-counter {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
}
.gav-download {
  text-decoration: none;
}

/* 内容舞台 */
.gav-body {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  max-height: 72vh;
  overflow: auto;
  border-radius: 10px;
  background-color: var(--el-fill-color-lighter);
  padding: 12px;
}
.gav-body.is-image {
  background-color: var(--el-fill-color-light);
}
/* 文本模式下由 .gav-text 自己控制限高/滚动，body 不再钳制高度 */
.gav-body:has(.gav-text) {
  max-height: none;
  overflow: visible;
}
/* 让图片按比例自适应容器大小 */
.gav-image {
  max-width: 100%;
  max-height: 68vh;
}
.gav-image :deep(.el-image__inner) {
  width: auto;
  height: auto;
  max-width: 100%;
  max-height: 68vh;
  object-fit: contain;
  border-radius: 6px;
  cursor: zoom-in;
}
.gav-audio,
.gav-video {
  width: min(100%, 640px);
  max-height: 68vh;
  border-radius: 8px;
}
.gav-frame {
  width: 100%;
  height: 68vh;
  border: none;
  border-radius: 8px;
  background: #fff;
}
/* 文本模式：白色卡片自身限高并在内部滚动，避免长文本溢出到 body 的灰色背景 */
.gav-text {
  align-self: stretch;
  width: 100%;
  max-height: 68vh;
  overflow: auto;
  margin: 0;
  padding: 14px 16px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--el-font-family-mono, ui-monospace, Menlo, Consolas, monospace);
  font-size: 13px;
  line-height: 1.65;
  color: var(--el-text-color-primary);
}
.gav-status {
  padding: 40px;
  color: var(--el-text-color-secondary);
  text-align: center;
}
.gav-status-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

/* 底部切换栏 */
.gav-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.gav-arrow {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 50%;
  cursor: pointer;
  color: var(--el-text-color-regular);
  font-size: 16px;
  background: var(--el-bg-color);
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.gav-arrow:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

/* 缩略图条 */
.gav-thumbs {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 2px;
  overflow-x: auto;
}
.gav-thumb {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
  transition: border-color 0.15s ease, opacity 0.15s ease;
  opacity: 0.72;
}
.gav-thumb:hover {
  opacity: 1;
}
.gav-thumb.is-active {
  border-color: var(--el-color-primary);
  opacity: 1;
}
.gav-thumb-img {
  width: 100%;
  height: 100%;
}
.gav-thumb-icon {
  font-size: 20px;
  color: var(--el-text-color-secondary);
}
</style>

<style>
/* 弹窗外壳（el-dialog 被 teleport 到 body，需用非 scoped 样式配合专属类名） */
.group-attachment-dialog.el-dialog {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  padding: 0;
}
.group-attachment-dialog .el-dialog__header {
  margin: 0;
  padding: 14px 18px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.group-attachment-dialog .el-dialog__body {
  padding: 16px;
}
</style>
