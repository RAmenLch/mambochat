<!-- frontend/mambo/src/components/settings/dialogs/SkillFormDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="t('resource.tree.newSkill')"
    width="700px"
    class="skill-form-dialog"
    @update:model-value="$emit('update:visible', $event)"
    @close="resetState"
  >
    <div class="dialog-content">
      <el-tabs v-model="activeTab" type="border-card" class="skill-tabs">
        <!-- Tab 1: 手动创建 -->
        <el-tab-pane name="create">
          <template #label>
            <div class="tab-label">
              <el-icon><Edit /></el-icon>
              <span>{{ t('resource.skill.tabCreate') }}</span>
            </div>
          </template>

          <el-form
            :model="manualForm"
            label-position="top"
            ref="manualFormRef"
            :rules="manualRules"
            style="padding: 10px 0"
          >
            <el-form-item :label="t('resource.skill.nameLabel')" prop="name">
              <el-input
                v-model="manualForm.name"
                :placeholder="t('resource.skill.namePlaceholder')"
                @input="manualForm.name = manualForm.name.replace(/[^ -~]/g, '')"
              />
            </el-form-item>
            <el-form-item :label="t('resource.skill.descLabel')" prop="description">
              <el-input
                v-model="manualForm.description"
                type="textarea"
                :rows="4"
                :placeholder="t('resource.skill.descPlaceholder')"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- Tab 2: 文件/文件夹导入 -->
        <el-tab-pane name="file">
          <template #label>
            <div class="tab-label">
              <el-icon><Files /></el-icon>
              <span>{{ t('resource.skill.tabFile') }}</span>
            </div>
          </template>

          <div class="file-import-section">
            <div class="action-bar">
              <el-upload
                ref="uploadRef"
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                :on-change="handleFileChange"
                accept=".md,.zip"
              >
                <el-button type="primary">
                  <el-icon class="el-icon--left"><Upload /></el-icon>
                  {{ t('resource.skill.clickUpload') }} (.md/.zip)
                </el-button>
              </el-upload>

              <el-button type="success" plain @click="triggerFolderSelect">
                <el-icon class="el-icon--left"><FolderOpened /></el-icon>
                {{ t('resource.skill.selectFolder') }}
              </el-button>
              <input
                ref="folderInputRef"
                type="file"
                webkitdirectory
                directory
                multiple
                hidden
                @change="handleFolderSelect"
              />
            </div>

            <!-- 预览区域 -->
            <div
              class="preview-container"
              v-if="pendingFiles.length > 0 || folderTreeData.length > 0"
            >
              <div class="preview-header">
                <span class="title">
                  <el-icon><View /></el-icon>
                  {{
                    isFolderMode
                      ? t('resource.skill.folderPreview')
                      : t('resource.skill.fileSelected')
                  }}
                </span>
                <el-button link type="danger" @click="clearFileSelection">
                  {{ t('resource.skill.clear') }}
                </el-button>
              </div>

              <div class="preview-body">
                <div v-if="!isFolderMode" class="file-item">
                  <el-icon><Document /></el-icon>
                  <span>{{ pendingFiles[0]?.name }}</span>
                </div>
                <el-tree
                  v-else
                  :data="folderTreeData"
                  :props="{ label: 'name', children: 'children' }"
                  default-expand-all
                  class="preview-tree"
                >
                  <template #default="{ data }">
                    <span class="custom-tree-node">
                      <el-icon>
                        <component :is="data.children ? 'Folder' : 'Document'" />
                      </el-icon>
                      <span>{{ data.name }}</span>
                    </span>
                  </template>
                </el-tree>
              </div>
            </div>

            <el-empty v-else :image-size="80" :description="t('resource.skill.selectHint')" />
          </div>
        </el-tab-pane>

        <!-- Tab 3: GitHub 导入 -->
        <el-tab-pane name="github">
          <template #label>
            <div class="tab-label">
              <el-icon><Link /></el-icon>
              <span>{{ t('resource.skill.tabGithub') }}</span>
            </div>
          </template>

          <div class="github-section">
            <el-alert
              :title="t('resource.skill.importFromRepo')"
              type="info"
              show-icon
              :closable="false"
            />
            <el-form :model="githubForm" label-position="top" style="margin-top: 20px">
              <el-form-item :label="t('resource.skill.githubUrl')">
                <el-input
                  v-model="githubForm.url"
                  :placeholder="t('resource.skill.repoPlaceholder')"
                >
                  <template #prefix
                    ><el-icon><Link /></el-icon
                  ></template>
                </el-input>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('update:visible', false)">
          {{ t('common.action.cancel') }}
        </el-button>
        <el-button type="primary" :loading="isSubmitting" @click="handleConfirm">
          {{ t('common.action.confirm') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance } from 'element-plus'
import {
  Edit,
  Files,
  Link,
  Upload,
  FolderOpened,
  View,
  Document,
  Folder,
} from '@element-plus/icons-vue'
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
const manualFormRef = ref<FormInstance>()
const folderInputRef = ref<HTMLInputElement>()
const uploadRef = ref()

const manualForm = reactive({ name: '', description: '' })
const githubForm = reactive({ url: '' })

const isFolderMode = ref(false)
const folderTreeData = ref<any[]>([])
const pendingFiles = ref<File[]>([])

// --- Validation Rules ---
const manualRules = {
  name: [
    { required: true, message: t('resource.skill.nameRequired'), trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_-]+$/, message: t('resource.skill.nameRequired'), trigger: 'blur' },
  ],
  description: [{ required: true, message: t('resource.skill.descRequired'), trigger: 'blur' }],
}

