<!-- frontend/mambo/src/mobile/components/settings/agent/MobileBackendManagerPanel.vue -->
<template>
  <div class="mobile-backend-manager-panel">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-button type="primary" size="small" @click="handleCreate">
        <el-icon><Plus /></el-icon> {{ $t('backend.new') }}
      </el-button>
      <el-button size="small" @click="handleShowPublicKey">
        <el-icon><Key /></el-icon> {{ $t('backend.showPublicKey') }}
      </el-button>
    </div>

    <!-- Backend 卡片列表 -->
    <el-scrollbar class="backend-list-container" v-loading="isLoading">
      <div v-if="backendList.length === 0" class="empty-state">
        <el-empty :description="$t('common.noData')" />
      </div>
      <div v-else class="backend-card-list">
        <el-card v-for="b in backendList" :key="b.id" class="backend-card" shadow="always">
          <div class="card-header">
            <span class="backend-name">{{ b.name }}</span>
            <div class="header-right">
              <el-tag size="small" :type="b.backendType === 'api' ? 'success' : 'info'">
                {{ b.backendType === 'api' ? 'API' : 'SSH' }}
              </el-tag>
              <el-tag
                v-if="b.backendType === 'api' && clientStatusMap[b.id]"
                :type="clientStatusMap[b.id]?.connected ? 'success' : 'danger'"
                size="small"
              >
                {{ clientStatusMap[b.id]?.connected ? 'Online' : 'Offline' }}
              </el-tag>
            </div>
          </div>
          <div class="card-body">
            <template v-if="b.backendType === 'ssh'">
              <div class="info-row">
                <span class="label">主机:</span>
                <span class="value">{{ b.configData.username }}@{{ b.configData.hostname }}:{{ b.configData.port || 22 }}</span>
              </div>
            </template>
            <template v-else-if="b.backendType === 'api'">
              <div class="info-row">
                <span class="label">ID:</span>
                <span class="value api-id">{{ b.id }}</span>
              </div>
            </template>
            <div class="info-row" v-if="b.description">
              <span class="label">描述:</span>
              <span class="value">{{ b.description }}</span>
            </div>
          </div>
          <div class="card-footer">
            <el-button link type="primary" @click="handleEdit(b)">{{ $t('common.action.edit') }}</el-button>
            <el-popconfirm :title="$t('common.msg.confirmDelete')" @confirm="handleDelete(b.id)">
              <template #reference>
                <el-button link type="danger">{{ $t('common.action.delete') }}</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </div>
    </el-scrollbar>

    <!-- Backend 表单弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? $t('backend.edit') : $t('backend.new')"
      width="90%"
      :close-on-click-modal="false"
      class="mobile-dialog"
    >
      <el-form ref="formRef" :model="form" :rules="currentRules" label-position="top" v-loading="isSaving">
        <el-form-item :label="$t('backend.name')" prop="name">
          <el-input v-model="form.name" placeholder="仅允许字母、数字、下划线" />
        </el-form-item>
        <el-form-item :label="$t('backend.description')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="$t('backend.type')" prop="backendType">
          <el-select v-model="form.backendType" :disabled="isEdit" style="width: 100%" @change="handleTypeChange">
            <el-option label="SSH (远程服务器)" value="ssh" />
            <el-option label="API (客户端连接)" value="api" />
          </el-select>
        </el-form-item>

        <!-- SSH 配置 -->
        <template v-if="form.backendType === 'ssh'">
          <el-divider content-position="left">SSH 配置</el-divider>
          <el-form-item label="Hostname" prop="configData.hostname">
            <el-input v-model="form.configData.hostname" placeholder="192.168.1.100 或 example.com" />
          </el-form-item>
          <el-form-item label="Username" prop="configData.username">
            <el-input v-model="form.configData.username" placeholder="root" />
          </el-form-item>
          <el-form-item label="Port" prop="configData.port">
            <el-input-number v-model="form.configData.port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Password" prop="configData.password">
            <el-input v-model="form.configData.password" type="password" show-password placeholder="不填则使用系统公钥免密登录" />
          </el-form-item>
        </template>

        <!-- API 配置 -->
        <template v-if="form.backendType === 'api'">
          <el-divider content-position="left">API 客户端配置</el-divider>
          <el-form-item label="API Key" prop="configData.api_key">
            <el-input v-model="form.configData.api_key" :type="showApiKey ? 'text' : 'password'" show-password placeholder="客户端连接时使用的密钥" />
          </el-form-item>
          <el-form-item label="Edit Whitelist" prop="configData.edit_whitelist">
            <el-select v-model="form.configData.edit_whitelist" multiple filterable allow-create default-first-option placeholder="例如: *.py" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Edit Blacklist" prop="configData.edit_blacklist">
            <el-select v-model="form.configData.edit_blacklist" multiple filterable allow-create default-first-option placeholder="例如: .env" style="width: 100%" />
          </el-form-item>
          <div class="api-tip">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>
                创建成功后，将 Backend ID 和 API Key 填入客户端命令：<br/>
                <code style="word-break: break-all;">python main.py --server-url ws://服务器 --backend-id &lt;ID&gt; --api-key &lt;KEY&gt; --root-dir /你的项目</code>
              </template>
            </el-alert>
          </div>
        </template>

        <!-- 通用配置 (仅 SSH) -->
        <template v-if="form.backendType === 'ssh'">
          <el-divider content-position="left">通用配置</el-divider>

          <el-form-item label="Root Dir" prop="configData.root_dir">
            <el-input v-model="form.configData.root_dir" placeholder="默认: /" />
          </el-form-item>
          <el-form-item label="Edit Whitelist" prop="configData.edit_whitelist">
            <el-select v-model="form.configData.edit_whitelist" multiple filterable allow-create default-first-option placeholder="例如: *.py" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Edit Blacklist" prop="configData.edit_blacklist">
            <el-select v-model="form.configData.edit_blacklist" multiple filterable allow-create default-first-option placeholder="例如: .env" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Ignore Dirs" prop="configData.ignore_dirs">
            <el-select v-model="form.configData.ignore_dirs" multiple filterable allow-create default-first-option placeholder="例如: .git" style="width: 100%" />
          </el-form-item>
        </template>

        <!-- 工具配置 -->
        <el-divider content-position="left">{{ $t('backend.toolConfig') }}</el-divider>
        <el-form-item label="Execute (命令执行)">
          <div class="tools-config-row">
            <span class="tools-config-label">{{ $t('backend.toolEnabled') }}</span>
            <el-switch v-model="form.tools_config!.execute.enabled" />
            <template v-if="form.tools_config!.execute.enabled">
              <span class="tools-config-label" style="margin-left: 16px;">{{ $t('backend.toolRequireReview') }}</span>
              <el-switch v-model="form.tools_config!.execute.require_review" />
            </template>
          </div>
          <div class="tools-config-tip">{{ $t('backend.toolExecuteTip') }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer-actions">
          <el-button
            v-if="form.backendType === 'ssh'"
            type="info"
            plain
            size="small"
            @click="handleTestConnection"
            :loading="isTesting"
          >
            <el-icon><Connection /></el-icon> 测试
          </el-button>
          <div class="right-actions">
            <el-button size="small" @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
            <el-button type="primary" size="small" @click="submitForm" :loading="isSaving">{{ $t('common.action.confirm') }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 公钥展示弹窗 -->
    <el-dialog v-model="keyDialogVisible" :title="$t('backend.systemPublicKey')" width="90%">
      <div v-loading="!systemPublicKey" class="public-key-container">
        <p class="key-tip">请将以下公钥添加到目标服务器的 <code>~/.ssh/authorized_keys</code> 文件中，以实现免密登录。</p>
        <el-input v-model="systemPublicKey" type="textarea" :rows="6" readonly class="key-textarea" />
      </div>
      <template #footer>
        <el-button @click="keyDialogVisible = false">{{ $t('common.action.close') }}</el-button>
        <el-button type="primary" @click="copyPublicKey" :disabled="!systemPublicKey">
          {{ $t('common.action.copy') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Plus, Key, Connection } from '@element-plus/icons-vue';
import { useBackendStore } from '@/stores/backendStore';
import { copyToClipboard } from '@/utils/clipboard';
import { getClientStatus } from '@/api/backendService';
import type { BackendConfig, BackendCreate, BackendType, SshConfigData, ApiConfigData, SshTestRequest } from '@/api/types/backendTypes';
import { defaultToolsConfig } from '@/api/types/backendTypes';

const backendStore = useBackendStore();
const { backendList, isLoading, systemPublicKey } = storeToRefs(backendStore);

const dialogVisible = ref(false);
const keyDialogVisible = ref(false);
const isEdit = ref(false);
const isSaving = ref(false);
const isTesting = ref(false);
const showApiKey = ref(false);
const currentEditId = ref<string | null>(null);

const formRef = ref<FormInstance>();
const clientStatusMap = ref<Record<string, { connected: boolean }>>({});
let statusPollTimer: ReturnType<typeof setInterval> | null = null;

const sshDefaultConfig = (): SshConfigData => ({
  hostname: '',
  username: 'root',
  port: 22,
  password: null,
  root_dir: '/',
  edit_whitelist: [],
  edit_blacklist: [],
  ignore_dirs: ['.git', 'node_modules', 'build']
});

const apiDefaultConfig = (): ApiConfigData => ({
  api_key: '',
  edit_whitelist: [],
  edit_blacklist: [],
});

const defaultForm = (type: BackendType = 'ssh'): BackendCreate => ({
  name: '',
  description: '',
  backendType: type,
  configData: type === 'ssh' ? sshDefaultConfig() : apiDefaultConfig(),
  tools_config: defaultToolsConfig()
});

const form = reactive<BackendCreate>(defaultForm('ssh'));

const sshRules: FormRules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '仅允许包含字母、数字和下划线', trigger: 'blur' }
  ],
  'configData.hostname': [{ required: true, message: '请输入主机地址', trigger: 'blur' }],
  'configData.username': [{ required: true, message: '请输入用户名', trigger: 'blur' }]
};

