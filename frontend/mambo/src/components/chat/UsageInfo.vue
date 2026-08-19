<template>
  <div v-if="hasUsage" class="usage-info">
    <!-- 模式1: 配置了最大上下文 -> 环形饼图 -->
    <el-tooltip v-if="useDonutMode" placement="top" :show-after="300">
      <template #content>
        <div class="usage-tooltip">
          <div class="tooltip-row">{{ $t('chat.usage.prompt') }}: {{ usage.prompt_tokens }}
            <template v-if="hasCacheData">
              (<span class="cache-hit">{{ $t('chat.usage.cacheHit') }}: {{ usage.cache_hit_tokens }}</span>,
              <span class="cache-miss">{{ $t('chat.usage.cacheMiss') }}: {{ usage.cache_miss_tokens }}</span>)
            </template>
          </div>
          <div class="tooltip-row">{{ $t('chat.usage.completion') }}: {{ usage.completion_tokens }}
            <template v-if="reasoningTokens">({{ $t('chat.usage.reasoning') }}: {{ reasoningTokens }})</template>
          </div>
          <div class="tooltip-row">{{ $t('chat.usage.total') }}: {{ usage.total_tokens }}</div>
        </div>
      </template>
      <div class="donut-container">
        <svg :width="donutSize" :height="donutSize" viewBox="0 0 36 36" class="donut-chart">
          <circle class="donut-bg" cx="18" cy="18" r="15.5" fill="none" stroke="var(--el-border-color-lighter, #e4e7ed)" stroke-width="3" />
          <!-- 缓存命中 (浅蓝) -->
          <circle
            v-if="donutSegments.cacheHitLen > 0"
            class="donut-segment cache-hit"
            cx="18" cy="18" r="15.5" fill="none"
            stroke="#7EC8F8" stroke-width="3"
            :stroke-dasharray="`${donutSegments.cacheHitLen} ${donutCircumference - donutSegments.cacheHitLen}`"
            :stroke-dashoffset="donutSegments.cacheHitOffset"
          />
          <!-- 缓存未命中 (深蓝) -->
          <circle
            v-if="donutSegments.cacheMissLen > 0"
            class="donut-segment cache-miss"
            cx="18" cy="18" r="15.5" fill="none"
            stroke="#409EFF" stroke-width="3"
            :stroke-dasharray="`${donutSegments.cacheMissLen} ${donutCircumference - donutSegments.cacheMissLen}`"
            :stroke-dashoffset="donutSegments.cacheMissOffset"
          />
          <!-- 输出 (绿色) -->
          <circle
            v-if="donutSegments.outputLen > 0"
            class="donut-segment output"
            cx="18" cy="18" r="15.5" fill="none"
            stroke="#67C23A" stroke-width="3"
            :stroke-dasharray="`${donutSegments.outputLen} ${donutCircumference - donutSegments.outputLen}`"
            :stroke-dashoffset="donutSegments.outputOffset"
          />
          <!-- 无缓存数据 -> cache_miss 全部深蓝 + output 绿色 -->
          <template v-if="!hasCacheData">
            <circle
              v-if="donutSegments.cacheMissLen > 0"
              class="donut-segment cache-miss"
              cx="18" cy="18" r="15.5" fill="none"
              stroke="#409EFF" stroke-width="3"
              :stroke-dasharray="`${donutSegments.cacheMissLen} ${donutCircumference - donutSegments.cacheMissLen}`"
              :stroke-dashoffset="donutSegments.cacheMissOffset"
            />
            <circle
              v-if="donutSegments.outputLen > 0"
              class="donut-segment output"
              cx="18" cy="18" r="15.5" fill="none"
              stroke="#67C23A" stroke-width="3"
              :stroke-dasharray="`${donutSegments.outputLen} ${donutCircumference - donutSegments.outputLen}`"
              :stroke-dashoffset="donutSegments.outputOffset"
            />
          </template>
        </svg>
      </div>
    </el-tooltip>

    <!-- 模式2: 未配置最大上下文 -> 100k 短方块并排 -->
    <el-tooltip v-else placement="top" :show-after="300">
      <template #content>
        <div class="usage-tooltip">
          <div class="tooltip-row">{{ $t('chat.usage.prompt') }}: {{ usage.prompt_tokens }}
            <template v-if="hasCacheData">
              (<span class="cache-hit">{{ $t('chat.usage.cacheHit') }}: {{ usage.cache_hit_tokens }}</span>,
              <span class="cache-miss">{{ $t('chat.usage.cacheMiss') }}: {{ usage.cache_miss_tokens }}</span>)
            </template>
          </div>
          <div class="tooltip-row">{{ $t('chat.usage.completion') }}: {{ usage.completion_tokens }}
            <template v-if="reasoningTokens">({{ $t('chat.usage.reasoning') }}: {{ reasoningTokens }})</template>
          </div>
          <div class="tooltip-row">{{ $t('chat.usage.total') }}: {{ usage.total_tokens }}</div>
        </div>
      </template>
      <div class="bar-blocks">
        <div
          v-for="block in barBlocks"
          :key="block.index"
          class="bar-block"
        >
          <div class="block-fill" :style="{ height: block.fillPct + '%' }">
            <div class="fill-band cache-hit" :style="{ height: block.colorPcts.cacheHit + '%' }" />
            <div class="fill-band cache-miss" :style="{ height: block.colorPcts.cacheMiss + '%' }" />
            <div class="fill-band output" :style="{ height: block.colorPcts.output + '%' }" />
          </div>
        </div>
      </div>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { SubMessage } from '@/api/types';

