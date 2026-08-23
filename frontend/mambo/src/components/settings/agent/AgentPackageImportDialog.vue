<!-- Agent 导出包导入对话框：文件选择 → 预检预览 → 导入结果（含失败清理重试） -->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('agentPackage.importDialog.title')"
    width="720px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="reset"
  >
    <el-steps :active="activeStep" align-center finish-status="success" style="margin-bottom: 20px">
      <el-step :title="t('agentPackage.importDialog.stepFile')" />
      <el-step :title="t('agentPackage.importDialog.stepPreview')" />
      <el-step :title="t('agentPackage.importDialog.stepResult')" />
    </el-steps>

    <!-- 步骤 1：选择文件与目标文件夹 -->
    <div v-if="activeStep === 1" class="step-body">
      <el-form label-width="110px">
        <el-form-item :label="t('agentPackage.importDialog.fileLabel')">
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".mamboagent"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            :file-list="fileList"
          >
            <el-button type="primary" plain>{{ t('agentPackage.importDialog.selectFile') }}</el-button>
            <template #tip>
              <div class="el-upload__tip">{{ t('agentPackage.importDialog.fileTip') }}</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item :label="t('agentPackage.importDialog.targetFolder')">
          <el-tree-select
            v-model="targetFolderId"
            :data="folderTree"
            :props="{ label: 'label', children: 'children' }"
            node-key="id"
            :placeholder="t('agentPackage.importDialog.targetFolderRoot')"
            clearable
            check-strictly
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- 步骤 2：预检预览 -->
    <div v-if="activeStep === 2 && previewData" class="step-body">
      <el-alert
        v-for="(w, i) in previewData.warnings"
        :key="i"
        :title="w"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      />
      <template v-if="previewData.rename_suggestions.length">
        <div class="section-title">{{ t('agentPackage.preview.renameTitle') }}</div>
        <el-table :data="previewData.rename_suggestions" size="small" max-height="180" style="margin-bottom: 12px">
          <el-table-column :label="t('agentPackage.preview.entity')" width="150">
            <template #default="{ row }">{{ t(`agentPackage.preview.entityTypes.${row.entity_type}`) }}</template>
          </el-table-column>
          <el-table-column :label="t('agentPackage.preview.originalName')" prop="original_name" show-overflow-tooltip />
          <el-table-column :label="t('agentPackage.preview.newName')" prop="new_name" show-overflow-tooltip />
        </el-table>
      </template>
      <template v-if="previewData.providers_missing_api_key.length">
        <div class="section-title">{{ t('agentPackage.preview.providersTitle') }}</div>
        <div style="margin-bottom: 12px">
          <el-tag v-for="p in previewData.providers_missing_api_key" :key="p.source_id" size="small" style="margin-right: 6px">
            {{ p.name }}
          </el-tag>
        </div>
      </template>
      <div class="section-title">{{ t('agentPackage.preview.treeTitle') }}</div>
      <el-tree
        :data="previewData.resource_tree"
        :props="{ label: 'name', children: 'children' }"
        default-expand-all
        class="preview-tree"
      >
        <template #default="{ data }">
          <span class="tree-node">
            <el-icon v-if="data.itemType === 'folder'"><Folder /></el-icon>
            <el-icon v-else><Document /></el-icon>
            <span>{{ data.name }}</span>
          </span>
        </template>
      </el-tree>
    </div>

    <!-- 步骤 3：导入结果 -->
    <div v-if="activeStep === 3 && report" class="step-body">
      <el-result
        v-if="report.success"
        icon="success"
        :title="t('agentPackage.result.successTitle')"
        :sub-title="t('agentPackage.result.successSubtitle')"
      />
      <el-result v-else icon="error" :title="t('agentPackage.result.failedTitle')">
        <template #sub-title>
          <div class="error-box">
            <div>{{ t('agentPackage.result.phase') }}: {{ report.failed_phase || '-' }} / {{ report.failed_entity || '-' }}</div>
            <div>{{ report.error }}</div>
          </div>
        </template>
      </el-result>
      <template v-if="report.providers_missing_api_key.length">
        <div class="section-title">{{ t('agentPackage.result.providersTitle') }}</div>
        <div>
          <el-tag v-for="p in report.providers_missing_api_key" :key="p.source_id" size="small" style="margin-right: 6px">
            {{ p.name }}
          </el-tag>
        </div>
      </template>
      <template v-if="report.created.length">
        <div class="section-title">{{ t('agentPackage.result.createdTitle') }}</div>
        <el-table :data="report.created" size="small" max-height="220">
          <el-table-column :label="t('agentPackage.result.entity')" width="140">
            <template #default="{ row }">{{ t(`agentPackage.result.entityTypes.${row.entity_type}`) }}</template>
          </el-table-column>
          <el-table-column :label="t('agentPackage.result.newId')" prop="new_id" show-overflow-tooltip />
        </el-table>
      </template>
    </div>

    <template #footer>
      <div v-if="activeStep === 1">
        <el-button @click="emit('update:modelValue', false)">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :disabled="!selectedFile" :loading="previewLoading" @click="handlePreview">
          {{ t('agentPackage.importDialog.next') }}
        </el-button>
      </div>
      <div v-else-if="activeStep === 2">
        <el-button @click="activeStep = 1">{{ t('common.action.back') }}</el-button>
        <el-button type="primary" :loading="importing" @click="handleImport">
          {{ t('agentPackage.importDialog.startImport') }}
        </el-button>
      </div>
      <div v-else>
        <el-button v-if="!report?.success" type="danger" :loading="cleaning" @click="handleCleanRetry">
          {{ t('agentPackage.result.cleanRetry') }}
        </el-button>
        <el-button type="primary" @click="emit('update:modelValue', false)">
          {{ t('common.action.close') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import type { UploadFile, UploadUserFile } from 'element-plus';
import { Folder, Document } from '@element-plus/icons-vue';

import { useAgentStore } from '@/stores/agentStore';
import { useResourceStore } from '@/stores/resourceStore';
import { useBackendStore } from '@/stores/backendStore';
import { useProviderStore } from '@/stores/providerStore';
import { useMcpStore } from '@/stores/mcpStore';
import { importAgent, importAgentPreview, cleanupImportSession } from '@/api/agentPackageService';
import type { AgentPackageImportReport, AgentPackagePreview } from '@/api/types/agentPackageTypes';
import type { Agent } from '@/api/types';

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'imported', mainAgentId: string | null): void;
}>();

