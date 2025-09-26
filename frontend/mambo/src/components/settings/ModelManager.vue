<template>
  <div class="model-manager">
    <!-- 头部区域：根据是否有服务商被选中来显示不同内容 -->
    <div class="header">
      <h2>模型 (Models)</h2>
      <el-button
        type="primary"
        @click="openAddModelDialog"
        :disabled="!selectedProvider"
      >
        <el-icon><Plus /></el-icon>
        新增模型
      </el-button>
    </div>

    <!-- 条件渲染：只有在选择了服务商后才显示表格 -->
    <div v-if="selectedProvider">
      <p class="provider-info">
        当前服务商: <strong>{{ selectedProvider.name }}</strong>
      </p>
      <el-table :data="selectedProvider.models" border style="width: 100%">
        <el-table-column prop="name" label="模型显示名称" width="200" />
        <el-table-column prop="modelId" label="模型 ID" />
        <el-table-column prop="id" label="数据库 ID" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDeleteModel(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <!-- 未选择服务商时的提示信息 -->
    <el-empty v-else description="请先在上方表格中点击选择一个服务商" />

    <!-- 新增模型的对话框 -->
    <el-dialog v-model="dialogVisible" title="新增 AI 模型" width="500">
      <el-form ref="formRef" :model="formModel" :rules="formRules" label-width="120px">
        <el-form-item label="模型显示名称" prop="name">
          <el-input v-model="formModel.name" placeholder="例如：GPT-4o" />
        </el-form-item>
        <el-form-item label="模型 ID" prop="modelId">
          <el-input v-model="formModel.modelId" placeholder="例如：gpt-4o" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleAddModel">
            确认
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { useProviderStore } from '@/stores/providerStore';
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus';
import { Plus } from '@element-plus/icons-vue';
import type { AIProviderWithModels, AIModel, AIModelCreate } from '@/api/types';

// 1. 定义 props
// 这个组件需要从父组件接收一个名为 selectedProvider 的 prop
const props = defineProps<{
  selectedProvider: AIProviderWithModels | null;
}>();

// 2. 初始化 Store
const providerStore = useProviderStore();

// 3. 对话框和表单逻辑
const dialogVisible = ref(false);
const formRef = ref<FormInstance>();
const formModel = reactive<Omit<AIModelCreate, 'providerId'>>({
  name: '',
  modelId: '',
});

const formRules = reactive<FormRules>({
  name: [{ required: true, message: '请输入模型显示名称', trigger: 'blur' }],
  modelId: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
});

const openAddModelDialog = () => {
  formRef.value?.resetFields();
  dialogVisible.value = true;
};

const handleAddModel = async () => {
  if (!formRef.value || !props.selectedProvider) return;
  await formRef.value.validate(async (valid) => {
    if (valid) {
      const modelData: AIModelCreate = {
        ...formModel,
        providerId: props.selectedProvider!.id, // 使用 selectedProvider 的 ID
      };
      try {
        await providerStore.addModel(modelData);
        ElMessage.success('新增模型成功！');
        dialogVisible.value = false;
      } catch (error) {
        ElMessage.error('新增模型失败，请检查控制台。');
      }
    }
  });
};

// 处理删除模型
const handleDeleteModel = async (model: AIModel) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除模型 "${model.name}" 吗？`,
      '警告',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    );
    await providerStore.removeModel(model.id);
    ElMessage.success('删除模型成功！');
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除模型失败，请检查控制台。');
    }
  }
};
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.header h2 {
  margin: 0;
  font-size: 20px;
}
.provider-info {
  margin-bottom: 16px;
  font-size: 14px;
  color: #606266;
}
</style>