const apiRules: FormRules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '仅允许包含字母、数字和下划线', trigger: 'blur' }
  ],
  'configData.api_key': [{ required: true, message: '请输入 API Key', trigger: 'blur' }]
};

const currentRules = computed(() => form.backendType === 'ssh' ? sshRules : apiRules);

const handleTypeChange = (type: BackendType) => {
  const newForm = defaultForm(type);
  newForm.name = form.name;
  newForm.description = form.description;
  Object.assign(form, newForm);
  formRef.value?.clearValidate();
};

function maskKey(key?: string | null): string {
  if (!key) return '***';
  if (key.length <= 8) return '********';
  return key.slice(0, 4) + '****' + key.slice(-4);
}

async function fetchClientStatuses() {
  for (const b of backendList.value) {
    if (b.backendType === 'api') {
      try {
        const status = await getClientStatus(b.id);
        clientStatusMap.value[b.id] = status;
      } catch {
        clientStatusMap.value[b.id] = { connected: false };
      }
    }
  }
}

onMounted(() => {
  backendStore.fetchBackends();
  statusPollTimer = setInterval(fetchClientStatuses, 15000);
});

onUnmounted(() => {
  if (statusPollTimer) clearInterval(statusPollTimer);
});

const handleCreate = () => {
  isEdit.value = false;
  currentEditId.value = null;
  showApiKey.value = false;
  Object.assign(form, defaultForm('ssh'));
  dialogVisible.value = true;
  formRef.value?.clearValidate();
};

