<template>
  <el-container class="settings-container">
    <el-header class="settings-header">
      <h1>AI 模型配置</h1>
      <router-link to="/chat">
        <el-button type="primary">返回聊天</el-button>
      </router-link>
    </el-header>

    <el-main class="settings-main">
      <el-scrollbar>
        <div class="settings-content">
          <!-- 【修改点 1】: 监听子组件发出的 provider-selected 事件 -->
          <ProviderManager @provider-selected="handleProviderSelect" />

          <el-divider />

          <!-- 【修改点 2】: 将选中的服务商数据通过 prop 传递给子组件 -->
          <ModelManager :selected-provider="selectedProvider" />
        </div>
      </el-scrollbar>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useProviderStore } from '@/stores/providerStore';
import ProviderManager from '@/components/settings/ProviderManager.vue';
import ModelManager from '@/components/settings/ModelManager.vue';
import type { AIProviderWithModels } from '@/api/types';

// 1. 初始化 store 并获取 providers 数组的响应式引用
const providerStore = useProviderStore();
const { providers } = storeToRefs(providerStore);

// 2. 定义一个 ref 来存储当前选中的服务商
const selectedProvider = ref<AIProviderWithModels | null>(null);

// 3. 定义事件处理函数，当子组件发出事件时，更新 selectedProvider 的值
const handleProviderSelect = (provider: AIProviderWithModels) => {
  selectedProvider.value = provider;
};

// 4. 【核心修复】添加一个侦听器
// 这个侦听器会监视 store 中的 providers 数组
watch(providers, (newProviders) => {
  // 如果 providers 数组更新了，并且我们当前有一个选中的 provider
  if (selectedProvider.value) {
    // 就在新的 providers 数组中，根据 id 找到这个 provider 的最新状态
    const updatedProvider = newProviders.find(p => p.id === selectedProvider.value!.id);

    // 用最新的 provider 对象来更新我们本地的 selectedProvider
    // 如果 provider 本身被删了，find 会返回 undefined，这里会安全地设置为 null
    selectedProvider.value = updatedProvider || null;
  }
}, {
  // deep: true 可以在数组内部对象变化时也触发，增加健壮性
  deep: true
});

</script>

<style scoped>
/* ... 样式保持不变 ... */
.settings-container { height: 100vh; background-color: #f0f2f5; }
.settings-header { display: flex; justify-content: space-between; align-items: center; background-color: #ffffff; border-bottom: 1px solid #dcdfe6; }
.settings-main { padding: 20px; }
.settings-content { max-width: 1200px; margin: 0 auto; background-color: #ffffff; padding: 24px; border-radius: 8px; }
</style>
