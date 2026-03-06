<!-- frontend/mambo/src/components/settings/dialogs/SkillFormDialog.vue -->
<template>
  <el-dialog :model-value="visible" :title="t('resource.tree.newSkill')" width="500px" @update:model-value="$emit('update:visible', $event)">
    <el-form :model="form" label-position="top" ref="formRef">
      <el-form-item :label="t('resource.meta.name')" prop="name" :rules="[{ required: true, message: 'Name is required' }]">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('resource.meta.description')" prop="description">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="handleConfirm">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits(['update:visible', 'confirm'])

const { t } = useI18n()
const form = ref({ name: '', description: '' })

const handleConfirm = () => {
  emit('confirm', { ...form.value })
  form.value = { name: '', description: '' } // Reset
}
</script>
