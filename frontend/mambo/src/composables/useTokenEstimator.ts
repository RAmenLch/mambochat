// frontend/mambo/src/composables/useTokenEstimator.ts

import { ref, watch } from 'vue';
import type { Ref } from 'vue';
import { debounce } from 'lodash-es';

interface UseTokenEstimatorReturn {
  estimatedTokens: Ref<number>;
}

// 定义 tokenizer 模块的类型
type TokenizerModule = {
  encode: (text: string) => number[];
};

const base64ImageRegex = /!\[(.*?)\]\((data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+)\)/g;

export function useTokenEstimator(
  contextText: Ref<string>,
  currentUserInput: Ref<string>,
  debounceMs = 300
): UseTokenEstimatorReturn {
  const estimatedTokens = ref(0);

  // 缓存模块，避免重复下载
  let tokenizerModule: TokenizerModule | null = null;
  let isLoading = false;

  const estimate = async (context: string, currentInput: string) => {
    const fullText = [context, currentInput].filter(Boolean).join('\n');

    if (!fullText) {
      estimatedTokens.value = 0;
      return;
    }

    // 动态加载逻辑
    if (!tokenizerModule) {
      if (isLoading) return; // 防止并发请求
      isLoading = true;
      try {
        // ✅ 关键点：只有执行到这里，浏览器才会去下载 gpt-tokenizer-xxxx.js
        // 配合 vite.config.ts 的 manualChunks，这会是一个独立的文件
        tokenizerModule = await import('gpt-tokenizer');
      } catch (error) {
        console.error('Failed to load gpt-tokenizer:', error);
        return;
      } finally {
        isLoading = false;
      }
    }

    try {
      const sanitizedText = fullText.replace(base64ImageRegex, '![image]');
      if (tokenizerModule) {
        estimatedTokens.value = tokenizerModule.encode(sanitizedText).length;
      }
    } catch (e) {
      console.error('Token estimation failed:', e);
      estimatedTokens.value = 0;
    }
  };

  const debouncedEstimate = debounce(estimate, debounceMs);

  watch([contextText, currentUserInput], ([newContext, newCurrentInput]) => {
    debouncedEstimate(newContext, newCurrentInput);
  }, {
    immediate: true,
  });

  return {
    estimatedTokens,
  };
}
