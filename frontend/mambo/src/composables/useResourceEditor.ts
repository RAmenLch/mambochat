// frontend/mambo/src/composables/useResourceEditor.ts
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useResourceStore } from '@/stores/resourceStore'
import { uploadResourceFile } from '@/api/kbService'
import type { ResourceWithVersions, ResourceVersion, ResourceVersionCreate, VersionReorderItem } from '@/api/types'

interface SubMessageTemplateAttributes {
  context_participation_length: number
  is_collapsed: boolean
  is_minimal: boolean
}

const DEFAULT_SUBMESSAGE_ATTRIBUTES: SubMessageTemplateAttributes = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: false,
}

export function useResourceEditor(props: {
  resource: ResourceWithVersions
  initialViewMode?: 'editor' | 'kb_config'
}) {
  const { t } = useI18n()
  const resourceStore = useResourceStore()

  // --- State ---
  const loadedVersionInEditor = ref<ResourceVersion | null>(null)
  const viewMode = ref<'editor' | 'kb_config'>('editor')
  const isUploading = ref(false)
  const editableFileContent = ref('')
  const isFileContentLoading = ref(false) // 新增：文件内容加载状态

  const form = reactive({
    name: '',
    description: '',
    content: '',
    attributes: { ...DEFAULT_SUBMESSAGE_ATTRIBUTES },
    versionName: '',
    versionCommitMessage: '',
  })

  const newVersionDialog = reactive({
    visible: false,
    form: {
      name: '',
      commitMessage: '',
    },
  })

  // --- Computed ---
  const currentVersion = computed(() => {
    return loadedVersionInEditor.value ?? props.resource.latest_version
  })

  const currentFileInfo = computed(() => {
    return currentVersion.value?.file_info ?? null
  })

  const isEditableFile = computed(() => {
    return currentFileInfo.value?.editable ?? false
  })

  const isFormDirty = computed(() => {
    const original = props.resource
    if (!original) return false

    const originalVersion = currentVersion.value
    const isMetaDirty =
      form.name !== original.name || form.description !== (original.description || '')

    if (original.itemType === 'resource' && originalVersion) {
      if (original.resourceType === 'file' && isEditableFile.value) {
        const isContentDirty = editableFileContent.value !== (originalVersion.content || '')
        return isMetaDirty || isContentDirty
      }

      if (original.resourceType === 'file') return isMetaDirty

      const isVersionMetaDirty =
        form.versionName !== originalVersion.name ||
        form.versionCommitMessage !== (originalVersion.commitMessage || '')
      const isContentDirty = form.content !== (originalVersion?.content || '')
      let isAttributesDirty = false
      if (original.resourceType === 'submessage_template') {
        const originalAttributes = {
          ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
          ...((originalVersion?.attributes as Partial<SubMessageTemplateAttributes>) || {}),
        }
        isAttributesDirty = JSON.stringify(form.attributes) !== JSON.stringify(originalAttributes)
      }
      return isMetaDirty || isVersionMetaDirty || isContentDirty || isAttributesDirty
    }

    return isMetaDirty
  })

  // --- Methods ---

  // 新增：拉取真实文件内容
  async function loadFileContent() {
    if (!props.resource || !currentVersion.value) return

    isFileContentLoading.value = true
    try {
      await resourceStore.fetchFileContent(props.resource.id, currentVersion.value.id)
      editableFileContent.value = currentVersion.value.content || ''
    } catch (error) {
      console.error('Failed to load file content:', error)
      ElMessage.error(t('resource.editor.loadContentError'))
    } finally {
      isFileContentLoading.value = false
    }
  }

  function resetForm() {
    const selection = props.resource
    if (selection) {
      const versionToLoad = selection.latest_version
      form.name = selection.name
      form.description = selection.description || ''
      form.content = versionToLoad?.content || ''
      form.versionName = versionToLoad?.name || ''
      form.versionCommitMessage = versionToLoad?.commitMessage || ''

      if (selection.resourceType === 'submessage_template') {
        form.attributes = {
          ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
          ...((versionToLoad?.attributes as Partial<SubMessageTemplateAttributes>) || {}),
        }
      } else {
        form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES }
      }
      loadedVersionInEditor.value = null

      if (isEditableFile.value && versionToLoad) {
        editableFileContent.value = versionToLoad.content || ''
      } else {
        editableFileContent.value = ''
      }
    }
  }

  async function handleSaveChanges() {
    if (!props.resource || !isFormDirty.value) return
    const resource = props.resource

    if (form.name !== resource.name || form.description !== (resource.description || '')) {
      await resourceStore.updateResourceItem(resource.id, {
        name: form.name,
        description: form.description,
      })
    }

    if (resource.itemType === 'resource') {
      if (resource.resourceType === 'file' && isEditableFile.value && currentVersion.value) {
        if (editableFileContent.value !== currentVersion.value.content) {
          await resourceStore.saveFileContent(
            resource.id,
            currentVersion.value.id,
            editableFileContent.value
          )
        }
      } else if (resource.resourceType !== 'file') {
        const targetVersionId = loadedVersionInEditor.value?.id ?? resource.latest_version?.id

        if (targetVersionId) {
          const payload = {
            name: form.versionName,
            commitMessage: form.versionCommitMessage,
            content: form.content,
            attributes: form.attributes,
          }
          await resourceStore.updateResourceVersionItem(resource.id, targetVersionId, payload)

          if (loadedVersionInEditor.value) {
            const updatedVersion = resource.versions.find((v) => v.id === targetVersionId)
            if (updatedVersion) {
              loadedVersionInEditor.value = { ...updatedVersion, ...payload }
            }
          }
        }
      }
    }

    ElMessage.success(t('resource.editor.saveSuccess'))
  }

  async function handleFileChange(uploadFile: any) {
    if (!uploadFile.raw || !props.resource) return

    isUploading.value = true
    try {
      await uploadResourceFile(uploadFile.raw, undefined, props.resource.id)
      ElMessage.success(t('resource.editor.uploadSuccess'))
      await resourceStore.fetchResourceDetails(props.resource.id)
    } catch (error) {
      console.error(error)
      ElMessage.error(t('resource.editor.uploadError'))
    } finally {
      isUploading.value = false
    }
  }

  function loadVersionIntoEditor(version: ResourceVersion) {
    form.content = version.content || ''
    form.versionName = version.name
    form.versionCommitMessage = version.commitMessage || ''

    if (props.resource?.resourceType === 'submessage_template') {
      form.attributes = {
        ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
        ...((version.attributes as Partial<SubMessageTemplateAttributes>) || {}),
      }
    } else {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES }
    }
    loadedVersionInEditor.value = version

    if (version.file_info?.editable) {
      loadFileContent() // 切换版本时加载文件内容
    }

    if (viewMode.value !== 'editor') {
      viewMode.value = 'editor'
    }
  }

  async function handleSetActiveVersion(versionId: string) {
    if (!props.resource) return
    try {
      await ElMessageBox.confirm(
        t('resource.version.confirmActive'),
        t('resource.tree.moveWarningTitle'),
        {
          confirmButtonText: t('common.action.confirm'),
          cancelButtonText: t('common.action.cancel'),
          type: 'info',
        }
      )
      await resourceStore.setActiveResourceVersion(props.resource.id, versionId)
      ElMessage.success(t('resource.version.switchSuccess'))
    } catch {
      /* User canceled */
    }
  }

  function openNewVersionDialog() {
    if (!props.resource) return
    newVersionDialog.form.name = `v${props.resource.versions.length + 1}`
    newVersionDialog.form.commitMessage = ''
    newVersionDialog.visible = true
  }

  async function handleConfirmNewVersion() {
    if (isEditableFile.value && currentFileInfo.value) {
      try {
        const blob = new Blob([editableFileContent.value], { type: currentFileInfo.value.mime_type })
        const file = new File([blob], currentFileInfo.value.filename, { type: currentFileInfo.value.mime_type })

        await uploadResourceFile(file, undefined, props.resource!.id)
        ElMessage.success(t('resource.editor.uploadSuccess'))
        newVersionDialog.visible = false
        await resourceStore.fetchResourceDetails(props.resource!.id)
      } catch (error) {
        console.error(error)
        ElMessage.error(t('resource.editor.uploadError'))
      }
    } else {
      const versionData: ResourceVersionCreate = {
        ...newVersionDialog.form,
        content: form.content,
        attributes: form.attributes,
      }
      await resourceStore.createNewVersion(props.resource!.id, versionData)
      newVersionDialog.visible = false
      ElMessage.success(t('resource.editor.uploadSuccess'))
    }
  }

  async function handleReorderVersions(reorderedVersions: ResourceVersion[]) {
    if (!props.resource) return
    const updates: VersionReorderItem[] = reorderedVersions.map((v, index) => ({
      id: v.id,
      sortOrder: index,
    }))
    await resourceStore.reorderVersions(props.resource.id, updates)
  }

  async function handleDeleteVersion(versionId: string) {
    if (!props.resource) return

    const version = props.resource.versions.find(v => v.id === versionId)
    if (!version) return

    try {
      await ElMessageBox.confirm(
        t('resource.version.confirmDelete', { name: version.name }),
        t('resource.version.delete'),
        {
          type: 'warning',
          confirmButtonText: t('common.action.confirm'),
          cancelButtonText: t('common.action.cancel'),
        }
      )
      await resourceStore.deleteVersion(props.resource.id, versionId)
      ElMessage.success(t('resource.version.deleteSuccess'))
    } catch {
      /* User canceled */
    }
  }

  // --- Watchers ---
  watch(
    () => props.resource,
    (newSelection, oldSelection) => {
      if (newSelection) {
        if (newSelection.id !== oldSelection?.id) {
          resetForm()
          viewMode.value = props.initialViewMode === 'kb_config' ? 'kb_config' : 'editor'
        } else {
          if (newSelection.kb_id !== oldSelection?.kb_id) {
            viewMode.value = 'editor'
          }
          if (!loadedVersionInEditor.value) {
            resetForm()
          }
        }

        // 资源切换时，如果是可编辑文件则加载内容
        if (isEditableFile.value && currentVersion.value) {
          loadFileContent()
        }
      } else {
        resetForm()
      }
    },
    { immediate: true }
  )

  // 监听当前版本变化（例如设置了新活跃版本）
  watch(currentVersion, (newVersion) => {
    if (newVersion && isEditableFile.value) {
      loadFileContent()
    }
  })

  return {
    form,
    viewMode,
    loadedVersionInEditor,
    currentVersion,
    currentFileInfo,
    isEditableFile,
    isFormDirty,
    isUploading,
    editableFileContent,
    isFileContentLoading,
    newVersionDialog,
    resetForm,
    handleSaveChanges,
    handleFileChange,
    loadVersionIntoEditor,
    handleSetActiveVersion,
    handleReorderVersions,
    handleDeleteVersion,
    openNewVersionDialog,
    handleConfirmNewVersion,
  }
}
