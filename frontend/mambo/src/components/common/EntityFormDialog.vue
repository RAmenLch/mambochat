<template>
  <el-dialog
    v-model="internalVisible"
    :title="title"
    width="400px"
    @close="handleClose"
    @open="handleOpen"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
      <el-form-item :label="nameLabel" prop="name">
        <el-input
          v-model="form.name"
          :placeholder="`请输入${nameLabel}`"
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
          :placeholder="`请选择${selectConfig.label}`"
          style="width: 100%;"
        >
          <!-- 修复点：支持分组渲染 -->
          <template v-for="(item, index) in selectConfig.options" :key="index">
            <!-- 如果是分组 (拥有 options 属性) -->
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

            <!-- 如果是普通选项 -->
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
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleConfirm">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch, nextTick } from 'vue';
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

// 联合类型：配置项可以是普通选项，也可以是分组
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

const internalVisible = ref(false);
const formRef = ref<FormInstance>();
const nameInputRef = ref<HTMLInputElement>();

const form = reactive({
  name: '',
  selectValue: '',
});

const rules = reactive<FormRules>({
  name: [{ required: true, message: '名称不能为空', trigger: 'blur' }],
  selectValue: [{ required: true, message: '请选择一项', trigger: 'change' }],
});

// --- Watchers ---

watch(() => props.visible, (val) => {
  internalVisible.value = val;
});

watch(internalVisible, (val) => {
  emit('update:visible', val);
});

// --- Handlers ---

const handleOpen = () => {
  form.name = props.initialName || '';

  if (props.selectConfig) {
    if (props.selectConfig.initialValue) {
      form.selectValue = props.selectConfig.initialValue;
    } else {
      // 尝试自动选中第一个可用选项
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

  nextTick(() => {
    formRef.value?.clearValidate();
    nameInputRef.value?.focus();
  });
};

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
        ElMessage.warning('名称不能为空');
      }
    }
  });
};
</script>
