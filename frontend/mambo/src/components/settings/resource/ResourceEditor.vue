<!-- frontend/mambo/src/components/settings/resource/ResourceEditor.vue -->
<template>
  <div class="editor-container">
    <!-- Top Region: Version History (Horizontal) -->
    <ResourceVersionBar
      v-if="resource.itemType === 'resource'"
      :versions="resource.versions || []"
      :active-version-id="resource.latest_version?.id || null"
      :viewing-version-id="loadedVersionInEditor?.id || null"
      @select-version="loadVersionIntoEditor"
      @set-active="handleSetActiveVersion"
    />

    <!-- Bottom Region: Split View (Content Left, Meta Right) -->
    <el-form :model="form" label-position="top" ref="formRef" class="editor-split-layout">

      <!-- Left: Content Editor -->
      <div class="content-column">
        <template v-if="resource.itemType === 'resource'">
          <div class="content-header">
            <span class="content-label">{{ contentEditorLabel }}</span>
          </div>
          <el-form-item prop="content" class="content-form-item">
            <el-input
              v-model="form.content"
              type="textarea"
              placeholder="在此处输入 Prompt 或模板内容..."
              class="content-textarea"
            />
          </el-form-item>
        </template>
        <div v-else class="folder-placeholder">
          <el-empty description="文件夹无需编辑内容" :image-size="100" />
        </div>

        <!-- Footer Actions (Attached to content area) -->
        <div class="editor-footer">
          <el-button @click="resetForm">重置</el-button>
          <el-button v-if="resource.itemType === 'resource'" type="success" @click="openNewVersionDialog">另存为新版本</el-button>
          <el-button type="primary" @click="handleSaveChanges" :disabled="!isFormDirty">保存更改</el-button>
        </div>
      </div>

      <!-- Right: Meta Sidebar -->
      <ResourceMetaSidebar
        :resource="resource"
        v-model:name="form.name"
        v-model:description="form.description"
        v-model:attributes="form.attributes"
      />

    </el-form>
  </div>

  <el-dialog v-model="newVersionDialog.visible" title="另存为新版本" width="500px">
    <el-form :model="newVersionDialog.form" label-position="top" ref="newVersionFormRef">
      <el-form-item label="版本名称" prop="name" :rules="{ required: true, message: '版本名称不能为空', trigger: 'blur' }">
        <el-input v-model="newVersionDialog.form.name" placeholder="例如：v1.1 优化了逻辑" />
      </el-form-item>
      <el-form-item label="提交信息 (可选)" prop="commitMessage">
        <el-input v-model="newVersionDialog.form.commitMessage" type="textarea" placeholder="描述本次变更的内容" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newVersionDialog.visible = false">取消</el-button>
      <el-button type="primary" @click="handleConfirmNewVersion">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus';

import { useResourceStore } from '@/stores/resourceStore';
import type { ResourceWithVersions, ResourceVersion, ResourceVersionCreate } from '@/api/types';
import ResourceVersionBar from './ResourceVersionBar.vue';
import ResourceMetaSidebar from './ResourceMetaSidebar.vue';

// --- Local Type Definitions ---
interface SubMessageTemplateAttributes {
  context_participation_length: number;
  is_collapsed: boolean;
  is_minimal: boolean;
}

// --- Props ---
const props = defineProps<{
  resource: ResourceWithVersions;
}>();

// --- Store ---
const resourceStore = useResourceStore();

// --- Constants ---
const DEFAULT_SUBMESSAGE_ATTRIBUTES: SubMessageTemplateAttributes = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: false,
};

// --- State ---
const formRef = ref<FormInstance>();
const newVersionFormRef = ref<FormInstance>();
const loadedVersionInEditor = ref<ResourceVersion | null>(null);

const form = reactive({
  name: '',
  description: '',
  content: '',
  attributes: { ...DEFAULT_SUBMESSAGE_ATTRIBUTES },
});

const newVersionDialog = reactive({
  visible: false,
  form: {
    name: '',
    commitMessage: '',
  },
});

// --- Computed Properties ---
const isFormDirty = computed(() => {
  const original = props.resource;
  if (!original) return false;

  const originalVersion = loadedVersionInEditor.value ?? original.latest_version;
  const isMetaDirty = form.name !== original.name || form.description !== (original.description || '');

  if (original.itemType === 'resource') {
    const isContentDirty = form.content !== (originalVersion?.content || '');
    let isAttributesDirty = false;
    if (original.resourceType === 'submessage_template') {
      const originalAttributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES, ...(originalVersion?.attributes as Partial<SubMessageTemplateAttributes> || {}) };
      isAttributesDirty = JSON.stringify(form.attributes) !== JSON.stringify(originalAttributes);
    }
    return isMetaDirty || isContentDirty || isAttributesDirty;
  }

  return isMetaDirty;
});