// --- Handlers ---
const resetState = () => {
  manualForm.name = ''
  manualForm.description = ''
  githubForm.url = ''
  pendingFiles.value = []
  folderTreeData.value = []
  isFolderMode.value = false
  activeTab.value = 'create'
}

const clearFileSelection = () => {
  pendingFiles.value = []
  folderTreeData.value = []
  isFolderMode.value = false
}

const handleFileChange = (file: any) => {
  if (file.status === 'ready') {
    isFolderMode.value = false
    pendingFiles.value = [file.raw]
  }
}

const triggerFolderSelect = () => {
  folderInputRef.value?.click()
}

const handleFolderSelect = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return

  isFolderMode.value = true
  const files = Array.from(input.files)

  // 1. 构建预览树结构
  const rootFolderName = files[0].webkitRelativePath.split('/')[0]

  // 修复：显式断言 children 为 any[]，避免被推断为 never[]
  const rootNode = { name: rootFolderName, children: [] as any[] }

  files.forEach((file) => {
    const pathParts = file.webkitRelativePath.split('/').slice(1) // 去掉根目录名
    let currentLevel = rootNode.children

    pathParts.forEach((part, index) => {
      let existingNode: any = currentLevel.find((n: any) => n.name === part)
      if (!existingNode) {
        existingNode = { name: part }
        if (index < pathParts.length - 1) {
          existingNode.children = []
        }
        currentLevel.push(existingNode)
      }
      // 安全访问 children，防止 undefined
      currentLevel = existingNode.children || []
    })
  })
  folderTreeData.value = [rootNode]

  // 2. 打包 ZIP 用于上传
  const zip = new JSZip()
  files.forEach((file) => {
    zip.file(file.webkitRelativePath, file)
  })
  const blob = await zip.generateAsync({ type: 'blob' })
  pendingFiles.value = [new File([blob], `${rootFolderName}.zip`, { type: 'application/zip' })]
}

const handleConfirm = async () => {
  if (activeTab.value === 'create') {
    await manualFormRef.value?.validate((valid) => {
      if (valid) {
        emit('confirm', { ...manualForm })
      }
    })
  } else if (activeTab.value === 'file') {
    if (pendingFiles.value.length === 0) {
      return ElMessage.warning(t('resource.skill.selectFileFirst'))
    }
    await performFileImport()
  } else {
    if (!githubForm.url) {
      return ElMessage.warning(t('resource.skill.urlRequired'))
    }
    await performGithubImport()
  }
}

const performFileImport = async () => {
  isSubmitting.value = true
  try {
    const res = await importSkillFromFile(pendingFiles.value[0], props.parentId)
    handleImportResponse(res)
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || t('common.error.general'))
  } finally {
    isSubmitting.value = false
  }
}

const performGithubImport = async () => {
  isSubmitting.value = true
  try {
    const res = await importSkillFromGithub(githubForm.url, props.parentId)
    handleImportResponse(res)
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || t('common.error.general'))
  } finally {
    isSubmitting.value = false
  }
}

const handleImportResponse = (res: SkillImportResponse) => {
  if (res.success_count > 0) {
    ElMessage.success(t('resource.skill.importSuccess', { count: res.success_count }))
    emit('import-success', res)
  } else {
    ElMessage.error(res.details[0]?.error || t('resource.skill.importFailed'))
  }
}
</script>

<style scoped>
.dialog-content {
  margin-top: -10px;
}

.skill-tabs {
  border: none;
  box-shadow: none;
  border-radius: 8px;
  overflow: hidden;
}

:deep(.el-tabs--border-card) {
  background: transparent;
  border: 1px solid var(--el-border-color-lighter);
}

:deep(.el-tabs__content) {
  padding: 20px;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* File Import Section */
.file-import-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.action-bar {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 30px;
  border: 2px dashed var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  transition: border-color 0.3s;
}

.action-bar:hover {
  border-color: var(--el-color-primary-light-3);
}

.preview-container {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}

.preview-header {
  padding: 10px 16px;
  background: var(--el-fill-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.preview-header .title {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-primary);
}

.preview-body {
  max-height: 240px;
  overflow-y: auto;
  padding: 12px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-color-primary);
  font-size: 14px;
}

.preview-tree {
  background: transparent;
}

.custom-tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

/* Github Section */
.github-section {
  padding: 10px 0;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
