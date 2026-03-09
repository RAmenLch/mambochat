<!-- frontend/mambo/src/components/settings/dialogs/SkillFormDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="t('resource.tree.newSkill')"
    width="600px"
    @update:model-value="$emit('update:visible', $event)"
    @close="resetState"
  >
    <el-tabs v-model="activeTab" class="import-tabs">
      <!-- Tab 1: 手动创建 -->
      <el-tab-pane :label="t('resource.skill.tabCreate')" name="create">
        <el-form :model="manualForm" label-position="top" ref="manualFormRef">
          <el-form-item
            :label="t('resource.meta.name')"
            prop="name"
            :rules="[{ required: true, message: 'Name is required' }]"
          >
            <el-input v-model="manualForm.name" />
          </el-form-item>
          <el-form-item :label="t('resource.meta.description')" prop="description">
            <el-input v-model="manualForm.description" type="textarea" :rows="3" />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <!-- Tab 2: 文件导入 -->
      <el-tab-pane :label="t('resource.skill.tabFile')" name="file">
        <div class="upload-section">
          <el-alert
            :title="t('resource.skill.uploadTip')"
            type="info"
            show-icon
            :closable="false"
            style="margin-bottom: 16px;"
          />

          <!-- 单文件/ZIP 上传 -->
          <el-upload
            ref="uploadRef"
            drag
            action="#"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-exceed="handleExceed"
            accept=".md,.zip"
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">
              {{ t('resource.skill.dropFile') }} <em>{{ t('resource.skill.clickUpload') }}</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                {{ t('resource.skill.fileTip') }}
              </div>
            </template>
          </el-upload>

          <el-divider>{{ t('common.or') }}</el-divider>

          <!-- 文件夹上传 (webkitdirectory) -->
          <div class="folder-upload-wrapper">
             <input
              ref="folderInputRef"
              type="file"
              webkitdirectory
              directory
              multiple
              style="display: none"
              @change="handleFolderSelect"
            />
            <el-button type="primary" plain @click="triggerFolderSelect">
              <el-icon class="el-icon--left"><FolderAdd /></el-icon>
              {{ t('resource.skill.selectFolder') }}
            </el-button>
            <div class="folder-tip" v-if="selectedFolderName">
              <el-icon><Folder /></el-icon>
              <span>{{ selectedFolderName }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 3: GitHub 导入 -->
      <el-tab-pane :label="t('resource.skill.tabGithub')" name="github">
        <el-form :model="githubForm" label-position="top">
          <el-form-item :label="t('resource.skill.githubUrl')">
            <el-input
              v-model="githubForm.url"
              placeholder="https://github.com/user/repo"
              clearable
            >
              <template #prefix>
                <el-icon><Link /></el-icon>
              </template>
            </el-input>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="$emit('update:visible', false)">{{ t('common.action.cancel') }}</el-button>
        <el-button
          type="primary"
          @click="handleConfirm"
          :loading="isSubmitting"
        >
          {{ t('common.action.confirm') }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, genFileId, type UploadInstance, type UploadProps, type UploadRawFile } from 'element-plus'
import { UploadFilled, FolderAdd, Folder, Link } from '@element-plus/icons-vue'
import JSZip from 'jszip'
import { importSkillFromFile, importSkillFromGithub } from '@/api/resourceService'
import type { SkillImportResponse } from '@/api/types'

const props = defineProps<{
  visible: boolean
  parentId?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'confirm', data: any): void
  (e: 'import-success', data: SkillImportResponse): void
}>()

const { t } = useI18n()

// --- State ---
const activeTab = ref('create')
const isSubmitting = ref(false)
const uploadRef = ref<UploadInstance>()
const folderInputRef = ref<HTMLInputElement>()

const manualForm = ref({ name: '', description: '' })
const githubForm = ref({ url: '' })
const selectedFolderName = ref('')
const pendingFiles = ref<File[]>([]) // 用于存储待上传的文件