interface UsageData {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  completion_tokens_details?: { reasoning_tokens?: number };
  cache_hit_tokens?: number;
  cache_miss_tokens?: number;
  [key: string]: unknown;
}

const props = defineProps<{
  usageSubMessage: SubMessage;
  /** 模型最大上下文 token 数（来自 meta_config.context_length），> 0 时启用环形图 */
  maxContextTokens?: number;
}>();

const { t } = useI18n();

const parsedUsage = computed<UsageData>(() => {
  try {
    if (props.usageSubMessage.content) {
      return JSON.parse(props.usageSubMessage.content) as UsageData;
    }
  } catch { /* ignore */ }
  return {};
});

const usage = computed<UsageData>(() => parsedUsage.value);

const hasUsage = computed(() => typeof usage.value.prompt_tokens === 'number');

const reasoningTokens = computed(() => usage.value.completion_tokens_details?.reasoning_tokens);

const hasCacheData = computed(
  () => typeof usage.value.cache_hit_tokens === 'number'
);

const useDonutMode = computed(() => {
  const max = props.maxContextTokens;
  return typeof max === 'number' && max > 0;
});

// ========== 环形图 ==========
const donutSize = 24;
const donutRadius = 15.5;
const donutCircumference = 2 * Math.PI * donutRadius;

const donutSegments = computed(() => {
  const circ = donutCircumference;
  const total = usage.value.total_tokens ?? 0;
  const contextLen = props.maxContextTokens ?? total;

  // 环形总填充比例 = total / context_length，剩余部分留空（灰色底色）
  const fillRatio = Math.min(total / Math.max(contextLen, 1), 1);
  const fillLen = circ * fillRatio;

  const hit = usage.value.cache_hit_tokens ?? 0;
  const miss = usage.value.cache_miss_tokens ?? (usage.value.prompt_tokens ?? 0);
  const out = usage.value.completion_tokens ?? 0;
  const tokenTotal = total || 1;

  const hitLen = fillLen * (hit / tokenTotal);
  const missLen = fillLen * (miss / tokenTotal);
  const outputLen = fillLen * (out / tokenTotal);

  const hitOffset = 0;
  const missOffset = -hitLen;
  const outputOffset = -(hitLen + missLen);

  return {
    cacheHitLen: hitLen,
    cacheHitOffset: hitOffset,
    cacheMissLen: missLen,
    cacheMissOffset: missOffset,
    outputLen: outputLen,
    outputOffset: outputOffset,
  };
});

// ========== 横向短方块 (每 100k 一个) ==========
const BLOCK_SIZE = 100_000;

interface BarBlock {
  index: number;
  fillPct: number;       // 该方块填充高度百分比
  colorPcts: { cacheHit: number; cacheMiss: number; output: number };
}

const barBlocks = computed<BarBlock[]>(() => {
  const total = (usage.value.total_tokens ?? 0) || 1;
  const hit = usage.value.cache_hit_tokens ?? 0;
  const miss = usage.value.cache_miss_tokens ?? (usage.value.prompt_tokens ?? 0);
  const out = usage.value.completion_tokens ?? 0;

  // 全局色比（所有方块共享同一比例）
  const hitPct = (hit / total) * 100;
  const missPct = (miss / total) * 100;
  const outPct = (out / total) * 100;
  const colorPcts = { cacheHit: hitPct, cacheMiss: missPct, output: outPct };

  const blockCount = Math.min(Math.ceil(total / BLOCK_SIZE), 10);
  const blocks: BarBlock[] = [];
  for (let i = 0; i < blockCount; i++) {
    const bucketStart = i * BLOCK_SIZE;
    const bucketUsed = Math.max(0, Math.min(BLOCK_SIZE, total - bucketStart));
    blocks.push({
      index: i,
      fillPct: (bucketUsed / BLOCK_SIZE) * 100,
      colorPcts,
    });
  }
  return blocks;
});
</script>

<style scoped>
.usage-info {
  display: inline-flex;
  align-items: center;
  user-select: none;
  cursor: pointer;
}

/* ========== 环形图 ========== */
.donut-container {
  display: inline-flex;
  align-items: center;
}
.donut-chart {
  transform: rotate(-90deg);
  display: block;
}
.donut-bg {
  opacity: 0.6;
}
.donut-segment {
  stroke-linecap: butt;
  transition: stroke-dasharray 0.4s ease, stroke-dashoffset 0.4s ease;
}

/* ========== 横向短方块 ========== */
.bar-blocks {
  display: inline-flex;
  gap: 3px;
  align-items: flex-end;
}
.bar-block {
  width: 8px;
  height: 18px;
  background: var(--el-border-color-lighter, #e4e7ed);
  border-radius: 3px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}
.block-fill {
  width: 100%;
  border-radius: 3px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: height 0.3s ease;
}
.fill-band {
  width: 100%;
  transition: height 0.3s ease;
}
.fill-band.cache-hit { background: #7EC8F8; }
.fill-band.cache-miss { background: #409EFF; }
.fill-band.output { background: #67C23A; }

/* ========== Tooltip ========== */
.usage-tooltip {
  font-size: 12px;
  line-height: 1.6;
}
.tooltip-row { white-space: nowrap; }
.cache-hit { color: #7EC8F8; font-weight: 500; }
.cache-miss { color: #409EFF; font-weight: 500; }
</style>
