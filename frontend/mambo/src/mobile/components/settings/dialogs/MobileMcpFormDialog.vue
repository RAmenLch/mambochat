<!-- MobileMcpFormDialog.vue — MCP 表单（Bottom Sheet） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="sheet-overlay" @click="handleCancel">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>
          <div class="sheet-header">
            <span class="sheet-title">{{ isEditMode ? t('settings.mcp.editTitle') : t('settings.mcp.addTitle') }}</span>
            <button class="sheet-close" @click="handleCancel">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-body">
            <el-form ref="formRef" :model="formData" :rules="rules" label-position="top" status-icon>

              <div class="field-item">
                <label class="field-label">{{ t('settings.mcp.columns.name') }}</label>
                <input v-model="formData.name" class="native-input" :placeholder="t('settings.mcp.form.namePlaceholder')" />
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.mcp.columns.description') }}</label>
                <textarea v-model="formData.description" class="native-textarea" :rows="2" placeholder="Optional"></textarea>
              </div>

              <div class="field-item">
                <label class="field-label">{{ t('settings.mcp.columns.type') }}</label>
                <el-radio-group v-model="formData.transportType" @change="handleTransportChange" class="full-radio">
                  <el-radio-button value="stdio">Stdio</el-radio-button>
                  <el-radio-button value="sse">SSE</el-radio-button>
                </el-radio-group>
              </div>

              <div class="field-row">
                <span class="field-label" style="margin-bottom:0">{{ t('settings.mcp.columns.enabled') }}</span>
                <el-switch v-model="formData.isEnabled" size="small" />
              </div>

              <template v-if="formData.transportType === 'stdio'">
                <div class="sheet-divider">Stdio Config</div>

                <div class="field-item">
                  <label class="field-label">Command</label>
                  <input v-model="formData.command" class="native-input" placeholder="python, node, uvx..." />
                </div>

                <div class="field-item">
                  <label class="field-label">Args</label>
                  <div class="dynamic-list">
                    <div v-for="(arg, index) in formData.argsList" :key="index" class="dynamic-row">
                      <input v-model="formData.argsList[index]" class="native-input" placeholder="Argument" style="flex:1" />
                      <button class="chip-close-btn" @click="removeArg(index)">
                        <el-icon :size="16"><Minus /></el-icon>
                      </button>
                    </div>
                    <button class="add-row-btn" @click="addArg">
                      <el-icon :size="14"><Plus /></el-icon> Add Arg
                    </button>
                  </div>
                </div>

                <div class="field-item">
                  <label class="field-label">Environment Variables</label>
                  <div class="dynamic-list">
                    <div v-for="(env, index) in formData.envList" :key="index" class="dynamic-row env-row">
                      <input v-model="env.key" class="native-input" placeholder="KEY" style="flex:1" />
                      <span class="sep">=</span>
                      <input v-model="env.value" class="native-input" placeholder="VALUE" style="flex:1" />
                      <button class="chip-close-btn" @click="removeEnv(index)">
                        <el-icon :size="16"><Minus /></el-icon>
                      </button>
                    </div>
                    <button class="add-row-btn" @click="addEnv">
                      <el-icon :size="14"><Plus /></el-icon> Add Env
                    </button>
                  </div>
                </div>
              </template>

              <template v-if="formData.transportType === 'sse'">
                <div class="sheet-divider">SSE Config</div>
                <div class="field-item">
                  <label class="field-label">URL</label>
                  <input v-model="formData.url" class="native-input" placeholder="http://localhost:8080/sse" />
                </div>
              </template>
            </el-form>

            <div class="test-section">
              <button class="test-btn" @click="handleTestConnection" :disabled="isTestingConnection">
                <el-icon v-if="isTestingConnection" class="is-loading"><Loading /></el-icon>
                <span v-else>{{ t('settings.mcp.testConnection') }}</span>
              </button>
              <div v-if="testFeedback.status !== 'none'" class="test-feedback" :class="testFeedback.status">
                {{ testFeedback.shortMessage }}
              </div>
            </div>
          </div>

          <div class="sheet-footer">
            <button class="footer-btn footer-btn-cancel" @click="handleCancel">{{ t('common.action.cancel') }}</button>
            <button class="footer-btn footer-btn-confirm" @click="handleSubmit" :disabled="isSubmitting">
              {{ t('common.action.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { Plus, Minus, Close, Loading } from '@element-plus/icons-vue';
import type { FormInstance, FormRules } from 'element-plus';
import type { McpServer, McpCreateRequest, McpTransportType } from '@/api/types';
import { useI18n } from 'vue-i18n';
import { useMcpStore } from '@/stores/mcpStore';

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
const mcpStore = useMcpStore();

const isTestingConnection = ref(false);
const testFeedback = reactive({ status: 'none' as 'none' | 'success' | 'error', shortMessage: '', message: '' });

interface LocalFormData {
  name: string; description: string; transportType: McpTransportType; isEnabled: boolean;
  command: string; argsList: string[]; envList: { key: string; value: string }[]; url: string;
}

const defaultFormData: LocalFormData = {
  name: '', description: '', transportType: 'stdio', isEnabled: true,
  command: '', argsList: [], envList: [], url: '',
};

const formData = reactive<LocalFormData>({ ...defaultFormData });
const isEditMode = computed(() => !!props.initialData);

const rules = computed<FormRules>(() => {
  const base = {
    name: [
      { required: true, message: 'Name is required', trigger: 'blur' },
      { max: 64, message: 'Name must not exceed 64 characters', trigger: 'blur' },
      { pattern: /^[a-zA-Z][a-zA-Z0-9_-]*$/, message: 'Name must start with a letter and contain only letters, digits, underscores, and hyphens', trigger: 'blur' },
      {
        validator: (_rule: any, value: string, callback: any) => {
          if (value && value.includes('__')) {
            callback(new Error('Name must not contain "__"'));
          } else {
            callback();
          }
        },
        trigger: 'blur',
      },
    ],
  };
  if (formData.transportType === 'stdio') return { ...base, command: [{ required: true, message: 'Command is required', trigger: 'blur' }] };
  return { ...base, url: [{ required: true, message: 'URL is required', trigger: 'blur' }] };
});

watch(() => [props.visible, props.initialData], ([newVisible]) => {
  if (newVisible) {
    if (props.initialData) {
      const d = props.initialData as McpServer;
      formData.name = d.name; formData.description = d.description || '';
      formData.transportType = d.transportType; formData.isEnabled = d.isEnabled;
      formData.command = d.command || ''; formData.url = d.url || '';
      formData.argsList = d.args ? [...d.args] : [];
      formData.envList = d.env ? Object.entries(d.env).map(([k, v]) => ({ key: k, value: v })) : [];
    } else {
      Object.assign(formData, JSON.parse(JSON.stringify(defaultFormData)));
    }
  }
});

const handleTransportChange = () => formRef.value?.clearValidate();
const addArg = () => formData.argsList.push('');
const removeArg = (i: number) => formData.argsList.splice(i, 1);
const addEnv = () => formData.envList.push({ key: '', value: '' });
const removeEnv = (i: number) => formData.envList.splice(i, 1);
const handleCancel = () => { emit('update:visible', false); testFeedback.status = 'none'; };

const handleTestConnection = async () => {
  isTestingConnection.value = true; testFeedback.status = 'none';
  try {
    const configData: McpCreateRequest = {
      name: formData.name, description: formData.description || null,
      transportType: formData.transportType, isEnabled: formData.isEnabled,
    };
    if (formData.transportType === 'stdio') {
      configData.command = formData.command;
      const args = formData.argsList.filter(a => a.trim());
      configData.args = args.length > 0 ? args : null;
      const env = formData.envList.filter(e => e.key.trim());
      configData.env = env.length > 0 ? env.reduce((acc, c) => { acc[c.key] = c.value; return acc; }, {} as Record<string, string>) : null;
    } else { configData.url = formData.url; }
    const resp = await mcpStore.testConnectionWithConfig(configData);
    testFeedback.status = resp.status === 'healthy' ? 'success' : 'error';
    testFeedback.shortMessage = resp.status === 'healthy' ? `OK (${resp.tools_count})` : 'Failed';
    testFeedback.message = resp.error || resp.message || '';
  } catch (e: any) {
    testFeedback.status = 'error'; testFeedback.shortMessage = 'Failed'; testFeedback.message = e.message || '';
  } finally { isTestingConnection.value = false; }
};

const handleSubmit = async () => {
  if (!formRef.value) return;
  await formRef.value.validate((valid) => {
    if (valid) {
      const data: McpCreateRequest = {
        name: formData.name, description: formData.description || null,
        transportType: formData.transportType, isEnabled: formData.isEnabled,
      };
      if (formData.transportType === 'stdio') {
        data.command = formData.command;
        const args = formData.argsList.filter(a => a.trim());
        data.args = args.length > 0 ? args : null;
        const env = formData.envList.filter(e => e.key.trim());
        data.env = env.length > 0 ? env.reduce((acc, c) => { acc[c.key] = c.value; return acc; }, {} as Record<string, string>) : null;
      } else { data.url = formData.url; }
      emit('save', data);
    }
  });
};
</script>

<style scoped>
.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0,0,0,0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 500px; max-height: 90vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0,0,0,0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); cursor: pointer; }
.sheet-body { flex: 1; overflow-y: auto; padding: 4px 16px 12px; -webkit-overflow-scrolling: touch; }
.sheet-divider { font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary); padding: 8px 0 4px; }

