<!-- frontend/mambo/src/mobile/components/settings/agent/MobileBackendManagerPanel.vue -->
<template>
  <div class="mobile-backend-manager-panel">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-button type="primary" size="small" @click="handleCreate">
        <el-icon><Plus /></el-icon> {{ $t('backend.new', '新建 Backend') }}
      </el-button>
      <el-button size="small" @click="handleShowPublicKey">
        <el-icon><Key /></el-icon> {{ $t('backend.showPublicKey', '系统公钥') }}
      </el-button>
    </div>

    <!-- Backend 卡片列表 -->
    <el-scrollbar class="backend-list-container" v-loading="isLoading">
      <div v-if="backendList.length === 0" class="empty-state">
        <el-empty :description="$t('common.noData', '暂无数据')" />
      </div>
      <div v-else class="backend-card-list">
        <el-card v-for="b in backendList" :key="b.id" class="backend-card" shadow="always">
          <div class="card-header">
            <span class="backend-name">{{ b.name }}</span>
            <el-tag size="small">{{ b.backendType.toUpperCase() }}</el-tag>
          </div>
          <div class="card-body">
            <div class="info-row">
              <span class="label">主机:</span>
              <span class="value">{{ b.configData.username }}@{{ b.configData.hostname }}:{{ b.configData.port || 22 }}</span>
            </div>
            <div class="info-row" v-if="b.description">
              <span class="label">描述:</span>
              <span class="value">{{ b.description }}</span>
            </div>
          </div>
          <div class="card-footer">
            <el-button link type="primary" @click="handleEdit(b)">{{ $t('common.action.edit', '编辑') }}</el-button>
            <el-popconfirm :title="$t('common.msg.confirmDelete', '确定要删除吗？')" @confirm="handleDelete(b.id)">
              <template #reference>
                <el-button link type="danger">{{ $t('common.action.delete', '删除') }}</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </div>
    </el-scrollbar>

    <!-- Backend 表单弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? $t('backend.edit', '编辑 Backend') : $t('backend.new', '新建 Backend')"
      width="90%"
      :close-on-click-modal="false"
      class="mobile-dialog"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" v-loading="isSaving">
        <el-form-item :label="$t('backend.name', '名称')" prop="name">
          <el-input v-model="form.name" :disabled="isEdit" placeholder="仅允许字母、数字、下划线" />
        </el-form-item>
        <el-form-item :label="$t('backend.description', '描述')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="$t('backend.type', '类型')" prop="backendType">
          <el-select v-model="form.backendType" disabled style="width: 100%">
            <el-option label="SSH" value="ssh" />
          </el-select>
        </el-form-item>

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
      </el-form>
      <template #footer>
        <div class="dialog-footer-actions">
          <el-button type="info" plain size="small" @click="handleTestConnection" :loading="isTesting">
            <el-icon><Connection /></el-icon> 测试
          </el-button>
          <div class="right-actions">
            <el-button size="small" @click="dialogVisible = false">{{ $t('common.action.cancel', '取消') }}</el-button>
            <el-button type="primary" size="small" @click="submitForm" :loading="isSaving">{{ $t('common.action.confirm', '确定') }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 公钥展示弹窗 -->
    <el-dialog v-model="keyDialogVisible" :title="$t('backend.systemPublicKey', '系统 SSH 公钥')" width="90%">
      <div v-loading="!systemPublicKey" class="public-key-container">
        <p class="key-tip">请将以下公钥添加到目标服务器的 <code>~/.ssh/authorized_keys</code> 文件中，以实现免密登录。</p>
        <el-input v-model="systemPublicKey" type="textarea" :rows="6" readonly class="key-textarea" />
      </div>
      <template #footer>
        <el-button @click="keyDialogVisible = false">{{ $t('common.action.close', '关闭') }}</el-button>
        <el-button type="primary" @click="copyPublicKey" :disabled="!systemPublicKey">
          {{ $t('common.action.copy', '复制') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Plus, Key, Connection } from '@element-plus/icons-vue';
import { useBackendStore } from '@/stores/backendStore';
import { copyToClipboard } from '@/utils/clipboard';
import type { BackendConfig, BackendCreate, SshConfigData, SshTestRequest } from '@/api/types/backendTypes';

const backendStore = useBackendStore();
const { backendList, isLoading, systemPublicKey } = storeToRefs(backendStore);

const dialogVisible = ref(false);
const keyDialogVisible = ref(false);
const isEdit = ref(false);
const isSaving = ref(false);
const isTesting = ref(false);
const currentEditId = ref<string | null>(null);

const formRef = ref<FormInstance>();

const defaultForm = (): BackendCreate => ({
  name: '',
  description: '',
  backendType: 'ssh',
  configData: {
    hostname: '',
    username: 'root',
    port: 22,
    password: null,
    root_dir: '/',
    edit_whitelist: [],
    edit_blacklist: [],
    ignore_dirs: ['.git', 'node_modules', 'build']
  }
});

const form = reactive<BackendCreate>(defaultForm());

const rules = reactive<FormRules>({
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '仅允许包含字母、数字和下划线', trigger: 'blur' }
  ],
  'configData.hostname': [{ required: true, message: '请输入主机地址', trigger: 'blur' }],
  'configData.username': [{ required: true, message: '请输入用户名', trigger: 'blur' }]
});

onMounted(() => {
  backendStore.fetchBackends();
});

const handleCreate = () => {
  isEdit.value = false;
  currentEditId.value = null;
  Object.assign(form, defaultForm());
  dialogVisible.value = true;
  formRef.value?.clearValidate();
};

const handleEdit = (row: BackendConfig) => {
  isEdit.value = true;
  currentEditId.value = row.id;

  const configData = JSON.parse(JSON.stringify(row.configData)) as SshConfigData;

  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    backendType: row.backendType,
    configData: {
      ...configData,
      edit_whitelist: configData.edit_whitelist || [],
      edit_blacklist: configData.edit_blacklist || [],
      ignore_dirs: configData.ignore_dirs || []
    }
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
        if (submitData.configData.edit_whitelist?.length === 0) submitData.configData.edit_whitelist = null;
        if (submitData.configData.edit_blacklist?.length === 0) submitData.configData.edit_blacklist = null;
        if (submitData.configData.ignore_dirs?.length === 0) submitData.configData.ignore_dirs = null;
        if (!submitData.configData.password) submitData.configData.password = null;

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

.card-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 8px;
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
</style>
