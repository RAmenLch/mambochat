<!-- MobileBackendManagerPanel.vue — 移动端 Backend 管理（P4 重构） -->
<template>
  <div class="mobile-backend-panel">
    <div class="list-header">
      <span class="header-title">Backend</span>
      <div class="header-actions">
        <button class="header-btn" @click="handleShowPublicKey">
          <el-icon :size="16"><Key /></el-icon>
        </button>
        <button class="header-add-btn" @click="handleCreate">
          <el-icon :size="16"><Plus /></el-icon>
        </button>
      </div>
    </div>

    <div class="backend-list" v-loading="isLoading">
      <div v-if="backendList.length === 0" class="empty-state">
        <el-empty :description="$t('common.noData')" />
      </div>
      <div v-for="b in backendList" :key="b.id" class="backend-card">
        <div class="card-top">
          <span class="card-name">{{ b.name }}</span>
          <div class="card-tags">
            <span class="type-tag" :class="'tag-' + b.backendType">
              {{ typeLabel(b.backendType) }}
            </span>
            <span v-if="b.backendType === 'api' && clientStatusMap[b.id]" class="status-tag" :class="clientStatusMap[b.id]?.connected ? 'tag-online' : 'tag-offline'">
              <span class="status-dot"></span>
              {{ clientStatusMap[b.id]?.connected ? $t('backend.connected') : $t('backend.offline') }}
            </span>
          </div>
        </div>

        <div class="card-body">
          <template v-if="b.backendType === 'ssh'">
            <div class="info-row">{{ b.configData.username }}@{{ b.configData.hostname }}:{{ b.configData.port || 22 }}</div>
          </template>
          <template v-else-if="b.backendType === 'api'">
            <div class="info-row"><code>{{ b.id }}</code></div>
          </template>
          <template v-else-if="b.backendType === 'local'">
            <div class="info-row">{{ b.configData.root_dir || '~' }}</div>
          </template>
          <template v-else-if="b.backendType === 'resource'">
            <div class="info-row">{{ $t('backend.resource') }} {{ b.configData.resource_id }}</div>
          </template>
          <div class="info-row info-desc" v-if="b.description">{{ b.description }}</div>
        </div>

        <div class="card-footer">
          <button class="card-btn" @click="handleEdit(b)">{{ $t('common.action.edit') }}</button>
          <button class="card-btn" @click="handleDuplicate(b.id)">{{ $t('backend.duplicate') }}</button>
          <el-popconfirm :title="$t('common.msg.confirmDelete')" @confirm="handleDelete(b.id)">
            <template #reference>
              <button class="card-btn card-btn-danger">{{ $t('common.action.delete') }}</button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>

    <!-- Bottom Sheet: Backend 表单 -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="dialogVisible" class="sheet-overlay" @click="dialogVisible = false">
          <div class="sheet-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-header">
              <span class="sheet-title">{{ isEdit ? $t('backend.edit') : $t('backend.new') }}</span>
              <button class="sheet-close" @click="dialogVisible = false">
                <el-icon :size="20"><Close /></el-icon>
              </button>
            </div>
            <div class="sheet-body">
              <el-form ref="formRef" :model="form" :rules="currentRules" label-position="top">
                <div class="field-item">
                  <label class="field-label">{{ $t('backend.name') }}</label>
                  <input v-model="form.name" class="native-input" :placeholder="$t('backend.namePlaceholder')" />
                </div>
                <div class="field-item">
                  <label class="field-label">{{ $t('backend.description') }}</label>
                  <textarea v-model="form.description" class="native-textarea" :rows="2"></textarea>
                </div>
                <div class="field-item">
                  <label class="field-label">{{ $t('backend.type') }}</label>
                  <el-select v-model="form.backendType" :disabled="isEdit" style="width: 100%" @change="handleTypeChange" popper-class="mobile-popper">
                    <el-option :label="$t('backend.typeSsh')" value="ssh" />
                    <el-option :label="$t('backend.typeApi')" value="api" />
                    <el-option :label="$t('backend.typeResource')" value="resource" />
                    <el-option :label="$t('backend.typeLocal')" value="local" />
                  </el-select>
                </div>

                <!-- SSH -->
                <template v-if="form.backendType === 'ssh'">
                  <div class="sheet-divider">{{ $t('backend.sshConfig') }}</div>
                  <div class="field-item"><label class="field-label">Hostname</label><input v-model="form.configData.hostname" class="native-input" :placeholder="$t('backend.hostPlaceholder')" /></div>
                  <div class="field-item"><label class="field-label">Username</label><input v-model="form.configData.username" class="native-input" placeholder="root" /></div>
                  <div class="field-item"><label class="field-label">Port</label><el-input-number v-model="form.configData.port" :min="1" :max="65535" controls-position="right" style="width: 100%" /></div>
                  <div class="field-item">
                    <label class="field-label">Password</label>
                    <div class="password-row">
                      <input :type="showPwd ? 'text' : 'password'" v-model="form.configData.password" class="native-input" :placeholder="$t('backend.passwordPlaceholder')" />
                      <button class="toggle-key" @click="showPwd = !showPwd"><el-icon :size="16"><View v-if="!showPwd" /><Hide v-else /></el-icon></button>
                    </div>
                  </div>
                </template>

                <!-- API -->
                <template v-if="form.backendType === 'api'">
                  <div class="sheet-divider">{{ $t('backend.apiConfig') }}</div>
                  <div class="field-item"><label class="field-label">API Key</label><input v-model="form.configData.api_key" class="native-input" :placeholder="$t('backend.apiKeyPlaceholder')" /></div>
                  <div class="api-hint">
                    <el-alert type="info" :closable="false" show-icon>
                      <template #title>{{ $t('backend.apiClientHint') }}</template>
                    </el-alert>
                  </div>
                </template>

                <!-- Resource -->
                <template v-if="form.backendType === 'resource'">
                  <div class="sheet-divider">{{ $t('backend.resourceConfig') }}</div>
                  <div class="field-item">
                    <label class="field-label">Resource ID</label>
                    <el-select v-model="form.configData.resource_id" :placeholder="$t('backend.resourceIdPlaceholder')" filterable clearable style="width: 100%" popper-class="mobile-popper">
                      <el-option v-for="f in resourceFolderOptions" :key="f.id" :label="f.name" :value="f.id" />
                    </el-select>
                  </div>
                </template>

                <!-- Local -->
                <template v-if="form.backendType === 'local'">
                  <el-alert type="warning" :closable="false" show-icon style="margin-bottom:12px">
                    <template #title>{{ $t('backend.localWarning') }}</template>
                  </el-alert>
                  <div class="sheet-divider">{{ $t('backend.localConfig') }}</div>
                  <div class="field-item"><label class="field-label">Root Dir</label><input v-model="form.configData.root_dir" class="native-input" :placeholder="$t('backend.rootDirPlaceholder')" /></div>
                </template>

                <!-- 通用编辑权限 (SSH / Local / Resource) -->
                <template v-if="form.backendType !== 'api'">
                  <div class="sheet-divider">{{ $t('backend.editPermission') }}</div>
                  <div class="field-item">
                    <label class="field-label">{{ $t('backend.editMode') }}</label>
                    <el-radio-group v-model="editMode" size="small">
                      <el-radio-button value="whitelist">{{ $t('backend.whitelist') }}</el-radio-button>
                      <el-radio-button value="blacklist">{{ $t('backend.blacklist') }}</el-radio-button>
                    </el-radio-group>
                  </div>
                  <div class="field-item" v-if="editMode === 'whitelist'">
                    <label class="field-label">{{ $t('backend.whitelistLabel') }}</label>
                    <el-select v-model="whitelistProxy" multiple filterable allow-create default-first-option :placeholder="$t('backend.pathInputPlaceholder')" style="width: 100%" popper-class="mobile-popper" />
                  </div>
                  <div class="field-item" v-if="editMode === 'blacklist'">
                    <label class="field-label">{{ $t('backend.blacklistLabel') }}</label>
                    <el-select v-model="blacklistProxy" multiple filterable allow-create default-first-option :placeholder="$t('backend.pathInputPlaceholder')" style="width: 100%" popper-class="mobile-popper" />
                  </div>
                </template>

                <!-- 工具配置 -->
                <div class="sheet-divider">{{ $t('backend.toolConfig') }}</div>
                <div class="field-row">
                  <span class="field-label" style="margin-bottom:0">{{ $t('backend.executeLabel') }} {{ $t('backend.executeSubLabel') }}</span>
                  <el-switch v-model="form.tools_config!.execute.enabled" size="small" />
                </div>
                <div class="field-row" v-if="form.tools_config!.execute.enabled">
                  <span class="field-label" style="margin-bottom:0">{{ $t('backend.toolRequireReview') }}</span>
                  <el-switch v-model="form.tools_config!.execute.require_review" size="small" />
                </div>
              </el-form>

              <button v-if="form.backendType === 'ssh'" class="test-btn" @click="handleTestConnection" :disabled="isTesting">
                <el-icon v-if="isTesting" class="is-loading"><Loading /></el-icon>
                <el-icon v-else><Connection /></el-icon>
                <span>{{ $t('backend.testConnection') }}</span>
              </button>
            </div>

            <div class="sheet-footer">
              <button class="footer-btn footer-btn-cancel" @click="dialogVisible = false">{{ $t('common.action.cancel') }}</button>
              <button class="footer-btn footer-btn-confirm" @click="submitForm" :disabled="isSaving">{{ $t('common.action.confirm') }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Bottom Sheet: 公钥 -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="keyDialogVisible" class="sheet-overlay" @click="keyDialogVisible = false">
          <div class="sheet-panel sheet-key-panel" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-header">
              <span class="sheet-title">{{ $t('backend.systemPublicKey') }}</span>
              <button class="sheet-close" @click="keyDialogVisible = false">
                <el-icon :size="20"><Close /></el-icon>
              </button>
            </div>
            <div class="sheet-body">
              <p class="key-hint" v-html="$t('backend.publicKeyTip')"></p>
              <textarea v-model="systemPublicKey" class="native-textarea key-text" :rows="6" readonly></textarea>
            </div>
            <div class="sheet-footer">
              <button class="footer-btn footer-btn-cancel" @click="keyDialogVisible = false">{{ $t('common.action.close') }}</button>
              <button class="footer-btn footer-btn-confirm" @click="copyPublicKey" :disabled="!systemPublicKey">{{ $t('common.action.copy') }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { Plus, Key, Connection, Loading, Close, View, Hide } from '@element-plus/icons-vue';
import { useBackendStore } from '@/stores/backendStore';
import { useResourceStore } from '@/stores/resourceStore';
import { copyToClipboard } from '@/utils/clipboard';
import { getClientStatus } from '@/api/backendService';
import type { BackendConfig, BackendCreate, BackendType, SshConfigData, ApiConfigData, LocalConfigData, ResourceConfigData, SshTestRequest } from '@/api/types/backendTypes';
import { defaultToolsConfig } from '@/api/types/backendTypes';

const { t } = useI18n();
const backendStore = useBackendStore();
const resourceStore = useResourceStore();
const { backendList, isLoading, systemPublicKey } = storeToRefs(backendStore);
const { resources } = storeToRefs(resourceStore);

const dialogVisible = ref(false);
const keyDialogVisible = ref(false);
const isEdit = ref(false);
const isSaving = ref(false);
const isTesting = ref(false);
const showPwd = ref(false);
const currentEditId = ref<string | null>(null);
const editMode = ref<'whitelist' | 'blacklist'>('whitelist');
const whitelistProxy = ref<string[]>([]);
const blacklistProxy = ref<string[]>([]);

const formRef = ref<FormInstance>();
const clientStatusMap = ref<Record<string, { connected: boolean }>>({});
let statusPollTimer: ReturnType<typeof setInterval> | null = null;

const sshDefault = (): SshConfigData => ({ hostname: '', username: 'root', port: 22, password: null, root_dir: '/', edit_whitelist: [], edit_blacklist: [], ignore_dirs: ['.git', 'node_modules', 'build'] });
const apiDefault = (): ApiConfigData => ({ api_key: '', edit_whitelist: [], edit_blacklist: [] });
const localDefault = (): LocalConfigData => ({ root_dir: '~', edit_whitelist: [], edit_blacklist: [], ignore_dirs: ['.git', 'node_modules', '__pycache__'] });
const resourceDefault = (): ResourceConfigData => ({ resource_id: '', edit_whitelist: [], edit_blacklist: [], ignore_dirs: [], enable_version_editing: false });

const defaultForm = (type: BackendType = 'resource'): BackendCreate => ({
  name: '', description: '', backendType: type,
  configData: type === 'ssh' ? sshDefault() : type === 'api' ? apiDefault() : type === 'local' ? localDefault() : resourceDefault(),
  tools_config: defaultToolsConfig()
});

const form = reactive<BackendCreate>(defaultForm('resource'));

const resourceFolderOptions = computed(() => resources.value.filter(r => r.itemType === 'resource' && r.resourceType === 'folder'));

const typeLabel = (type: string) => ({ ssh: 'SSH', api: 'API', local: 'Local', resource: 'Resource' }[type] || type);

const NAME_UNSAFE_RE = /[\/\\\x00-\x1f\x7f]/;
const RESERVED_NAMES = new Set(['skills', 'memories', 'state', 'root', 'tmp', 'temp', 'workspace', 'this_chat_tmp', '.mambo']);

function validateName(_: any, value: string, cb: (e?: Error) => void) {
  if (!value) return cb(new Error(t('backend.nameRequired')));
  if (NAME_UNSAFE_RE.test(value)) return cb(new Error(t('backend.nameUnsafe')));
  if (value === '.' || value === '..') return cb(new Error(t('backend.nameDot')));
  if (RESERVED_NAMES.has(value.toLowerCase())) return cb(new Error(t('backend.nameReserved', { name: value })));
  cb();
}

const nameRules = computed(() => [{ required: true, message: t('backend.nameRequired'), trigger: 'blur' }, { validator: validateName, trigger: 'blur' }]);
const sshRules = computed<FormRules>(() => ({ name: nameRules.value, 'configData.hostname': [{ required: true, message: t('backend.hostRequired'), trigger: 'blur' }], 'configData.username': [{ required: true, message: t('backend.usernameRequired'), trigger: 'blur' }] }));
const apiRules = computed<FormRules>(() => ({ name: nameRules.value, 'configData.api_key': [{ required: true, message: t('backend.apiKeyRequired'), trigger: 'blur' }] }));
const localRules = computed<FormRules>(() => ({ name: nameRules.value }));
const resourceRules = computed<FormRules>(() => ({ name: nameRules.value, 'configData.resource_id': [{ required: true, message: t('backend.resourceIdRequired'), trigger: 'change' }] }));

const currentRules = computed(() => {
  if (form.backendType === 'ssh') return sshRules.value;
  if (form.backendType === 'api') return apiRules.value;
  if (form.backendType === 'resource') return resourceRules.value;
  return localRules.value;
});

// sync whitelist/blacklist proxies
watch(whitelistProxy, (v) => { (form.configData as any).edit_whitelist = [...v]; }, { deep: true });
watch(blacklistProxy, (v) => { (form.configData as any).edit_blacklist = [...v]; }, { deep: true });

const handleTypeChange = (type: BackendType) => {
  const nf = defaultForm(type); nf.name = form.name; nf.description = form.description;
  Object.assign(form, nf); formRef.value?.clearValidate();
  editMode.value = 'whitelist';
};

async function fetchClientStatuses() {
  for (const b of backendList.value) {
    if (b.backendType === 'api') {
      try { clientStatusMap.value[b.id] = await getClientStatus(b.id); }
      catch { clientStatusMap.value[b.id] = { connected: false }; }
    }
  }
}

onMounted(() => {
  backendStore.fetchBackends();
  resourceStore.initializeList();
  statusPollTimer = setInterval(fetchClientStatuses, 15000);
});
onUnmounted(() => { if (statusPollTimer) clearInterval(statusPollTimer); });

const handleCreate = () => {
  isEdit.value = false; currentEditId.value = null; showPwd.value = false;
  Object.assign(form, defaultForm('resource')); editMode.value = 'whitelist';
  whitelistProxy.value = []; blacklistProxy.value = [];
  dialogVisible.value = true; formRef.value?.clearValidate();
};

const handleEdit = (row: BackendConfig) => {
  isEdit.value = true; currentEditId.value = row.id; showPwd.value = false;
  const type = row.backendType;
  const cd = JSON.parse(JSON.stringify(row.configData));
  Object.assign(form, {
    name: row.name, description: row.description || '', backendType: type,
    configData: cd,
    tools_config: row.tools_config ? JSON.parse(JSON.stringify(row.tools_config)) : defaultToolsConfig(),
  });
  whitelistProxy.value = cd.edit_whitelist || [];
  blacklistProxy.value = cd.edit_blacklist || [];
  editMode.value = (cd.edit_whitelist && cd.edit_whitelist.length > 0) ? 'whitelist' : 'blacklist';
  dialogVisible.value = true; formRef.value?.clearValidate();
};

const handleDuplicate = async (id: string) => {
  try {
    await backendStore.duplicateBackendItem(id);
    ElMessage.success(t('common.msg.duplicateSuccess'));
  } catch { ElMessage.error(t('backend.duplicateFailed')); }
};

const handleDelete = async (id: string) => {
  try { await backendStore.removeBackend(id); ElMessage.success(t('common.msg.deleteSuccess')); }
  catch { ElMessage.error(t('backend.deleteFailed')); }
};

const handleTestConnection = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isTesting.value = true;
      try {
        const testData: SshTestRequest = {
          backend_id: isEdit.value ? currentEditId.value : null,
          configData: { ...form.configData, password: form.configData.password || null }
        };
        const res = await backendStore.testConnection(testData);
        ElMessage[res.success ? 'success' : 'error'](res.success ? t('backend.connectionSuccess') : t('backend.connectionFailed'));
      } catch (e: any) { ElMessage.error(e.message || t('backend.connectionError')); }
      finally { isTesting.value = false; }
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
        if (submitData.backendType !== 'api') {
          if (cd.edit_whitelist?.length === 0) cd.edit_whitelist = null;
          if (cd.edit_blacklist?.length === 0) cd.edit_blacklist = null;
        }
        if (submitData.backendType === 'ssh' && !cd.password) cd.password = null;
        if (submitData.backendType === 'api' && !cd.api_key) cd.api_key = null;

        if (isEdit.value && currentEditId.value) {
          await backendStore.updateExistingBackend(currentEditId.value, submitData);
          ElMessage.success(t('common.msg.updateSuccess'));
        } else {
          await backendStore.createNewBackend(submitData);
          ElMessage.success(t('common.msg.createSuccess'));
        }
        dialogVisible.value = false;
      } catch { ElMessage.error(isEdit.value ? t('backend.updateFailed') : t('common.msg.createFailed')); }
      finally { isSaving.value = false; }
    }
  });
};

