<!-- frontend/mambo/src/mobile/components/chat/AttachmentPreview.vue -->
<template>
  <div class="mobile-attachment-preview">
    <!-- Knowledge Bases -->
    <div v-if="attachedKnowledgeBases.length > 0" class="preview-section">
      <!-- 添加 scrollable 类 -->
      <div class="preview-list horizontal scrollable">
        <div
          v-for="kb in attachedKnowledgeBases"
          :key="kb.id"
          class="preview-tag kb"
          @click="handlePreviewKB(kb)"
        >
          <el-icon class="tag-icon"><Search /></el-icon>
          <span class="tag-name">{{ kb.name }}</span>
          <!-- 使用 .stop 防止点击关闭时触发预览 -->
          <el-icon class="remove-icon" @click.stop="$emit('remove-knowledge-base', kb.id)">
            <Close />
          </el-icon>
        </div>
      </div>
    </div>

    <!-- Resources (Templates) -->
    <div v-if="attachedResources.length > 0" class="preview-section">
      <div class="preview-list horizontal scrollable">
        <div
          v-for="resource in attachedResources"
          :key="resource.id"
          class="preview-tag resource"
          @click="handlePreviewResource(resource)"
        >
          <span class="tag-name">{{ resource.name }}</span>
          <el-icon class="remove-icon" @click.stop="$emit('remove-resource', resource.id)">
            <Close />
          </el-icon>
        </div>
      </div>
    </div>

    <!-- Uploaded Files -->
    <div v-if="uploadedFiles.length > 0" class="preview-section">
      <div class="preview-list horizontal scrollable">
        <div v-for="(file, index) in uploadedFiles" :key="file.id" class="file-card">
          <el-image
            v-if="file.mime_type.startsWith('image/')"
            :src="file.url"
            fit="cover"
            class="file-image"
            :preview-src-list="imagePreviewList"
            :initial-index="index"
          >
            <template #error>
              <div class="image-error">
                <el-icon><Picture /></el-icon>
              </div>
            </template>
          </el-image>
          <!-- 非图片文件点击显示信息 -->
          <div v-else class="file-icon-wrapper" @click="handlePreviewFile(file)">
             <el-icon class="file-icon"><Document /></el-icon>
          </div>
          <div class="file-info">
            <span class="file-name">{{ file.filename }}</span>
          </div>
          <el-button
            class="remove-file-btn"
            :icon="Close"
            circle
            size="small"
            @click.stop="$emit('remove-file', file.id)"
          />
        </div>
      </div>
    </div>

    <!-- 通用预览弹窗 (用于资源/知识库/文件信息) -->
    <el-dialog
      v-model="previewVisible"
      :title="previewTitle"
      class="mobile-preview-dialog"
      append-to-body
      destroy-on-close
    >
      <el-scrollbar max-height="50vh">
        <div class="preview-dialog-content">
          <pre>{{ previewContent }}</pre>
        </div>
      </el-scrollbar>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PropType } from 'vue'
import type { FileResponse, Resource } from '@/api/types'
import { Document, Picture, Close, Search } from '@element-plus/icons-vue'

// --- Props Definition ---
const props = defineProps({
  uploadedFiles: {
    type: Array as PropType<FileResponse[]>,
    required: true,
  },
  attachedResources: {
    type: Array as PropType<Resource[]>,
    required: true,
  },
  attachedKnowledgeBases: {
    type: Array as PropType<Resource[]>,
    default: () => [],
  },
})

// --- Emits Definition ---
defineEmits<{
  (e: 'remove-file', fileId: string): void
  (e: 'remove-resource', resourceId: string): void
  (e: 'remove-knowledge-base', resourceId: string): void
}>()

// --- Preview Logic ---
const previewVisible = ref(false)
const previewTitle = ref('')
const previewContent = ref('')

const handlePreviewResource = (resource: Resource) => {
  previewTitle.value = resource.name
  previewContent.value = resource.latest_version?.content || '无内容预览'
  previewVisible.value = true
}

const handlePreviewKB = (kb: Resource) => {
  previewTitle.value = kb.name
  previewContent.value = kb.description || '暂无描述'
  previewVisible.value = true
}

const handlePreviewFile = (file: FileResponse) => {
  previewTitle.value = file.filename
  previewContent.value = `文件类型: ${file.mime_type}\n文件大小: ${(file.size / 1024).toFixed(2)} KB`
  previewVisible.value = true
}

// --- Image Preview Logic ---
// 提取图片URL列表，供 el-image 组件使用，实现左右滑动预览
const imagePreviewList = computed(() => {
  return props.uploadedFiles
    .filter(f => f.mime_type.startsWith('image/'))
    .map(f => f.url)
})

</script>

<style scoped>
.mobile-attachment-preview {
  padding-top: 8px;
  padding-bottom: 4px;
  background-color: var(--color-background);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.preview-section {
  margin-bottom: 6px;
}

.preview-section:last-child {
  margin-bottom: 0;
}

.preview-list {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 核心修改：开启横向滚动 */
.preview-list.scrollable {
  overflow-x: auto;
  overflow-y: hidden;
  white-space: nowrap;
  -webkit-overflow-scrolling: touch; /* iOS 丝滑滚动 */
  padding-bottom: 4px;
  /* 隐藏滚动条，保持美观 */
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE 10+ */
}

.preview-list.scrollable::-webkit-scrollbar {
  display: none; /* Chrome Safari */
}

.preview-tag {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  flex-shrink: 0; /* 关键：防止标签被压缩 */
  position: relative;
  cursor: pointer;
}

.preview-tag.kb {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.preview-tag.resource {
  background-color: var(--el-color-info-light-9);
  color: var(--el-color-info);
}

.tag-icon {
  margin-right: 4px;
  font-size: 12px;
}

.tag-name {
  max-width: 100px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-icon {
  margin-left: 6px;
  font-size: 12px;
  cursor: pointer;
  opacity: 0.7;
}

.remove-icon:active {
  opacity: 1;
}

/* File Cards */
.file-card {
  position: relative;
  width: 70px;
  height: 70px;
  border-radius: 6px;
  overflow: hidden;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0; /* 关键：防止卡片被压缩 */
  display: flex;
  flex-direction: column;
}

.file-image {
  width: 100%;
  height: 100%;
}

.image-error {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  background: var(--el-fill-color-light);
}

.file-icon-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
}

.file-icon {
  font-size: 24px;
  color: var(--el-text-color-placeholder);
}

.file-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 4px;
}

.file-name {
  display: block;
  font-size: 10px;
  color: white;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-file-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  border: none;
}

.remove-file-btn:active {
  background: rgba(0, 0, 0, 0.7);
}

/* 预览弹窗样式 */
.preview-dialog-content {
  padding: 10px;
  font-size: 14px;
  line-height: 1.6;
  background-color: var(--color-background-soft);
  border-radius: 4px;
}

.preview-dialog-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}
</style>
