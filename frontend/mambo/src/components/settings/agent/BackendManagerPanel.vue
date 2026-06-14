<!-- frontend/mambo/src/components/settings/agent/BackendManagerPanel.vue -->
<template>
  <div class="backend-manager-panel">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon> {{ $t('backend.new') }}
      </el-button>
      <el-button @click="handleShowPublicKey">
        <el-icon><Key /></el-icon> {{ $t('backend.showPublicKey') }}
      </el-button>
    </div>

    <!-- Backend 列表 -->
    <el-table :data="backendList" v-loading="isLoading" border stripe class="backend-table">
      <el-table-column prop="name" :label="$t('backend.name')" width="150" />
      <el-table-column prop="backendType" :label="$t('backend.type')" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.backendType === 'ssh'" size="small" type="info">SSH</el-tag>
          <el-tag v-else-if="row.backendType === 'api'" size="small" type="success">API</el-tag>
          <el-tag v-else-if="row.backendType === 'resource'" size="small" type="warning">Resource</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('backend.host')" min-width="220">
        <template #default="{ row }">
          <template v-if="row.backendType === 'ssh'">
            {{ row.configData.username }}@{{ row.configData.hostname }}:{{ row.configData.port || 22 }}
          </template>
          <template v-else-if="row.backendType === 'api'">
            <div class="api-info">
              <span class="api-label">ID:</span>
              <span class="api-id">{{ row.id }}</span>
              <el-tag
                v-if="clientStatusMap[row.id]"
                :type="clientStatusMap[row.id]?.connected ? 'success' : 'danger'"
                size="small"
                class="status-tag"
              >
                {{ clientStatusMap[row.id]?.connected ? 'Connected' : 'Offline' }}
              </el-tag>
            </div>
          </template>
          <template v-else-if="row.backendType === 'resource'">
            <div class="api-info">
              <span class="api-label">Resource ID:</span>
              <span class="api-id">{{ row.configData.resource_id }}</span>
            </div>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="description" :label="$t('backend.description')" show-overflow-tooltip />
      <el-table-column :label="$t('common.action.operate')" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleEdit(row)">{{ $t('common.action.edit') }}</el-button>
          <el-popconfirm :title="$t('common.msg.confirmDelete')" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button link type="danger">{{ $t('common.action.delete') }}</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Backend 表单弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? $t('backend.edit') : $t('backend.new')"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="currentRules" label-width="120px" v-loading="isSaving">
        <el-form-item :label="$t('backend.name')" prop="name">
          <el-input v-model="form.name" placeholder="仅允许字母、数字、下划线 (作为路由路径)" />
        </el-form-item>
        <el-form-item :label="$t('backend.description')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="$t('backend.type')" prop="backendType">
          <el-select v-model="form.backendType" :disabled="isEdit" style="width: 100%" @change="handleTypeChange">
            <el-option label="SSH (远程服务器)" value="ssh" />
            <el-option label="API (客户端连接)" value="api" />
            <el-option label="Resource (资源文件夹)" value="resource" />
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
            <el-input-number v-model="form.configData.port" :min="1" :max="65535" controls-position="right" />
          </el-form-item>
          <el-form-item label="Password" prop="configData.password">
            <el-input v-model="form.configData.password" type="password" show-password placeholder="不填则使用系统公钥免密登录" />
          </el-form-item>
        </template>

        <!-- API 配置 -->
        <template v-if="form.backendType === 'api'">
          <el-divider content-position="left">API 客户端配置</el-divider>
          <el-form-item label="API Key" prop="configData.api_key">
            <el-input v-model="form.configData.api_key" :type="showApiKey ? 'text' : 'password'" show-password placeholder="客户端连接时使用的密钥">
              <template #append>
                <el-button @click="showApiKey = !showApiKey">
                  <el-icon><View v-if="!showApiKey" /><Hide v-else /></el-icon>
                </el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="Edit Whitelist" prop="configData.edit_whitelist">
            <el-select v-model="form.configData.edit_whitelist" multiple filterable allow-create default-first-option placeholder="例如: *.py (回车添加)" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Edit Blacklist" prop="configData.edit_blacklist">
            <el-select v-model="form.configData.edit_blacklist" multiple filterable allow-create default-first-option placeholder="例如: .env (回车添加)" style="width: 100%" />
          </el-form-item>
          <div class="api-tip">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>
                创建成功后，将显示的 <b>Backend ID</b> 和 <b>API Key</b> 填入客户端启动命令中：<br/>
                <code>python main.py --server-url ws://服务器地址 --backend-id &lt;ID&gt; --api-key &lt;KEY&gt; --root-dir /你的项目</code>
              </template>
            </el-alert>
          </div>
        </template>

        <!-- Resource 配置 -->
        <template v-if="form.backendType === 'resource'">
          <el-divider content-position="left">资源文件夹配置</el-divider>
          <el-form-item label="Resource ID" prop="configData.resource_id">
            <el-select
              v-model="form.configData.resource_id"
              placeholder="选择 FOLDER 类型资源作为 workspace root"
              filterable
              clearable
              style="width: 100%"
              :loading="isResourceFoldersLoading"
              @visible-change="onResourceFolderDropdownVisible"
            >
              <el-option
                v-for="folder in resourceFolderOptions"
                :key="folder.id"
                :label="folder.name"
                :value="folder.id"
              >
                <span>{{ folder.name }}</span>
                <span class="resource-mount-path" style="float: right; color: var(--el-text-color-secondary); font-size: 12px;" v-if="folder.path">{{ folder.path }}</span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="Edit Whitelist" prop="configData.edit_whitelist">
            <el-select v-model="form.configData.edit_whitelist" multiple filterable allow-create default-first-option placeholder="例如: *.py, *.md (回车添加)" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Edit Blacklist" prop="configData.edit_blacklist">
            <el-select v-model="form.configData.edit_blacklist" multiple filterable allow-create default-first-option placeholder="例如: .env (回车添加)" style="width: 100%" />
          </el-form-item>
          <div class="api-tip">
            <el-alert type="success" :closable="false" show-icon>
              <template #title>
                将资源文件夹映射为 Agent 的虚拟文件系统（workspace root）。<br/>
                仅 <b>Mambo Agent</b> 可挂载 Resource 类型 Backend，DeepAgent 不可用。
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
            <el-select v-model="form.configData.edit_whitelist" multiple filterable allow-create default-first-option placeholder="例如: *.py (回车添加)" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Edit Blacklist" prop="configData.edit_blacklist">
            <el-select v-model="form.configData.edit_blacklist" multiple filterable allow-create default-first-option placeholder="例如: .env (回车添加)" style="width: 100%" />
          </el-form-item>
          <el-form-item label="Ignore Dirs" prop="configData.ignore_dirs">
            <el-select v-model="form.configData.ignore_dirs" multiple filterable allow-create default-first-option placeholder="例如: .git, node_modules (回车添加)" style="width: 100%" />
          </el-form-item>
        </template>

        <!-- 工具配置 (仅 SSH / API) -->
        <template v-if="form.backendType === 'ssh' || form.backendType === 'api'">
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
        </template>
      </el-form>
      <template #footer>
        <div class="dialog-footer-actions">
          <el-button
            v-if="form.backendType === 'ssh'"
            type="info"
            plain
            @click="handleTestConnection"
            :loading="isTesting"
          >
            <el-icon><Connection /></el-icon> {{ $t('backend.testConnection') }}
          </el-button>
          <div class="right-actions">
            <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
            <el-button type="primary" @click="submitForm" :loading="isSaving">{{ $t('common.action.confirm') }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 公钥展示弹窗 -->
    <el-dialog v-model="keyDialogVisible" :title="$t('backend.systemPublicKey')" width="500px">
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
import { Plus, Key, Connection, View, Hide } from '@element-plus/icons-vue';
import { useBackendStore } from '@/stores/backendStore';
import { useResourceStore } from '@/stores/resourceStore';
import { copyToClipboard } from '@/utils/clipboard';
import { getClientStatus } from '@/api/backendService';
import type { BackendConfig, BackendCreate, BackendType, SshConfigData, ApiConfigData, ResourceConfigData, SshTestRequest } from '@/api/types/backendTypes';
import { isSshConfig, defaultToolsConfig } from '@/api/types/backendTypes';

const backendStore = useBackendStore();
const resourceStore = useResourceStore();
const { backendList, isLoading, systemPublicKey } = storeToRefs(backendStore);
const { resourceTree } = storeToRefs(resourceStore);

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

const resourceDefaultConfig = (): ResourceConfigData => ({
  resource_id: '',
  edit_whitelist: [],
  edit_blacklist: [],
});

const defaultForm = (type: BackendType = 'ssh'): BackendCreate => ({
  name: '',
  description: '',
  backendType: type,
  configData: type === 'ssh' ? sshDefaultConfig() : type === 'api' ? apiDefaultConfig() : resourceDefaultConfig(),
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

const resourceRules: FormRules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '仅允许包含字母、数字和下划线', trigger: 'blur' }
  ],
  'configData.resource_id': [{ required: true, message: '请选择资源文件夹', trigger: 'change' }]
};