const handleShowPublicKey = async () => {
  keyDialogVisible.value = true;
  if (!systemPublicKey.value) await backendStore.fetchPublicKey();
};

const copyPublicKey = async () => {
  if (systemPublicKey.value) { await copyToClipboard(systemPublicKey.value); ElMessage.success(t('common.msg.copySuccess')); }
};
</script>

<style scoped>
.mobile-backend-panel { height: 100%; display: flex; flex-direction: column; background: var(--color-background); }

.list-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; flex-shrink: 0;
  background: rgba(255,255,255,0.72); backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 0.5px solid rgba(0,0,0,0.08); z-index: 5;
}
.header-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.header-actions { display: flex; gap: 8px; }
.header-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; border-radius: 50%; background: var(--el-fill-color); color: var(--el-text-color-secondary); cursor: pointer; }
.header-add-btn { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; border-radius: 50%; background: var(--el-color-primary); color: #fff; cursor: pointer; }

.backend-list { flex: 1; overflow-y: auto; padding: 8px 12px; -webkit-overflow-scrolling: touch; }

.backend-card {
  background: var(--color-background-soft); border-radius: 12px; padding: 14px;
  margin-bottom: 10px; border: 0.5px solid rgba(0,0,0,0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.card-name { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.card-tags { display: flex; gap: 6px; }
.type-tag { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 4px; }
.tag-ssh { color: var(--el-color-info); background: var(--el-color-info-light-9); }
.tag-api { color: var(--el-color-success); background: var(--el-color-success-light-9); }
.tag-local { color: var(--el-color-danger); background: var(--el-color-danger-light-9); }
.tag-resource { color: var(--el-color-warning-dark-2); background: var(--el-color-warning-light-9); }
.status-tag { font-size: 11px; font-weight: 500; padding: 2px 7px; border-radius: 10px; display: flex; align-items: center; gap: 3px; }
.tag-online { color: var(--el-color-success); background: var(--el-color-success-light-9); }
.tag-offline { color: var(--el-color-danger); background: var(--el-color-danger-light-9); }
.status-dot { width: 5px; height: 5px; border-radius: 50%; }
.tag-online .status-dot { background: var(--el-color-success); }
.tag-offline .status-dot { background: var(--el-color-danger); }

.card-body { margin-bottom: 8px; }
.info-row { font-size: 13px; color: var(--el-text-color-regular); margin-bottom: 2px; word-break: break-all; }
.info-row code { font-size: 12px; font-family: monospace; }
.info-desc { color: var(--el-text-color-secondary); }

.card-footer { display: flex; justify-content: flex-end; gap: 6px; padding-top: 8px; border-top: 0.5px solid rgba(0,0,0,0.05); }
.card-btn { height: 28px; padding: 0 10px; font-size: 12px; font-weight: 500; color: var(--el-text-color-regular); background: var(--el-fill-color); border: none; border-radius: 14px; cursor: pointer; -webkit-tap-highlight-color: transparent; }
.card-btn:active { background: var(--el-fill-color-dark); }
.card-btn-danger { color: var(--el-color-danger); }

/* ===== Bottom Sheet ===== */
.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0,0,0,0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 500px; max-height: 90vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-key-panel { max-height: 60vh; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0,0,0,0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); cursor: pointer; }
.sheet-body { flex: 1; overflow-y: auto; padding: 4px 16px 12px; -webkit-overflow-scrolling: touch; }
.sheet-divider { font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary); padding: 8px 0 4px; }
.sheet-footer { display: flex; gap: 10px; padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid rgba(0,0,0,0.08); flex-shrink: 0; }
.footer-btn { flex: 1; height: 44px; font-size: 15px; font-weight: 600; border: none; border-radius: 10px; cursor: pointer; transition: opacity 0.2s, transform 0.1s; }
.footer-btn-cancel { color: var(--el-text-color-primary); background: var(--el-fill-color-light); }
.footer-btn-confirm { color: #fff; background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); box-shadow: 0 4px 12px rgba(64,158,255,0.3); }
.footer-btn-confirm:disabled { opacity: 0.5; }
.footer-btn:active { transform: scale(0.98); }

.field-item { margin-bottom: 12px; }
.field-label { display: block; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 4px; }
.field-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }
.native-input { width: 100%; height: 40px; padding: 0 12px; font-size: 15px; font-family: inherit; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-input:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
.native-textarea { width: 100%; padding: 10px 12px; font-size: 14px; font-family: inherit; line-height: 1.5; color: var(--el-text-color-primary); background: var(--el-bg-color); border: none; border-radius: 10px; box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset; outline: none; resize: vertical; box-sizing: border-box; transition: box-shadow 0.2s; }
.native-textarea:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
.password-row { position: relative; display: flex; align-items: center; }
.password-row .native-input { padding-right: 40px; }
.toggle-key { position: absolute; right: 8px; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; background: transparent; color: var(--el-text-color-secondary); cursor: pointer; border-radius: 6px; }
.api-hint { margin-bottom: 8px; }
.test-btn { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; height: 38px; margin-top: 8px; font-size: 13px; font-weight: 500; color: var(--el-color-info); background: var(--el-color-info-light-9); border: 1px solid var(--el-color-info-light-5); border-radius: 8px; cursor: pointer; }
.test-btn:active { background: var(--el-color-info-light-7); }
.key-hint { font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 10px; }
.key-hint code { background: var(--el-fill-color); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.key-text { font-family: monospace; font-size: 12px; }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }

@media (prefers-color-scheme: dark) {
  .list-header { background: rgba(30,30,30,0.72); border-bottom-color: rgba(255,255,255,0.08); }
  .backend-card { border-color: rgba(255,255,255,0.05); box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
  .sheet-handle { background: rgba(255,255,255,0.2); }
  .sheet-footer, .card-footer { border-color: rgba(255,255,255,0.08); }
  .native-input, .native-textarea { box-shadow: 0 0 0 1px rgba(255,255,255,0.1) inset; }
  .native-input:focus, .native-textarea:focus { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
}
</style>