.field-item { margin-bottom: 12px; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 4px; }
.field-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }

.native-input { width: 100%; height: 40px; padding: 0 12px; font-size: 15px; font-family: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-input:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
.native-textarea { width: 100%; padding: 10px 12px; font-size: 14px; font-family: inherit; line-height: 1.5; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; resize: vertical; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-textarea:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }

.full-radio { display: flex; width: 100%; }
.full-radio :deep(.el-radio-button) { flex: 1; }
.full-radio :deep(.el-radio-button__inner) { width: 100%; }

.dynamic-list { display: flex; flex-direction: column; gap: 6px; }
.dynamic-row { display: flex; align-items: center; gap: 6px; }
.env-row .native-input { width: auto; }
.sep { font-weight: 700; color: var(--el-text-color-secondary); flex-shrink: 0; }
.chip-close-btn { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; border-radius: 50%; background: var(--el-fill-color-light); color: var(--el-color-danger); cursor: pointer; flex-shrink: 0; }
.add-row-btn { display: flex; align-items: center; justify-content: center; gap: 4px; width: 100%; height: 34px; font-size: 13px; color: var(--el-color-primary); background: var(--el-color-primary-light-9); border: 1px dashed var(--el-color-primary-light-5); border-radius: 8px; cursor: pointer; }

.test-section { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.test-btn { display: flex; align-items: center; justify-content: center; gap: 4px; height: 36px; padding: 0 16px; font-size: 13px; font-weight: 500; color: var(--el-color-primary); background: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-5); border-radius: 8px; cursor: pointer; }
.test-btn:active { background: var(--el-color-primary-light-7); }
.test-feedback { font-size: 12px; white-space: nowrap; }
.test-feedback.success { color: var(--el-color-success); }
.test-feedback.error { color: var(--el-color-danger); }

.sheet-footer { display: flex; gap: 10px; padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid rgba(0,0,0,0.08); flex-shrink: 0; }
.footer-btn { flex: 1; height: 44px; font-size: 15px; font-weight: 600; border: none; border-radius: 10px; cursor: pointer; transition: opacity 0.2s, transform 0.1s; }
.footer-btn-cancel { color: var(--el-text-color-primary); background: var(--el-fill-color-light); }
.footer-btn-confirm { color: #fff; background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); box-shadow: 0 4px 12px rgba(64,158,255,0.3); }
.footer-btn-confirm:disabled { opacity: 0.5; }
.footer-btn:active { transform: scale(0.98); }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }

@media (prefers-color-scheme: dark) {
  .sheet-handle { background: rgba(255,255,255,0.2); }
  .sheet-footer { border-top-color: rgba(255,255,255,0.08); }
  .native-input, .native-textarea { box-shadow: 0 0 0 1px rgba(255,255,255,0.1) inset; }
  .native-input:focus, .native-textarea:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
}
</style>
