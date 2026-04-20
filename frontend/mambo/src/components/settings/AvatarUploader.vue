<template>
  <div class="avatar-uploader-container">
    <h3 class="uploader-title">{{ title }}</h3>
    <div class="avatar-wrapper">
      <el-upload
        action="#"
        :show-file-list="false"
        :before-upload="handleBeforeUpload"
        :http-request="handleHttpRequest"
        accept="image/png, image/jpeg, image/gif, image/webp"
        class="avatar-uploader-trigger"
      >
        <el-tooltip :content="t('settings.avatar.uploadTip')" placement="top" :show-after="500">
          <el-avatar :size="80" :src="avatarUrl || ''" v-loading="isLoading">
            <component :is="icon" v-if="icon" />
          </el-avatar>
        </el-tooltip>
      </el-upload>
    </div>
    <div class="actions-wrapper">
      <el-button
        v-if="avatarUrl"
        type="danger"
        :icon="Delete"
        link
        @click="handleDelete"
        :loading="isLoading"
      >
        {{ t('common.action.delete') }}
      </el-button>
    </div>

    <!-- 裁剪弹窗 -->
    <el-dialog
      v-model="showCropDialog"
      :title="t('settings.avatar.cropTitle')"
      width="500px"
      destroy-on-close
      @opened="initCropper"
      @closed="destroyCropper"
    >
      <div class="cropper-container">
        <img ref="imageRef" :src="previewImageUrl" alt="Preview" class="preview-img" />
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="showCropDialog = false">
            {{ t('common.action.cancel') }}
          </el-button>
          <el-button @click="handleUploadOriginal">
            {{ t('settings.avatar.uploadOriginal') }}
          </el-button>
          <el-button type="primary" @click="handleUploadCropped" :loading="isProcessing">
            {{ t('settings.avatar.cropAndUpload') }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import type { UploadRequestOptions, UploadRawFile } from 'element-plus'
import Cropper from 'cropperjs'
import 'cropperjs/dist/cropper.css'

defineProps<{
  title: string
  avatarUrl: string | null
  icon: Component
  isLoading: boolean
}>()

const emit = defineEmits<{
  (e: 'upload', file: File): void
  (e: 'delete'): void
}>()

const { t } = useI18n()

const ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const MAX_FILE_SIZE_MB = 5

// 裁剪相关的状态
const showCropDialog = ref(false)
const previewImageUrl = ref('')
const selectedFile = ref<File | null>(null)
const imageRef = ref<HTMLImageElement | null>(null)
const isProcessing = ref(false)
let cropperInstance: Cropper | null = null

const handleBeforeUpload = (rawFile: UploadRawFile): boolean => {
  if (!ALLOWED_MIME_TYPES.includes(rawFile.type)) {
    ElMessage.error(
      t('settings.avatar.invalidType', { types: ALLOWED_MIME_TYPES.join(', ') })
    )
    return false
  }
  if (rawFile.size / 1024 / 1024 > MAX_FILE_SIZE_MB) {
    ElMessage.error(t('settings.avatar.tooLarge', { size: MAX_FILE_SIZE_MB }))
    return false
  }
  return true
}

const handleHttpRequest = (options: UploadRequestOptions) => {
  // 拦截默认上传行为，保存文件并打开裁剪弹窗
  selectedFile.value = options.file as File
  previewImageUrl.value = URL.createObjectURL(options.file)
  showCropDialog.value = true
  return Promise.resolve(true)
}

const initCropper = () => {
  if (imageRef.value) {
    cropperInstance = new Cropper(imageRef.value, {
      aspectRatio: 1, // 强制正方形裁剪
      viewMode: 1,    // 限制裁剪框不能超出图片范围
      dragMode: 'move', // 允许拖动图片
      guides: false,
      center: false,
      background: true,
      autoCropArea: 0.8,
    })
  }
}

const destroyCropper = () => {
  if (cropperInstance) {
    cropperInstance.destroy()
    cropperInstance = null
  }
  if (previewImageUrl.value) {
    URL.revokeObjectURL(previewImageUrl.value)
    previewImageUrl.value = ''
  }
  selectedFile.value = null
  isProcessing.value = false
}

// 选择上传原图
const handleUploadOriginal = () => {
  if (selectedFile.value) {
    emit('upload', selectedFile.value)
    showCropDialog.value = false
  }
}

// 选择裁剪并上传
const handleUploadCropped = () => {
  if (!cropperInstance || !selectedFile.value) return

  isProcessing.value = true
  const mimeType = selectedFile.value.type
  const fileName = selectedFile.value.name

  // 获取裁剪后的 Canvas
  const canvas = cropperInstance.getCroppedCanvas({
    // 可以考虑限制最大输出分辨率以防图片过大，这里暂不限制，保持裁剪区域原分辨率
  })

  canvas.toBlob((blob) => {
    if (blob) {
      // 保持原文件名和原格式
      const croppedFile = new File([blob], fileName, { type: mimeType })
      emit('upload', croppedFile)
      showCropDialog.value = false
    } else {
      ElMessage.error(t('settings.avatar.cropFailed'))
      isProcessing.value = false
    }
  }, mimeType)
}

const handleDelete = () => {
  emit('delete')
}
</script>

<style scoped>
.avatar-uploader-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  width: 200px;
}

.uploader-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.avatar-wrapper {
  cursor: pointer;
}

.avatar-uploader-trigger :deep(.el-avatar) {
  font-size: 40px;
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  transition: box-shadow 0.2s ease-in-out;
}

.avatar-uploader-trigger:hover :deep(.el-avatar) {
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
}

.actions-wrapper {
  height: 22px;
}

/* 裁剪器容器样式 */
.cropper-container {
  width: 100%;
  max-height: 400px;
  overflow: hidden;
  background-color: #f8f8f8;
  display: flex;
  justify-content: center;
  align-items: center;
}

.preview-img {
  max-width: 100%;
  max-height: 400px;
  display: block;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
