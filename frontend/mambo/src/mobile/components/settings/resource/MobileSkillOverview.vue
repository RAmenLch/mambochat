<!-- frontend/mambo/src/mobile/components/settings/resource/MobileSkillOverview.vue -->
<template>
  <div class="mobile-skill-overview">
    <div class="skill-header">
      <div class="title-row">
        <span class="title">{{ resource.name }}</span>
        <el-tag v-if="validationResult" :type="validationResult.is_valid ? 'success' : 'danger'" size="small">
          {{ validationResult.is_valid ? t('resource.skill.valid') : t('resource.skill.invalid') }}
        </el-tag>
      </div>
      <div class="action-row">
        <el-button type="primary" size="small" @click="handleEditSkillMd" :disabled="!skillMdFile">
          {{ t('resource.skill.editFile') }}
        </el-button>
        <el-button size="small" @click="runValidation" :loading="isValidating">
          {{ t('resource.skill.validate') }}
        </el-button>
      </div>
    </div>

    <div v-if="validationResult && validationResult.errors.length > 0" class="validation-error-box">
      <div class="error-title">{{ t('resource.skill.errors') }}</div>
      <ul>
        <li v-for="(err, idx) in validationResult.errors" :key="idx">{{ err }}</li>
      </ul>
    </div>

    <!-- 移动端使用 Tabs 节省空间 -->
    <el-tabs v-model="activeTab" class="mobile-skill-tabs">
      <el-tab-pane :label="t('resource.skill.preview')" name="preview">
        <el-scrollbar class="tab-scroll-area">
          <div v-if="skillMdContent" class="markdown-body" v-html="renderedMarkdown"></div>
          <el-empty v-else :description="t('resource.skill.noContent')" :image-size="80" />
        </el-scrollbar>
      </el-tab-pane>

      <el-tab-pane :label="t('resource.skill.structure')" name="structure">
        <el-scrollbar class="tab-scroll-area">
          <el-tree
            v-if="children.length > 0"
            :data="children"
            :props="{ label: 'name', children: 'children' }"
            default-expand-all
            @node-click="handleFileClick"
          >
            <template #default="{ data }">
              <span class="custom-tree-node">
                <el-icon><Document /></el-icon>
                <span>{{ data.name }}</span>
              </span>
            </template>
          </el-tree>
          <el-empty v-else :description="t('common.status.loading')" :image-size="80" />
        </el-scrollbar>
      </el-tab-pane>
    </el-tabs>
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

const props = defineProps<{ resource: Resource }>()
const emit = defineEmits<{ (e: 'edit-file', file: Resource, viewMode: 'editor'): void }>()

const { t } = useI18n()
const resourceStore = useResourceStore()

const activeTab = ref('preview')
const children = ref<Resource[]>([])
const skillMdFile = ref<Resource | null>(null)
const skillMdContent = ref<string>('')
const isValidating = ref(false)
const validationResult = ref<SkillValidationResult | null>(null)

const renderedMarkdown = computed(() => skillMdContent.value ? md.render(skillMdContent.value) : '')

const loadSkillData = async () => {
  try {
    const res = await getResourceChildren([props.resource.id])
    children.value = res
    const mdFile = res.find(r => r.name === 'SKILL.md' && r.resourceType === 'file')
    if (mdFile) {
      skillMdFile.value = mdFile
      let targetFile = mdFile
      if (!mdFile.latest_version?.file_info) {
        await resourceStore.fetchResourceDetails(mdFile.id)
        targetFile = resourceStore.resources.find(r => r.id === mdFile.id) || mdFile
        skillMdFile.value = targetFile
      }
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
  } finally {
    isValidating.value = false
  }
}

const handleEditSkillMd = () => {
  if (skillMdFile.value) emit('edit-file', skillMdFile.value, 'editor')
}

const handleFileClick = (data: Resource) => {
  if (data.itemType === 'resource') emit('edit-file', data, 'editor')
}

onMounted(() => { loadSkillData(); runValidation(); })
watch(() => props.resource.id, () => { loadSkillData(); runValidation(); })
</script>

<style scoped>
.mobile-skill-overview {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-background);
}
.skill-header {
  padding: 12px 16px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
}
.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.title {
  font-size: 16px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}
.action-row {
  display: flex;
  gap: 10px;
}
.validation-error-box {
  margin: 10px 16px;
  padding: 10px;
  background-color: var(--el-color-danger-light-9);
  border-radius: 6px;
  color: var(--el-color-danger);
  font-size: 13px;
}
.error-title { font-weight: bold; margin-bottom: 4px; }
.mobile-skill-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
:deep(.el-tabs__header) { margin-bottom: 0; padding: 0 16px; background: #fff;}
:deep(.el-tabs__content) { flex: 1; overflow: hidden; position: relative; }
.tab-scroll-area { height: 100%; padding: 12px 16px; box-sizing: border-box; }
.custom-tree-node { display: flex; align-items: center; gap: 6px; font-size: 14px; }
</style>
