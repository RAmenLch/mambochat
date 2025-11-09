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
        <el-tooltip content="点击上传新头像" placement="top" :show-after="500">
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
        删除
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { type Component } from 'vue';
import { ElMessage } from 'element-plus';
import { Delete } from '@element-plus/icons-vue';
import type { UploadRequestOptions, UploadRawFile } from 'element-plus';

const props = defineProps<{
  title: string;
  avatarUrl: string | null;
  icon: Component;
  isLoading: boolean;
}>();

const emit = defineEmits<{
  (e: 'upload', file: File): void;
  (e: 'delete'): void;
}>();

const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];
const MAX_FILE_SIZE_MB = 5;

const handleBeforeUpload = (rawFile: UploadRawFile): boolean => {
  if (!ALLOWED_MIME_TYPES.includes(rawFile.type)) {
    ElMessage.error(`文件类型无效。只允许上传 ${ALLOWED_MIME_TYPES.join(', ')} 格式的图片。`);
    return false;
  }
  if (rawFile.size / 1024 / 1024 > MAX_FILE_SIZE_MB) {
    ElMessage.error(`文件过大。图片大小不能超过 ${MAX_FILE_SIZE_MB}MB。`);
    return false;
  }
  return true;
};

const handleHttpRequest = (options: UploadRequestOptions) => {
  // 自定义上传行为, 仅将文件 emit 出去, 由父组件处理实际的上传逻辑
  emit('upload', options.file);
};

const handleDelete = () => {
  emit('delete');
};
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
  font-size: 40px; /* Icon size */
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  transition: box-shadow 0.2s ease-in-out;
}

.avatar-uploader-trigger:hover :deep(.el-avatar) {
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
}

.actions-wrapper {
  height: 22px; /* 占位以防止删除按钮出现/消失时布局跳动 */
}
</style>
