<!-- frontend/mambo/src/components/common/EntityFormDialog.vue -->
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

      <el-form-item v-if="showChatMode" :label="t('chat.settings.chatMode')" prop="chatMode">
        <el-select v-model="form.chatMode" style="width: 100%;">
          <el-option :label="t('chat.settings.normalMode')" value="normal" />
          <el-option :label="t('chat.settings.agentMode')" value="agent" />
        </el-select>
      </el-form-item>

      <el-form-item
        v-if="selectConfig && form.chatMode === 'normal'"
        :label="selectConfig.label"
        prop="selectValue"
      >
        <el-select
          ref="modelSelectRef"
          v-model="form.selectValue"
          :placeholder="t('common.placeholder.select', { label: selectConfig.label })"
          style="width: 100%;"
          @visible-change="(visible: boolean) => scrollToTopIfStarred(visible, modelSelectRef)"
        >
          <template v-for="(item, index) in selectConfig.options" :key="index">
            <el-option-group v-if="'options' in item" :label="item.label">
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

      <el-form-item
        v-if="agentSelectConfig && form.chatMode === 'agent'"
        :label="agentSelectConfig.label"
        prop="agentId"
      >
        <el-select
          v-model="form.agentId"
          :placeholder="t('common.placeholder.select', { label: agentSelectConfig.label })"
          style="width: 100%;"
        >
          <el-option
            v-for="opt in agentSelectConfig.options"
            :key="(opt as SelectOptionItem).value"
            :label="(opt as SelectOptionItem).label"
            :value="(opt as SelectOptionItem).value"
          />
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

export interface ConfirmPayload {
  name: string;
  selectValue?: string;
  chatMode?: 'normal' | 'agent';
  agentId?: string;
}

const props = defineProps<{
  visible: boolean;
  title: string;
  nameLabel?: string;
  initialName?: string;
  selectConfig?: SelectConfig;
  showChatMode?: boolean;
  agentSelectConfig?: SelectConfig;
  selectStarredIds?: Set<string>;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', payload: ConfirmPayload): void;
}>();

const { t } = useI18n();
const internalVisible = ref(false);
const formRef = ref<FormInstance>();
const nameInputRef = ref<HTMLInputElement>();
const modelSelectRef = ref();

function scrollToTopIfStarred(visible: boolean, selectRef: any) {
  if (!visible || !selectRef || !props.selectStarredIds) return;
  const value = selectRef.modelValue as string | null;
  if (!value || !props.selectStarredIds.has(value)) return;

  setTimeout(() => {
    try {
      const popperContentRef = selectRef.tooltipRef?.popperRef?.contentRef;
      if (!popperContentRef) return;
      const wrapEl = popperContentRef.querySelector('.el-select-dropdown__wrap');
      if (wrapEl) wrapEl.scrollTop = 0;
    } catch { /* ignore */ }
  }, 0);
}

const form = reactive({
  name: '',
  selectValue: '',
  chatMode: 'normal' as 'normal' | 'agent',
  agentId: '',
});

const rules = reactive<FormRules>({
  name: [{ required: true, message: t('common.rule.nameRequired'), trigger: 'blur' }],
});

const initFormData = () => {
  form.name = props.initialName || '';
  form.chatMode = 'normal';

  if (props.selectConfig) {
    if (props.selectConfig.initialValue) {
      form.selectValue = props.selectConfig.initialValue;
    } else {
      const firstItem = props.selectConfig.options[0];
      if (firstItem) {
        if ('options' in firstItem && firstItem.options.length > 0) {
          form.selectValue = firstItem.options[0].value;
        } else if ('value' in firstItem) {
          form.selectValue = (firstItem as SelectOptionItem).value;
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

  if (props.agentSelectConfig) {
    if (props.agentSelectConfig.initialValue) {
      form.agentId = props.agentSelectConfig.initialValue;
    } else if (props.agentSelectConfig.options.length > 0) {
      const first = props.agentSelectConfig.options[0];
      if ('value' in first) form.agentId = (first as SelectOptionItem).value;
    } else {
      form.agentId = '';
    }
  } else {
    form.agentId = '';
  }

  nextTick(() => {
    formRef.value?.clearValidate();
    nameInputRef.value?.focus();
  });
};

watch(() => props.visible, (val) => {
  internalVisible.value = val;
  if (val) {
    initFormData();
  }
}, { immediate: true });

watch(internalVisible, (val) => {
  emit('update:visible', val);
});

const handleClose = () => {
  internalVisible.value = false;
};

const handleConfirm = async () => {
  if (!formRef.value) return;

  await formRef.value.validate((valid) => {
    if (valid) {
      if (form.chatMode === 'normal' && props.selectConfig && !form.selectValue) {
        ElMessage.warning(t('common.rule.selectRequired'));
        return;
      }
      if (form.chatMode === 'agent' && props.agentSelectConfig && !form.agentId) {
        ElMessage.warning(t('common.rule.selectRequired'));
        return;
      }

      const payload: ConfirmPayload = {
        name: form.name.trim(),
        chatMode: form.chatMode,
      };

      if (form.chatMode === 'normal' && props.selectConfig) {
        payload.selectValue = form.selectValue;
      }
      if (form.chatMode === 'agent' && props.agentSelectConfig) {
        payload.agentId = form.agentId;
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
