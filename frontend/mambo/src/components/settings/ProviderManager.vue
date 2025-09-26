<template>
  <div class="provider-manager">
    <div class="header">
      <h2>服务商 (Providers)</h2>
      <el-button type="primary" @click="openAddDialog">
        <el-icon><Plus /></el-icon>
        新增服务商
      </el-button>
    </div>

    <!-- 【修改点 1】: 新增 highlight-current-row 和 @row-click 事件监听 -->
    <el-table
      :data="providers"
      v-loading="isLoading"
      border
      style="width: 100%"
      highlight-current-row
      @row-click="handleRowClick"
    >
      <el-table-column prop="name" label="服务商名称" width="180" />
      <el-table-column prop="apiHost" label="API Host" />
      <el-table-column prop="id" label="服务商 ID" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button link type="danger" @click.stop="handleDeleteProvider(row)">
            <!-- 【修改点 2】: 给删除按钮添加 .stop 修饰符，防止点击删除时触发 row-click -->
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增 AI 服务商" width="500">
      <!-- ... 对话框内容保持不变 ... -->
      <el-form ref="formRef" :model="formModel" :rules="formRules" label-width="100px">
        <el-form-item label="服务商名称" prop="name">
          <el-input v-model="formModel.name" placeholder="例如：OpenAI" />
        </el-form-item>
        <el-form-item label="API Host" prop="apiHost">
          <el-input v-model="formModel.apiHost" placeholder="例如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key" prop="apiKey">
          <el-input v-model="formModel.apiKey" type="password" show-password placeholder="请输入您的 API Key" />
        </el-form-item>
        <el-form-item label="自定义 ID" prop="id">
          <el-input v-model="formModel.id" placeholder="(可选) 例如：openai" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleAddProvider">
            确认
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { useProviderStore } from '@/stores/providerStore';
import { storeToRefs } from 'pinia';
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import type { AIProvider, AIProviderCreate, AIProviderWithModels } from '@/api/types';

// 【修改点 3】: 定义组件要发出的事件
const emit = defineEmits(['provider-selected']);

const providerStore = useProviderStore();
const { providers, isLoading } = storeToRefs(providerStore);

onMounted(() => {
  providerStore.fetchProviders();
});

// ... 对话框和表单逻辑保持不变 ...
const dialogVisible = ref(false);
const formRef = ref<FormInstance>();
const formModel = reactive<AIProviderCreate>({ name: '', apiHost: '', apiKey: '', id: null });
const formRules = reactive<FormRules<AIProviderCreate>>({ name: [{ required: true, message: '请输入服务商名称', trigger: 'blur' }], apiHost: [{ required: true, message: '请输入 API Host', trigger: 'blur' }], apiKey: [{ required: true, message: '请输入 API Key', trigger: 'blur' }] });
const openAddDialog = () => { formRef.value?.resetFields(); formModel.id = null; dialogVisible.value = true; };
const handleAddProvider = async () => { if (!formRef.value) return; await formRef.value.validate(async (valid) => { if (valid) { try { await providerStore.addProvider(formModel); ElMessage.success('新增成功！'); dialogVisible.value = false; } catch (error) { ElMessage.error('新增失败，请检查控制台错误信息。'); } } }); };
const handleDeleteProvider = async (provider: AIProvider) => { try { await ElMessageBox.confirm(`确定要删除服务商 "${provider.name}" 吗？其下所有模型也将被一并删除。`, '警告', { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }); await providerStore.removeProvider(provider.id); ElMessage.success('删除成功！'); } catch (error) { if (error !== 'cancel') { ElMessage.error('删除失败，请检查控制台错误信息。'); } } };

// 【修改点 4】: 新增行点击事件处理函数
const handleRowClick = (row: AIProviderWithModels) => {
  // 发出 'provider-selected' 事件，并把当前行的数据作为参数传递出去
  emit('provider-selected', row);
};
</script>

<style scoped>
/* ... 样式保持不变 ... */
.provider-manager { margin-bottom: 20px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header h2 { margin: 0; font-size: 20px; }
</style>