// --- Handlers ---

const resetState = () => {
  manualForm.value = { name: '', description: '' }
  githubForm.value = { url: '' }
  selectedFolderName.value = ''
  pendingFiles.value = []
  activeTab.value = 'create'
  uploadRef.value?.clearFiles()
}

const handleConfirm = async () => {
  isSubmitting.value = true
  try {
    if (activeTab.value === 'create') {
      // 原有的手动创建逻辑
      if (!manualForm.value.name) {
        ElMessage.warning(t('resource.skill.nameRequired'))
        return
      }
      emit('confirm', { ...manualForm.value })
      emit('update:visible', false)
    } else if (activeTab.value === 'file') {
      await handleFileImport()
    } else if (activeTab.value === 'github') {
      await handleGithubImport()
    }
  } catch (error) {
    console.error(error)
  } finally {
    isSubmitting.value = false
  }
}

// --- File Import Logic ---

const handleFileChange: UploadProps['onChange'] = (uploadFile) => {
  // 单文件替换逻辑
  if (uploadFile.status === 'ready') {
    selectedFolderName.value = '' // 清空文件夹选择
    pendingFiles.value = [uploadFile.raw as File]
  }
}

const handleExceed: UploadProps['onExceed'] = (files) => {
  uploadRef.value!.clearFiles()
  const file = files[0] as UploadRawFile
  file.uid = genFileId()
  uploadRef.value!.handleStart(file)
  pendingFiles.value = [file]
}

const triggerFolderSelect = () => {
  folderInputRef.value?.click()
}

const handleFolderSelect = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return

  uploadRef.value?.clearFiles() // 清空拖拽区的文件
  pendingFiles.value = []

  const files = Array.from(input.files)

  // 获取根目录名称用于显示
  const relativePath = files[0].webkitRelativePath
  const rootFolder = relativePath.split('/')[0]
  selectedFolderName.value = rootFolder

  // 前端打包逻辑：将文件夹内容打包为 ZIP
  const zip = new JSZip()

  // 遍历文件添加到 zip
  for (const file of files) {
    // webkitRelativePath 包含了根文件夹名称，这正是我们需要的结构
    zip.file(file.webkitRelativePath, file)
  }

  const blob = await zip.generateAsync({ type: 'blob' })
  // 创建以根文件夹命名的 zip 文件
  const zipFile = new File([blob], `${rootFolder}.zip`, { type: 'application/zip' })

  pendingFiles.value = [zipFile]
}

const handleFileImport = async () => {
  if (pendingFiles.value.length === 0) {
    ElMessage.warning(t('resource.skill.selectFileFirst'))
    return
  }

  const fileToUpload = pendingFiles.value[0]

  try {
    const result = await importSkillFromFile(fileToUpload, props.parentId || null)
    handleImportResult(result)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.error.general'))
  }
}

// --- Github Import Logic ---

const handleGithubImport = async () => {
  if (!githubForm.value.url) {
    ElMessage.warning(t('resource.skill.urlRequired'))
    return
  }

  try {
    const result = await importSkillFromGithub(githubForm.value.url, props.parentId || null)
    handleImportResult(result)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || t('common.error.general'))
  }
}

// --- Result Handling ---

const handleImportResult = (result: SkillImportResponse) => {
  if (result.success_count > 0) {
    ElMessage.success(t('resource.skill.importSuccess', { count: result.success_count }))
    emit('import-success', result)
    emit('update:visible', false)
  }

  if (result.failed_count > 0) {
    // 展示部分失败详情，这里简单展示第一条错误
    const firstError = result.details.find(d => d.status === 'failed')
    if (firstError) {
        ElMessage.warning(`${t('resource.skill.importPartial')}: ${firstError.name} - ${firstError.error}`)
    }
  }
}
</script>

<style scoped>
.import-tabs {
  min-height: 300px;
}

.upload-section {
  padding: 10px 0;
}

.folder-upload-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.folder-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
