<template>
  <div v-if="formattedUsageText" class="usage-info">
    {{ formattedUsageText }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { SubMessage } from '@/api/types';

const { t } = useI18n();

/**
 * 定义了 completion_tokens 的详细分类。
 */
interface CompletionTokensDetails {
  reasoning_tokens?: number;
  image_tokens?: number;
}

/**
 * 定义从 usage sub-message 的 content 字段中解析出的数据结构。
 */
interface UsageData {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  completion_tokens_details?: CompletionTokensDetails;
  [key: string]: unknown; // 允许其他未知字段
}

const props = defineProps<{
  usageSubMessage: SubMessage;
}>();

/**
 * 安全地解析 usage sub-message 的 JSON 内容。
 * @returns 解析后的 UsageData 对象，如果解析失败则返回空对象。
 */
const parsedUsage = computed<UsageData>(() => {
  try {
    if (props.usageSubMessage.content) {
      return JSON.parse(props.usageSubMessage.content) as UsageData;
    }
  } catch (error) {
    console.error('Failed to parse usage info JSON:', error);
  }
  return {};
});

/**
 * 将解析后的 usage 数据格式化为用户友好的显示字符串。
 * 例如: "Prompt: 7 | Completion: 98 (Reasoning: 5) | Total: 105"
 */
const formattedUsageText = computed<string>(() => {
  const usage = parsedUsage.value;
  const mainParts: string[] = [];

  // 1. Prompt Tokens
  if (typeof usage.prompt_tokens === 'number') {
    mainParts.push(`${t('usage.prompt')}: ${usage.prompt_tokens}`);
  }

  // 2. Completion Tokens with Details
  if (typeof usage.completion_tokens === 'number') {
    const detailParts: string[] = [];
    const details = usage.completion_tokens_details;

    if (details) {
      if (typeof details.reasoning_tokens === 'number' && details.reasoning_tokens > 0) {
        detailParts.push(`${t('usage.reasoning')}: ${details.reasoning_tokens}`);
      }
      if (typeof details.image_tokens === 'number' && details.image_tokens > 0) {
        detailParts.push(`Image: ${details.image_tokens}`);
      }
    }

    let completionString = `${t('usage.completion')}: ${usage.completion_tokens}`;
    if (detailParts.length > 0) {
      completionString += ` (${detailParts.join(', ')})`;
    }
    mainParts.push(completionString);
  }

  // 3. Total Tokens
  if (typeof usage.total_tokens === 'number') {
    mainParts.push(`${t('usage.total')}: ${usage.total_tokens}`);
  }

  return mainParts.join(' | ');
});
</script>

<style scoped>
.usage-info {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  user-select: none;
}
</style>
