<template>
  <el-dialog
    :model-value="visible"
    :title="isEditMode ? t('settings.mcp.editTitle') : t('settings.mcp.addTitle')"
    width="100%"
    class="mobile-mcp-dialog"
    @update:model-value="handleUpdateVisible"
    @closed="handleClosed"
    :close-on-click-modal="false"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-position="top"
      status-icon
    >
      <el-form-item :label="t('settings.mcp.columns.name')" prop="name">
        <el-input v-model="formData.name" :placeholder="t('settings.mcp.form.namePlaceholder')" />
      </el-form-item>

      <el-form-item :label="t('settings.mcp.columns.description')" prop="description">
        <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="Optional" />
      </el-form-item>

      <el-form-item :label="t('settings.mcp.columns.type')" prop="transportType">
        <el-radio-group v-model="formData.transportType" @change="handleTransportChange" class="full-width-radio">
          <el-radio-button value="stdio">Stdio</el-radio-button>
          <el-radio-button value="sse">SSE</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="t('settings.mcp.columns.enabled')" prop="isEnabled">
        <el-switch v-model="formData.isEnabled" />
      </el-form-item>

      <!-- Stdio 配置 -->
      <template v-if="formData.transportType === 'stdio'">
        <el-divider content-position="left">Stdio Config</el-divider>

        <el-form-item label="Command" prop="command">
          <el-input v-model="formData.command" placeholder="python, node, uvx..." />
        </el-form-item>

        <el-form-item label="Args">
          <div class="dynamic-list">
            <div v-for="(arg, index) in formData.argsList" :key="index" class="dynamic-row">
              <el-input v-model="formData.argsList[index]" placeholder="Argument" />
              <el-button type="danger" :icon="Minus" circle size="small" @click="removeArg(index)" class="remove-btn" />
            </div>
            <el-button type="primary" plain size="small" :icon="Plus" @click="addArg" class="add-btn">Add Arg</el-button>
          </div>
        </el-form-item>

        <el-form-item label="Environment Variables">
           <div class="dynamic-list">
            <div v-for="(env, index) in formData.envList" :key="index" class="dynamic-row env-row">
              <el-input v-model="env.key" placeholder="KEY" />
              <span class="separator">=</span>
              <el-input v-model="env.value" placeholder="VALUE" />
              <el-button type="danger" :icon="Minus" circle size="small" @click="removeEnv(index)" class="remove-btn" />
            </div>
            <el-button type="primary" plain size="small" :icon="Plus" @click="addEnv" class="add-btn">Add Env</el-button>
          </div>
        </el-form-item>
      </template>

      <!-- SSE 配置 -->
      <template v-if="formData.transportType === 'sse'">
        <el-divider content-position="left">SSE Config</el-divider>
        <el-form-item label="URL" prop="url">
          <el-input v-model="formData.url" placeholder="http://localhost:8080/sse" />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="isSubmitting">
          {{ t('common.action.confirm') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { Plus, Minus } from '@element-plus/icons-vue';
import type { FormInstance, FormRules } from 'element-plus';
import type { McpServer, McpCreateRequest, McpTransportType } from '@/api/types';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps<{
  visible: boolean;
  initialData?: McpServer | null;
  isSubmitting?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'save', data: McpCreateRequest): void;
}>();

const formRef = ref<FormInstance>();

interface LocalFormData {
  name: string;
  description: string;
  transportType: McpTransportType;
  isEnabled: boolean;
  command: string;
  argsList: string[];
  envList: { key: string; value: string }[];
  url: string;
}

const defaultFormData: LocalFormData = {
  name: '',
  description: '',
  transportType: 'stdio',
  isEnabled: true,
  command: '',
  argsList: [],
  envList: [],
  url: '',
};

const formData = reactive<LocalFormData>({ ...defaultFormData });

const isEditMode = computed(() => !!props.initialData);

// 简单的校验规则
const rules = computed<FormRules>(() => {
  const commonRules = {
    name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
  };

  if (formData.transportType === 'stdio') {
    return {
      ...commonRules,
      command: [{ required: true, message: 'Command is required', trigger: 'blur' }],
    };
  } else {
    return {
      ...commonRules,
      url: [{ required: true, message: 'URL is required', trigger: 'blur' }],
    };
  }
});

// 监听数据变化初始化表单
watch(
  () => [props.visible, props.initialData],
  ([newVisible]) => {
    if (newVisible) {
      if (props.initialData) {
        const data = props.initialData as McpServer;
        formData.name = data.name;
        formData.description = data.description || '';
        formData.transportType = data.transportType;
        formData.isEnabled = data.isEnabled;
        formData.command = data.command || '';
        formData.url = data.url || '';
        formData.argsList = data.args ? [...data.args] : [];
        formData.envList = data.env
          ? Object.entries(data.env).map(([key, value]) => ({ key, value }))
          : [];
      } else {
        Object.assign(formData, JSON.parse(JSON.stringify(defaultFormData)));
      }
    }
  }
);

const handleTransportChange = () => {
  formRef.value?.clearValidate();
};

const addArg = () => formData.argsList.push('');
const removeArg = (index: number) => formData.argsList.splice(index, 1);
const addEnv = () => formData.envList.push({ key: '', value: '' });
const removeEnv = (index: number) => formData.envList.splice(index, 1);

const handleUpdateVisible = (val: boolean) => emit('update:visible', val);
const handleCancel = () => emit('update:visible', false);
const handleClosed = () => formRef.value?.resetFields();

const handleSubmit = async () => {
  if (!formRef.value) return;
  await formRef.value.validate((valid) => {
    if (valid) {
      const requestData: McpCreateRequest = {
        name: formData.name,
        description: formData.description || null,
        transportType: formData.transportType,
        isEnabled: formData.isEnabled,
      };

      if (formData.transportType === 'stdio') {
        requestData.command = formData.command;
        const validArgs = formData.argsList.filter(a => a.trim() !== '');
        requestData.args = validArgs.length > 0 ? validArgs : null;
        const validEnv = formData.envList.filter(e => e.key.trim() !== '');
        if (validEnv.length > 0) {
          requestData.env = validEnv.reduce((acc, cur) => {
            acc[cur.key] = cur.value;
            return acc;
          }, {} as Record<string, string>);
        } else {
          requestData.env = null;
        }
      } else {
        requestData.url = formData.url;
      }
      emit('save', requestData);
    }
  });
};
</script>

<style scoped>
.mobile-mcp-dialog :deep(.el-dialog) {
  margin: 0;
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  flex-direction: column;
}

.mobile-mcp-dialog :deep(.el-dialog__body) {
  padding: 10px 20px;
  overflow-y: auto;
  flex: 1;
}

.full-width-radio {
  display: flex;
  width: 100%;
}
.full-width-radio .el-radio-button {
  flex: 1;
}
.full-width-radio :deep(.el-radio-button__inner) {
  width: 100%;
}

.dynamic-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.dynamic-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.env-row .el-input {
  flex: 1;
}

.separator {
  font-weight: bold;
  color: var(--el-text-color-secondary);
}

.remove-btn {
  flex-shrink: 0;
}

.add-btn {
  width: 100%;
  margin-top: 4px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 10px 0 0;
}
</style>
