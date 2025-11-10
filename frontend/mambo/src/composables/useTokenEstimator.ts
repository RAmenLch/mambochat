// frontend/mambo/src/composables/useTokenEstimator.ts

import { ref, watch } from 'vue';
import type { Ref } from 'vue';
import { encode } from 'gpt-tokenizer';
import { debounce } from 'lodash-es';

/**
 * useTokenEstimator 的返回值类型。
 */
interface UseTokenEstimatorReturn {
  /** 响应式的引用，表示当前估算的 token 数量。 */
  estimatedTokens: Ref<number>;
}

// 正则表达式，用于匹配 Base64 图片的 Markdown 语法
// 我们用它来移除 Base64 数据，避免将其传入 tokenizer
const base64ImageRegex = /!\[(.*?)\]\((data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+)\)/g;

/**
 * 创建一个响应式的 Token 估算器。
 * 它会监视输入的文本内容（包括上下文和当前用户输入），并在内容变化时
 * (经过防抖处理后) 异步计算 token 数量。
 *
 * @param contextText - 一个响应式的 Ref，包含历史消息等上下文内容。
 * @param currentUserInput - 一个响应式的 Ref，包含用户当前正在输入的内容。
 * @param debounceMs - 防抖延迟时间，单位为毫秒。默认为 300ms。
 * @returns 返回一个包含 `estimatedTokens` Ref 的对象。
 */
export function useTokenEstimator(
  contextText: Ref<string>,
  currentUserInput: Ref<string>,
  debounceMs = 300
): UseTokenEstimatorReturn {
  const estimatedTokens = ref(0);

  const estimate = (context: string, currentInput: string) => {
    const fullText = [context, currentInput].filter(Boolean).join('\n');
    if (!fullText) {
      estimatedTokens.value = 0;
      return;
    }

    try {
      // 在进行 tokenization 之前，先移除巨大的 Base64 数据，
      // 替换为一个简短的占位符，以防止主线程阻塞。
      // '![image]' 本身也会消耗 token，所以这是一个合理的近似。
      const sanitizedText = fullText.replace(base64ImageRegex, '![image]');

      // gpt-tokenizer 是同步的，但我们通过防抖使其行为表现为异步更新
      estimatedTokens.value = encode(sanitizedText).length;
    } catch (e) {
      console.error('Token estimation failed:', e);
      estimatedTokens.value = 0;
    }
  };

  const debouncedEstimate = debounce(estimate, debounceMs);

  // 监视两个输入源的变化
  watch([contextText, currentUserInput], ([newContext, newCurrentInput]) => {
    debouncedEstimate(newContext, newCurrentInput);
  }, {
    immediate: true, // 初始加载时立即执行一次估算
  });

  return {
    estimatedTokens,
  };
}
