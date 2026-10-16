<!-- frontend/mambo/src/components/chat/group/GroupMailAttachments.vue -->
<template>
  <div v-if="attachments.length" class="group-attachments">
    <!-- 图片：按数量自适应尺寸的缩略图网格 -->
    <div v-if="images.length" class="image-grid" :class="gridClass">
      <button
        v-for="att in images"
        :key="att.fileId"
        type="button"
        class="image-cell"
        :title="att.filename || ''"
        @click="open(att)"
      >
        <el-image :src="att.url || ''" fit="cover" class="image-thumb" lazy>
          <template #error>
            <div class="image-fallback"><el-icon><Picture /></el-icon></div>
          </template>
          <template #placeholder>
            <div class="image-fallback"><el-icon class="is-loading"><Loading /></el-icon></div>
          </template>
        </el-image>
        <span class="image-zoom"><el-icon><ZoomIn /></el-icon></span>
      </button>
    </div>

    <!-- 非图片文件：文件条 -->
    <div v-if="files.length" class="file-list">
      <button
        v-for="att in files"
        :key="att.fileId"
        type="button"
        class="file-chip"
        :title="att.filename || ''"
        @click="open(att)"
      >
        <el-icon class="chip-icon"><Document /></el-icon>
        <span class="chip-name">{{ att.filename || att.fileId }}</span>
        <span v-if="att.sizeBytes" class="chip-size">{{ formatSize(att.sizeBytes) }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Document, Loading, Picture, ZoomIn } from '@element-plus/icons-vue';
import type { GroupMailAttachment } from '@/api/types/groupChatTypes';

const props = defineProps<{
  attachments: GroupMailAttachment[];
}>();

const emit = defineEmits<{
  (e: 'preview', attachments: GroupMailAttachment[], index: number): void;
}>();

function open(att: GroupMailAttachment) {
  const i = props.attachments.indexOf(att);
  emit('preview', props.attachments, i < 0 ? 0 : i);
}

function isImage(att: GroupMailAttachment): boolean {
  return !!att.mimeType?.startsWith('image/') && !!att.url;
}

const images = computed(() => props.attachments.filter(isImage));
const files = computed(() => props.attachments.filter((a) => !isImage(a)));

/** 依据图片数量决定网格列数/单张尺寸，避免大图占满邮件卡 */
const gridClass = computed(() => {
  const n = images.value.length;
  if (n === 1) return 'is-single';
  if (n <= 4) return 'is-few';
  return 'is-many';
});

function formatSize(size: number): string {
  if (!size) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
</script>

<style scoped>
.group-attachments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

/* --- 图片网格 --- */
.image-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.image-cell {
  position: relative;
  padding: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
  line-height: 0;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.image-cell:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}
.image-thumb {
  display: block;
  transition: transform 0.18s ease;
}
.image-cell:hover .image-thumb {
  transform: scale(1.05);
}
/* 尺寸随数量自适应 */
.image-grid.is-single .image-thumb {
  width: 200px;
  height: 150px;
}
.image-grid.is-single .image-cell {
  max-width: 100%;
}
.image-grid.is-few .image-thumb {
  width: 88px;
  height: 88px;
}
.image-grid.is-many .image-thumb {
  width: 64px;
  height: 64px;
}
.image-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-width: 64px;
  min-height: 64px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
}
/* 悬停放大提示角标 */
.image-zoom {
  position: absolute;
  right: 4px;
  bottom: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: #fff;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.image-cell:hover .image-zoom {
  opacity: 1;
}

/* --- 文件条 --- */
.file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 240px;
  padding: 4px 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  font-size: 12px;
  font-family: inherit;
  color: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.file-chip:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-fill-color-light);
}
.chip-icon {
  font-size: 16px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip-size {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
</style>
