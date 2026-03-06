<!-- frontend/mambo/src/components/settings/skill/SkillOverview.vue -->
<template>
  <div class="skill-overview-container">
    <div class="skill-header">
      <div class="title-area">
        <h3>{{ resource.name }}</h3>
        <el-tag v-if="validationResult" :type="validationResult.is_valid ? 'success' : 'danger'" size="small">
          {{ validationResult.is_valid ? t('resource.skill.valid') : t('resource.skill.invalid') }}
        </el-tag>
      </div>
      <div class="actions">
        <el-button type="primary" @click="handleEditSkillMd" :disabled="!skillMdFile">
          {{ t('resource.skill.editFile') }}
        </el-button>
        <el-button @click="runValidation" :loading="isValidating">
          {{ t('resource.skill.validate') }}
        </el-button>
      </div>
    </div>

    <el-divider />

    <!-- Validation Errors -->
    <div v-if="validationResult && validationResult.errors.length > 0" class="validation-section error">
      <h4>{{ t('resource.skill.errors') }}</h4>
      <ul>
        <li v-for="(err, idx) in validationResult.errors" :key="idx">{{ err }}</li>
      </ul>
    </div>

    <!-- Content Area -->
    <div class="skill-content-layout">
      <!-- Left: File Structure -->
      <div class="file-structure-panel">
        <div class="panel-title">{{ t('resource.skill.structure') }}</div>
        <el-tree
          v-if="children.length > 0"
          :data="children"
          :props="{ label: 'name', children: 'children' }"
          default-expand-all
          highlight-current
          @node-click="handleFileClick"
        >
          <template #default="{ data }">
            <span class="custom-tree-node">
              <el-icon><Document /></el-icon>
              <span>{{ data.name }}</span>
            </span>
          </template>
        </el-tree>
        <el-empty v-else :description="t('common.status.loading')" :image-size="60" />
      </div>

      <!-- Right: SKILL.md Preview -->
      <div class="preview-panel">
        <div class="panel-title">{{ t('resource.skill.preview') }}</div>
        <div v-if="skillMdContent" class="markdown-body" v-html="renderedMarkdown"></div>
        <el-empty v-else :description="t('resource.skill.noContent')" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Document } from '@element-plus/icons-vue'
import { useResourceStore } from '@/stores/resourceStore'
import { getResourceChildren } from '@/api/resourceService'
import { getFileContent } from '@/api/fileService'
import type { Resource, SkillValidationResult } from '@/api/types'
import { md } from '@/utils/markdownParser'

const props = defineProps<{
  resource: Resource
}>()

// 修改 emit 定义，增加 viewMode 参数
const emit = defineEmits<{
  (e: 'edit-file', file: Resource, viewMode: 'editor'): void
}>()

const { t } = useI18n()
const resourceStore = useResourceStore()

const children = ref<Resource[]>([])
const skillMdFile = ref<Resource | null>(null)
const skillMdContent = ref<string>('')
const isValidating = ref(false)
const validationResult = ref<SkillValidationResult | null>(null)

const renderedMarkdown = computed(() => {
  return skillMdContent.value ? md.render(skillMdContent.value) : ''
})

// Load children and find SKILL.md
const loadSkillData = async () => {
  try {
    const res = await getResourceChildren([props.resource.id])
    children.value = res

    const mdFile = res.find(r => r.name === 'SKILL.md' && r.resourceType === 'file')
    if (mdFile) {
      skillMdFile.value = mdFile

      // 修复：确保获取完整的文件信息
      let targetFile = mdFile
      // 如果列表接口返回的数据不包含 file_info，则请求详情
      if (!mdFile.latest_version?.file_info) {
        await resourceStore.fetchResourceDetails(mdFile.id)
        // 从 store 中获取更新后的数据
        const updatedResource = resourceStore.resources.find(r => r.id === mdFile.id)
        if (updatedResource) {
          targetFile = updatedResource
          skillMdFile.value = updatedResource // 更新本地引用
        }
      }

      // 获取文件内容
      if (targetFile.latest_version?.file_info) {
         const contentRes = await getFileContent(targetFile.latest_version.file_info.id)
         skillMdContent.value = contentRes.content
      }
    }
  } catch (error) {
    console.error('Failed to load skill data', error)
  }
}

const runValidation = async () => {
  isValidating.value = true
  try {
    validationResult.value = await resourceStore.checkSkillValidation(props.resource.id)
  } catch (error) {
    // handled in store
  } finally {
    isValidating.value = false
  }
}

const handleEditSkillMd = () => {
  if (skillMdFile.value) {
    // 修改：传递 'editor' 模式
    emit('edit-file', skillMdFile.value, 'editor')
  }
}

const handleFileClick = (data: Resource) => {
  if (data.itemType === 'resource') {
    // 修改：传递 'editor' 模式
    emit('edit-file', data, 'editor')
  }
}

onMounted(() => {
  loadSkillData()
  runValidation() // Auto validate on open
})

watch(() => props.resource.id, () => {
  loadSkillData()
  runValidation()
})
</script>

<style scoped>
.skill-overview-container {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.skill-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title-area {
  display: flex;
  align-items: center;
  gap: 12px;
}
.skill-content-layout {
  display: flex;
  flex: 1;
  gap: 20px;
  min-height: 0;
}
.file-structure-panel {
  flex: 2;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  padding: 10px;
  overflow: auto;
}
.preview-panel {
  flex: 8;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  padding: 10px;
  overflow: auto;
}
.panel-title {
  font-weight: bold;
  margin-bottom: 10px;
  color: var(--el-text-color-secondary);
}
.validation-section.error {
  background-color: var(--el-color-danger-light-9);
  padding: 10px;
  border-radius: 4px;
  margin-bottom: 12px;
  color: var(--el-color-danger);
}

/* GitHub 风格 Frontmatter 表格 */
:deep(.frontmatter-table) {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 16px;
  font-size: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
}

:deep(.frontmatter-table th),
:deep(.frontmatter-table td) {
  border: 1px solid var(--el-border-color-light);
  padding: 8px 12px;
  text-align: left;
  vertical-align: top;
}

:deep(.frontmatter-table th) {
  background-color: var(--el-fill-color-light);
  font-weight: 600;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

:deep(.frontmatter-table td:first-child) {
  white-space: nowrap;
  width: 1%;
  color: var(--el-text-color-primary);
}

:deep(.frontmatter-table td:last-child) {
  word-break: break-word;
  color: var(--el-text-color-regular);
}
</style>
