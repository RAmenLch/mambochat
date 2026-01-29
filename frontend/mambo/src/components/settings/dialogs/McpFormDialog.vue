<template>
  <el-dialog
    :model-value="visible"
    :title="isEditMode ? '编辑 MCP 服务' : '新增 MCP 服务'"
    width="600px"
    @update:model-value="handleUpdateVisible"
    @closed="handleClosed"
    :close-on-click-modal="false"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="100px"
      label-position="right"
    >
      <el-form-item label="名称" prop="name">
        <el-input v-model="formData.name" placeholder="请输入服务名称" />
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input v-model="formData.description" type="textarea" placeholder="可选描述" />
      </el-form-item>

      <el-form-item label="传输类型" prop="transportType">
        <el-radio-group v-model="formData.transportType" @change="handleTransportChange">
          <el-radio-button value="stdio">Stdio (本地进程)</el-radio-button>
          <el-radio-button value="sse">SSE (远程服务)</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="启用状态" prop="isEnabled">
        <el-switch v-model="formData.isEnabled" />
      </el-form-item>

      <!-- Stdio 专属字段 -->
      <template v-if="formData.transportType === 'stdio'">
        <el-divider content-position="left">Stdio 配置</el-divider>
        <el-form-item label="Command" prop="command">
          <el-input v-model="formData.command" placeholder="例如: python, node, uvx" />
        </el-form-item>

        <el-form-item label="Args">
          <div class="dynamic-list">
            <div v-for="(arg, index) in formData.argsList" :key="index" class="dynamic-row">
              <el-input v-model="formData.argsList[index]" placeholder="参数" />
              <el-button type="danger" :icon="Minus" circle size="small" @click="removeArg(index)" />
            </div>
            <el-button type="primary" link :icon="Plus" @click="addArg">添加参数</el-button>
          </div>
        </el-form-item>

        <el-form-item label="Env">
          <div class="dynamic-list">
            <div v-for="(env, index) in formData.envList" :key="index" class="dynamic-row">
              <el-input v-model="env.key" placeholder="变量名 (KEY)" style="flex: 1" />
              <span class="separator">=</span>
              <el-input v-model="env.value" placeholder="变量值 (VALUE)" style="flex: 1" />
              <el-button type="danger" :icon="Minus" circle size="small" @click="removeEnv(index)" />
            </div>
            <el-button type="primary" link :icon="Plus" @click="addEnv">添加环境变量</el-button>
          </div>
        </el-form-item>
      </template>

      <!-- SSE 专属字段 -->
      <template v-if="formData.transportType === 'sse'">
        <el-divider content-position="left">SSE 配置</el-divider>
        <el-form-item label="URL" prop="url">
          <el-input v-model="formData.url" placeholder="例如: http://localhost:8080/sse" />
        </el-form-item>
      </template>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="handleCancel">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="isSubmitting">
          确定
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { Plus, Minus } from '@element-plus/icons-vue';
import type { FormInstance, FormRules } from 'element-plus';
import type { McpServer, McpCreateRequest, McpTransportType } from '@/api/types';

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

// 内部表单数据结构，为了方便 UI 绑定，将 args 和 env 转换为数组形式
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

const rules = computed<FormRules>(() => {
  const commonRules = {
    name: [{ required: true, message: '请输入服务名称', trigger: 'blur' }],
  };

  if (formData.transportType === 'stdio') {
    return {
      ...commonRules,
      command: [{ required: true, message: '请输入执行命令', trigger: 'blur' }],
    };
  } else {
    return {
      ...commonRules,
      url: [{ required: true, message: '请输入 SSE URL', trigger: 'blur' }],
    };
  }
});

// 监听 visible 和 initialData 变化以初始化表单
watch(
  () => [props.visible, props.initialData],
  ([newVisible]) => {
    if (newVisible) {
      if (props.initialData) {
        // 编辑模式：回填数据
        const data = props.initialData as McpServer;
        formData.name = data.name;
        formData.description = data.description || '';
        formData.transportType = data.transportType;
        formData.isEnabled = data.isEnabled;
        formData.command = data.command || '';
        formData.url = data.url || '';

        // 转换 args
        formData.argsList = data.args ? [...data.args] : [];

        // 转换 env
        formData.envList = data.env
          ? Object.entries(data.env).map(([key, value]) => ({ key, value }))
          : [];
      } else {
        // 新增模式：重置
        Object.assign(formData, JSON.parse(JSON.stringify(defaultFormData)));
      }
    }
  }
);

const handleTransportChange = () => {
  // 切换类型时清除校验结果
  formRef.value?.clearValidate();
};

const addArg = () => {
  formData.argsList.push('');
};

const removeArg = (index: number) => {
  formData.argsList.splice(index, 1);
};

const addEnv = () => {
  formData.envList.push({ key: '', value: '' });
};

const removeEnv = (index: number) => {
  formData.envList.splice(index, 1);
};

const handleUpdateVisible = (val: boolean) => {
  emit('update:visible', val);
};

const handleCancel = () => {
  emit('update:visible', false);
};

const handleClosed = () => {
  formRef.value?.resetFields();
};

const handleSubmit = async () => {
  if (!formRef.value) return;

  await formRef.value.validate((valid) => {
    if (valid) {
      // 构造提交数据
      const requestData: McpCreateRequest = {
        name: formData.name,
        description: formData.description || null,
        transportType: formData.transportType,
        isEnabled: formData.isEnabled,
      };

      if (formData.transportType === 'stdio') {
        requestData.command = formData.command;
        // 过滤空参数
        const validArgs = formData.argsList.filter(a => a.trim() !== '');
        requestData.args = validArgs.length > 0 ? validArgs : null;

        // 转换 env 数组为对象
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

.separator {
  font-weight: bold;
  color: var(--el-text-color-secondary);
}
</style>
