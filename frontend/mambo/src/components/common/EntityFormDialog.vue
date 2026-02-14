<template>
  <el-dialog
    v-model="internalVisible"
    :title="title"
    width="400px"
    @close="handleClose"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
      <el-form-item :label="nameLabel" prop="name">
        <el-input
          v-model="form.name"
          :placeholder="t('common.placeholder.enter', { label: nameLabel })"
          @keyup.enter="handleConfirm"
          ref="nameInputRef"
        />
      </el-form-item>

      <el-form-item
        v-if="selectConfig"
        :label="selectConfig.label"
        prop="selectValue"
      >
        <el-select
          v-model="form.selectValue"
          :placeholder="t('common.placeholder.select', { label: selectConfig.label })"
          style="width: 100%;"
        >
          <template v-for="(item, index) in selectConfig.options" :key="index">
            <el-option-group
              v-if="'options' in item"
              :label="item.label"
            >
              <el-option
                v-for="opt in (item as SelectGroupItem).options"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-option-group>

            <el-option
              v-else
              :label="(item as SelectOptionItem).label"
              :value="(item as SelectOptionItem).value"
            />
          </template>
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="handleConfirm">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { type FormInstance, type FormRules, ElMessage } from 'element-plus';

// --- Types ---

export interface SelectOptionItem {
  label: string;
  value: string;
}

export interface SelectGroupItem {
  label: string;
  options: SelectOptionItem[];
}

export type SelectConfigOption = SelectOptionItem | SelectGroupItem;

interface SelectConfig {
  label: string;
  options: SelectConfigOption[];
  initialValue?: string;
}

interface ConfirmPayload {
  name: string;
  selectValue?: string;
}

// --- Props & Emits ---

const props = defineProps<{
  visible: boolean;
  title: string;
  nameLabel?: string;
  initialName?: string;
  selectConfig?: SelectConfig;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', payload: ConfirmPayload): void;
}>();

// --- State ---

const { t } = useI18n();
const internalVisible = ref(false);
const formRef = ref<FormInstance>();
const nameInputRef = ref<HTMLInputElement>();

const form = reactive({
  name: '',
  selectValue: '',
});

const rules = reactive<FormRules>({
  name: [{ required: true, message: t('common.rule.nameRequired'), trigger: 'blur' }],
  selectValue: [{ required: true, message: t('common.rule.selectRequired'), trigger: 'change' }],
});

// --- Methods ---

/**
 * 初始化表单数据
 */
const initFormData = () => {
  // 1. 设置名称
  form.name = props.initialName || '';

  // 2. 处理下拉选择框初始值
  if (props.selectConfig) {
    if (props.selectConfig.initialValue) {
      form.selectValue = props.selectConfig.initialValue;
    } else {
      const firstItem = props.selectConfig.options[0];
      if (firstItem) {
        if ('options' in firstItem && firstItem.options.length > 0) {
          form.selectValue = firstItem.options[0].value;
        } else if ('value' in firstItem) {
          form.selectValue = firstItem.value;
        } else {
          form.selectValue = '';
        }
      } else {
        form.selectValue = '';
      }
    }
  } else {
    form.selectValue = '';
  }

  // 3. 清除校验并聚焦
  // 使用 nextTick 确保 DOM 已更新
  nextTick(() => {
    formRef.value?.clearValidate();
    nameInputRef.value?.focus();
  });
};

// --- Watchers ---

watch(() => props.visible, (val) => {
  internalVisible.value = val;
  // 当 visible 变为 true 时，立即初始化表单数据
  // 配合 immediate: true，即使组件挂载时 visible 已经是 true，也会执行初始化
  if (val) {
    initFormData();
  }
}, { immediate: true }); // [重要] 必须保留 immediate: true

watch(internalVisible, (val) => {
  emit('update:visible', val);
});

// --- Handlers ---

const handleClose = () => {
  internalVisible.value = false;
};

const handleConfirm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate((valid) => {
    if (valid) {
      const payload: ConfirmPayload = {
        name: form.name.trim(),
      };

      if (props.selectConfig) {
        payload.selectValue = form.selectValue;
      }

      emit('confirm', payload);
      handleClose();
    } else {
      if (!form.name.trim()) {
        ElMessage.warning(t('common.rule.nameRequired'));
      }
    }
  });
};
</script>
