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
      <el-table-column prop="backendType" :label="$t('backend.type')" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ row.backendType.toUpperCase() }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('backend.host')" width="200">
        <template #default="{ row }">
          {{ row.configData.username }}@{{ row.configData.hostname }}:{{ row.configData.port || 22 }}
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
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" v-loading="isSaving">
        <el-form-item :label="$t('backend.name')" prop="name">
          <el-input v-model="form.name" :disabled="isEdit" placeholder="仅允许字母、数字、下划线 (作为路由路径)" />
        </el-form-item>
        <el-form-item :label="$t('backend.description')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="$t('backend.type')" prop="backendType">
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
          <el-input-number v-model="form.configData.port" :min="1" :max="65535" controls-position="right" />
        </el-form-item>
        <el-form-item label="Password" prop="configData.password">
          <el-input v-model="form.configData.password" type="password" show-password placeholder="不填则使用系统公钥免密登录" />
        </el-form-item>
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
      </el-form>
      <template #footer>
        <div class="dialog-footer-actions">
          <el-button type="info" plain @click="handleTestConnection" :loading="isTesting">
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
const isTesting = ref(false); // [新增] 测试连接状态
const currentEditId = ref<string | null>(null);

const formRef = ref<FormInstance>();

// 表单初始数据
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

// 校验规则
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

  // 深拷贝，防止直接修改 store 数据
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

// [新增] 测试连接
const handleTestConnection = async () => {
  if (!formRef.value) return;
  // 测试前仅校验表单，确保必填项（如 hostname, username）已填写
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
        // 数据清洗：将空数组转为 null 以符合后端规范
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

/* [新增] 底部操作按钮布局 */
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
</style>