const contentEditorLabel = computed(() => {
  if (loadedVersionInEditor.value) {
    return `内容 (正在查看: ${loadedVersionInEditor.value.name})`;
  }
  return '内容 (当前版本)';
});

// --- Watchers ---
watch(() => props.resource, (newSelection) => {
  if (newSelection) {
    form.name = newSelection.name;
    form.description = newSelection.description || '';
    form.content = newSelection.latest_version?.content || '';

    if (newSelection.resourceType === 'submessage_template') {
      form.attributes = {
        ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
        ...(newSelection.latest_version?.attributes as Partial<SubMessageTemplateAttributes> || {}),
      };
    } else {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
    }
    loadedVersionInEditor.value = null;
  } else {
    // Reset form when resource becomes null (handled by parent)
    form.name = '';
    form.description = '';
    form.content = '';
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
  }
}, { immediate: true });


// --- Handlers ---
function resetForm() {
  const selection = props.resource;
  if (selection) {
    form.name = selection.name;
    form.description = selection.description || '';
    form.content = selection.latest_version?.content || '';

    if (selection.resourceType === 'submessage_template') {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES, ...(selection.latest_version?.attributes as Partial<SubMessageTemplateAttributes> || {}) };
    } else {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
    }
    loadedVersionInEditor.value = null;
  }
}

async function handleSaveChanges() {
  if (!props.resource || !isFormDirty.value) return;
  const resource = props.resource;

  if (form.name !== resource.name || form.description !== (resource.description || '')) {
    await resourceStore.updateResourceItem(resource.id, {
      name: form.name,
      description: form.description,
    });
  }

  if (resource.itemType === 'resource') {
    await resourceStore.updateActiveVersionDetails(resource.id, {
      content: form.content,
      attributes: form.attributes,
    });
  }

  ElMessage.success('保存成功');
  loadedVersionInEditor.value = null;
}

function loadVersionIntoEditor(version: ResourceVersion) {
  form.content = version.content || '';
  if (props.resource?.resourceType === 'submessage_template') {
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES, ...(version.attributes as Partial<SubMessageTemplateAttributes> || {}) };
  } else {
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES };
  }
  loadedVersionInEditor.value = version;
}

async function handleSetActiveVersion(versionId: string) {
  if (!props.resource) return;
  try {
    await ElMessageBox.confirm('确定要将此版本设为当前活跃版本吗？', '确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'info'
    });
    await resourceStore.setActiveResourceVersion(props.resource.id, versionId);
    ElMessage.success('活跃版本已切换');
  } catch { /* User canceled */ }
}

function openNewVersionDialog() {
  if (!props.resource) return;
  newVersionDialog.form.name = `v${props.resource.versions.length + 1}`;
  newVersionDialog.form.commitMessage = '';
  newVersionDialog.visible = true;
}

async function handleConfirmNewVersion() {
  if (!newVersionFormRef.value || !props.resource) return;
  await newVersionFormRef.value.validate(async (valid) => {
    if (valid) {
      const versionData: ResourceVersionCreate = {
        ...newVersionDialog.form,
        content: form.content,
        attributes: form.attributes,
      };
      await resourceStore.createNewVersion(props.resource!.id, versionData);
      newVersionDialog.visible = false;
      ElMessage.success('新版本创建成功');
    }
  });
}
</script>

<style scoped>
.editor-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

/* --- Split Layout --- */
.editor-split-layout {
  flex-grow: 1;
  display: flex;
  min-height: 0; /* Important for flex child scrolling */
}

/* Left: Content Column */
.content-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 0;
  position: relative;
}

.content-header {
  padding: 12px 20px 0 20px;
  flex-shrink: 0;
}

.content-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.content-form-item {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  margin-bottom: 0 !important;
  padding: 10px 20px 0 20px;
}

:deep(.content-form-item .el-form-item__content) {
  flex-grow: 1;
  height: 100%;
}

:deep(.content-textarea) {
  height: 100%;
}

:deep(.content-textarea .el-textarea__inner) {
  height: 100% !important;
  resize: none;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  line-height: 1.6;
  padding: 12px;
  border-radius: 4px;
}

.folder-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.editor-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 16px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background-color: #fff;
}
</style>