const handleEdit = (row: BackendConfig) => {
  isEdit.value = true;
  currentEditId.value = row.id;
  showApiKey.value = false;

  const type = row.backendType;
  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    backendType: type,
    configData: {
      ...(JSON.parse(JSON.stringify(row.configData))),
      edit_whitelist: (row.configData as any).edit_whitelist || [],
      edit_blacklist: (row.configData as any).edit_blacklist || [],
      ignore_dirs: (row.configData as any).ignore_dirs || [],
    },
    tools_config: row.tools_config ? JSON.parse(JSON.stringify(row.tools_config)) : defaultToolsConfig(),
  });
  dialogVisible.value = true;
  formRef.value?.clearValidate();
};

const handleDelete = async (id: string) => {
  try {
    await backendStore.removeBackend(id);
    ElMessage.success('删除成功');
  } catch (error) {
    ElMessage.error('删除失败');
  }
};

const handleTestConnection = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isTesting.value = true;
      try {
        const testData: SshTestRequest = {
          backend_id: isEdit.value ? currentEditId.value : null,
          configData: {
            ...form.configData,
            edit_whitelist: form.configData.edit_whitelist?.length === 0 ? null : form.configData.edit_whitelist,
            edit_blacklist: form.configData.edit_blacklist?.length === 0 ? null : form.configData.edit_blacklist,
            ignore_dirs: form.configData.ignore_dirs?.length === 0 ? null : form.configData.ignore_dirs,
            password: form.configData.password || null
          }
        };
        const res = await backendStore.testConnection(testData);
        if (res.success) {
          ElMessage.success(res.message || '连接成功');
        } else {
          ElMessage.error(res.message || '连接失败');
        }
      } catch (error: any) {
        ElMessage.error(error.message || '测试连接发生异常');
      } finally {
        isTesting.value = false;
      }
    }
  });
};