const currentRules = computed(() => {
  if (form.backendType === 'ssh') return sshRules;
  if (form.backendType === 'api') return apiRules;
  return resourceRules;
});

const handleTypeChange = (type: BackendType) => {
  const newForm = defaultForm(type);
  newForm.name = form.name;
  newForm.description = form.description;
  Object.assign(form, newForm);
  formRef.value?.clearValidate();
};

// --- 资源文件夹选择器逻辑 ---
const isResourceFoldersLoading = ref(false);

function collectFolders(nodes: any[]): { id: string; name: string; path: string }[] {
  const folders: { id: string; name: string; path: string }[] = [];
  for (const node of nodes) {
    if (node.itemType === 'folder') {
      folders.push({ id: node.id, name: node.name, path: '' });
    }
    if (node.children && node.children.length > 0) {
      folders.push(...collectFolders(node.children));
    }
  }
  return folders;
}

const resourceFolderOptions = computed(() => {
  return collectFolders(resourceTree.value);
});

async function onResourceFolderDropdownVisible(visible: boolean) {
  if (visible && resourceTree.value.length === 0) {
    isResourceFoldersLoading.value = true;
    try {
      await resourceStore.initializeList();
    } finally {
      isResourceFoldersLoading.value = false;
    }
  }
}

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
        } else if (submitData.backendType === 'api') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
          if (!cd.api_key) cd.api_key = null;
        } else if (submitData.backendType === 'resource') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
        }

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
.backend-manager-panel {
  padding: 20px;
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

.backend-table {
  flex-grow: 1;
}

.api-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.api-label {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.api-id {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-regular);
  word-break: break-all;
}

.status-tag {
  margin-left: auto;
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
  gap: 12px;
}

.tools-config-row {
  display: flex;
  align-items: center;
  gap: 8px;
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