const { t } = useI18n();
const agentStore = useAgentStore();
const resourceStore = useResourceStore();
const backendStore = useBackendStore();
const providerStore = useProviderStore();
const mcpStore = useMcpStore();

const activeStep = ref(1);
const selectedFile = ref<File | null>(null);
const fileList = ref<UploadUserFile[]>([]);
const targetFolderId = ref<string | null>(null);
const previewData = ref<AgentPackagePreview | null>(null);
const report = ref<AgentPackageImportReport | null>(null);
const previewLoading = ref(false);
const importing = ref(false);
const cleaning = ref(false);

// 目标文件夹树（仅 folder 节点，agentList 懒加载可能不全，优先用 allAgents）
const folderTree = computed(() => {
  const source = agentStore.allAgents.length ? agentStore.allAgents : agentStore.agentList;
  const folders = source.filter((a) => a.itemType === 'folder');
  const byId = new Map<string, Agent & { children: any[] }>();
  folders.forEach((f) => byId.set(f.id, { ...f, children: [] as any[] }));
  const roots: Array<{ id: string; label: string; children: any[] }> = [];
  byId.forEach((f) => {
    const parent = f.parentId ? byId.get(f.parentId) : undefined;
    const node = { id: f.id, label: f.name, children: f.children };
    if (parent) parent.children.push(node);
    else roots.push(node);
  });
  return roots;
});

function handleFileChange(file: UploadFile) {
  if (file.raw) {
    selectedFile.value = file.raw;
  }
}

function handleFileRemove() {
  selectedFile.value = null;
}

async function handlePreview() {
  if (!selectedFile.value) return;
  previewLoading.value = true;
  try {
    previewData.value = await importAgentPreview(selectedFile.value, targetFolderId.value);
    activeStep.value = 2;
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    previewLoading.value = false;
  }
}

async function handleImport() {
  if (!selectedFile.value) return;
  importing.value = true;
  try {
    report.value = await importAgent(selectedFile.value, targetFolderId.value);
    activeStep.value = 3;
    if (report.value.success) {
      // 导入会创建 backend / provider / mcp / resource 等实体，
      // 需要一并刷新各 store 缓存，避免展示"未知 Backend"/UUID
      await Promise.all([
        agentStore.initializeList(),
        resourceStore.initializeList(),
        backendStore.fetchBackends(),
        providerStore.fetchProviders(),
        mcpStore.fetchAvailableServices(),
      ]);
      emit('imported', report.value.main_agent_id);
    }
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    importing.value = false;
  }
}

async function handleCleanRetry() {
  if (!report.value?.import_session_id) return;
  cleaning.value = true;
  try {
    await cleanupImportSession(report.value.import_session_id);
    ElMessage.success(t('agentPackage.result.cleanSuccess'));
    reset();
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    cleaning.value = false;
  }
}

function reset() {
  activeStep.value = 1;
  selectedFile.value = null;
  fileList.value = [];
  targetFolderId.value = null;
  previewData.value = null;
  report.value = null;
  if (!agentStore.allAgents.length) {
    agentStore.fetchAllAgents();
  }
}
</script>

<style scoped>
.step-body {
  min-height: 200px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 8px 0 8px;
}

.preview-tree {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  max-height: 260px;
  overflow: auto;
}

.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.error-box {
  color: var(--el-color-danger);
  word-break: break-all;
  max-width: 560px;
}
</style>