const submitForm = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isSaving.value = true;
      try {
        const submitData: BackendCreate = JSON.parse(JSON.stringify(form));
        const cd = submitData.configData as any;

        if (submitData.backendType === 'ssh') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
          if (cd.ignore_dirs?.length === 0) cd.ignore_dirs = null;
          if (!cd.password) cd.password = null;
        } else {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
        }
        if (submitData.backendType === 'api' && !cd.api_key) cd.api_key = null;

        if (isEdit.value && currentEditId.value) {
          await backendStore.updateExistingBackend(currentEditId.value, submitData);
          ElMessage.success('更新成功');
        } else {
          await backendStore.createNewBackend(submitData);
          ElMessage.success('创建成功');
        }
        dialogVisible.value = false;
      } catch (error) {
        ElMessage.error(isEdit.value ? '更新失败' : '创建失败');
      } finally {
        isSaving.value = false;
      }
    }
  });
};

const handleShowPublicKey = async () => {
  keyDialogVisible.value = true;
  if (!systemPublicKey.value) {
    await backendStore.fetchPublicKey();
  }
};

const copyPublicKey = async () => {
  if (systemPublicKey.value) {
    await copyToClipboard(systemPublicKey.value);
    ElMessage.success('公钥已复制到剪贴板');
  }
};
</script>

<style scoped>
.mobile-backend-manager-panel {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.toolbar {
  margin-bottom: 16px;
  display: flex;
  gap: 12px;
}

.backend-list-container {
  flex-grow: 1;
}

.backend-card-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 16px;
}

.backend-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.header-right {
  display: flex;
  gap: 6px;
}

.backend-name {
  font-size: 15px;
  font-weight: 600;
}

.card-body {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 12px;
}

.info-row {
  margin-bottom: 4px;
  display: flex;
  gap: 8px;
}

.label {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.value {
  word-break: break-all;
}

.api-id {
  font-family: monospace;
  font-size: 12px;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 8px;
}

.api-tip {
  margin-bottom: 16px;
}

.public-key-container {
  min-height: 150px;
}

.key-tip {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}

.key-textarea {
  font-family: monospace;
  font-size: 12px;
}

.dialog-footer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.right-actions {
  display: flex;
  gap: 8px;
}

.tools-config-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tools-config-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.tools-config-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
