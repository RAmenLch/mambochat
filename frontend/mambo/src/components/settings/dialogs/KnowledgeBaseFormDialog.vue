<!-- frontend/mambo/src/components/settings/dialogs/KnowledgeBaseFormDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="$t('kb.form.createTitle')"
    width="500px"
    @update:model-value="(val: boolean) => emit('update:visible', val)"
    @close="handleClose"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item :label="$t('kb.form.nameLabel')" prop="name">
        <el-input
          v-model="form.name"
          :placeholder="$t('kb.form.namePlaceholder')"
          ref="nameInputRef"
          @keyup.enter="handleConfirm"
        />
      </el-form-item>

      <el-form-item :label="$t('kb.form.modelLabel')" prop="embeddingModelId">
        <el-select
          v-model="form.embeddingModelId"
          :placeholder="$t('kb.form.modelPlaceholder')"
          style="width: 100%"
          :no-data-text="$t('kb.form.noModel')"
        >
          <template v-for="group in embeddingModelOptions" :key="group.label">
            <el-option-group :label="group.label">
              <el-option
                v-for="item in group.options"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-option-group>
          </template>
        </el-select>
      </el-form-item>

      <el-form-item prop="embeddingRateLimit">
        <template #label>
          <span>{{ $t('kb.form.rateLimitLabel') }}</span>
          <el-tooltip :content="$t('kb.form.rateLimitTooltip')" placement="top">
            <el-icon class="label-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <el-input-number
          v-model="form.embeddingRateLimit"
          :min="0"
          :step="0.1"
          :precision="2"
          style="width: 100%"
          :placeholder="$t('kb.form.rateLimitPlaceholder')"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">{{ $t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="handleConfirm">{{ $t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, watch, computed } from 'vue';
import { type FormInstance, type FormRules, ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';

// --- Types ---

export interface ModelOption {
  label: string;
  value: string;
}

export interface ModelGroup {
  label: string;
  options: ModelOption[];
}

export interface KBConfirmPayload {
  name: string;
  embeddingModelId: string;
  embeddingRateLimit: number;
}

// --- Props & Emits ---

const props = withDefaults(defineProps<{
  visible: boolean;
  embeddingModelOptions: ModelGroup[];
  initialName?: string;
}>(), {
  initialName: ''
});

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', payload: KBConfirmPayload): void;
}>();

// --- State ---

const { t } = useI18n();
const formRef = ref<FormInstance>();
const nameInputRef = ref<HTMLInputElement>();

const form = reactive({
  name: '',
  embeddingModelId: '',
  embeddingRateLimit: 0,
});

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('kb.form.rule.nameRequired'), trigger: 'blur' }],
  embeddingModelId: [{ required: true, message: t('kb.form.rule.modelRequired'), trigger: 'change' }],
}));

// --- Methods ---

/**
 * 尝试自动选中第一个可用的模型
 */
const tryAutoSelectModel = () => {
  // 如果已经选中了有效值，就不再自动覆盖
  if (form.embeddingModelId) return;

  if (props.embeddingModelOptions && props.embeddingModelOptions.length > 0) {
    // 遍历所有分组，找到第一个包含选项的分组
    for (const group of props.embeddingModelOptions) {
      if (group.options && group.options.length > 0) {
        form.embeddingModelId = group.options[0].value;
        return;
      }
    }
  }
};

/**
 * 初始化表单数据
 */
const initForm = () => {
  // 1. 设置默认名称，如果 props 未提供则使用 i18n 默认值
  form.name = props.initialName || t('kb.form.createTitle');
  form.embeddingRateLimit = 0;

  // 2. 重置模型选择
  form.embeddingModelId = '';

  // 3. 尝试自动选择模型 (处理数据已加载的情况)
  tryAutoSelectModel();

  // 4. 重置校验并聚焦
  nextTick(() => {
    formRef.value?.clearValidate();
    nameInputRef.value?.focus();
  });
};

// --- Watchers ---

// 1. 监听 visible 变化来触发初始化
// 使用 immediate: true 确保组件首次挂载且 visible 为 true 时也能执行初始化
watch(() => props.visible, (val) => {
  if (val) {
    initForm();
  }
}, { immediate: true });

// 2. 监听选项数据变化
// 处理异步数据加载：当弹窗已打开但数据还没回来时，数据回来后自动补选
watch(() => props.embeddingModelOptions, () => {
  if (props.visible) {
    tryAutoSelectModel();
  }
}, { deep: true });

// --- Handlers ---

const handleClose = () => {
  emit('update:visible', false);
};

const handleConfirm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate((valid) => {
    if (valid) {
      emit('confirm', {
        name: form.name.trim(),
        embeddingModelId: form.embeddingModelId,
        embeddingRateLimit: form.embeddingRateLimit,
      });
      handleClose();
    } else {
      if (!form.name.trim()) {
        ElMessage.warning(t('kb.form.rule.checkInput'));
      }
    }
  });
};
</script>

<style scoped>
.label-icon {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  cursor: help;
  vertical-align: middle;
}
</style>
