<!-- frontend/mambo/src/components/chat/WebSearchResultList.vue -->
<template>
  <div class="web-search-result">
    <!-- 视图切换：卡片 / LLM 实际获取的原文 -->
    <div v-if="rawResult" class="wsr-toolbar">
      <span class="wsr-toolbar-hint">{{ t('chat.message.mcp.webSearch.rawHint') }}</span>
      <div class="wsr-switch">
        <button
          type="button"
          class="wsr-switch-btn"
          :class="{ 'is-active': view === 'cards' }"
          @click.stop="view = 'cards'"
        >
          {{ t('chat.message.mcp.webSearch.viewCards') }}
        </button>
        <button
          type="button"
          class="wsr-switch-btn"
          :class="{ 'is-active': view === 'raw' }"
          @click.stop="view = 'raw'"
        >
          {{ t('chat.message.mcp.webSearch.viewRaw') }}
        </button>
      </div>
    </div>

    <!-- 原文视图：与 LLM 实际读取到的工具结果文本完全一致 -->
    <div v-if="isRawView" class="wsr-raw-wrap">
      <pre class="wsr-raw">{{ rawResult }}</pre>
      <button
        type="button"
        class="wsr-action wsr-raw-copy"
        @click.stop="handleCopy(rawResult || '', 'chat.message.mcp.webSearch.copiedRaw')"
      >
        <el-icon><CopyDocument /></el-icon>
        {{ t('chat.message.mcp.webSearch.copyRaw') }}
      </button>
    </div>

    <!-- 结果列表 -->
    <template v-else-if="parsed.kind === 'list'">
      <div class="wsr-list">
        <article
          v-for="(item, idx) in visibleItems"
          :key="`${item.url}-${idx}`"
          class="wsr-card"
        >
          <header class="wsr-head">
            <div class="wsr-site">
              <img
                v-if="item.siteIcon && !failedIcons[idx]"
                :src="item.siteIcon"
                alt=""
                class="wsr-icon"
                loading="lazy"
                referrerpolicy="no-referrer"
                @error="markIconFailed(idx)"
              />
              <span v-else class="wsr-icon wsr-icon-fallback" :style="{ backgroundColor: fallbackColor(item) }">
                {{ fallbackLetter(item) }}
              </span>
              <span class="wsr-site-name" :title="item.siteName || ''">{{ item.siteName || item.url }}</span>
              <template v-if="item.date">
                <span class="wsr-sep">·</span>
                <span class="wsr-date">{{ item.date }}</span>
              </template>
            </div>
            <div class="wsr-badges">
              <span v-if="isHighQuality(item)" class="wsr-badge is-score">
                {{ t('chat.message.mcp.webSearch.bestMatch') }} {{ formatScore(item.score) }}
              </span>
              <el-tooltip
                v-if="isAuthoritative(item)"
                :content="t('chat.message.mcp.webSearch.authoritative')"
                placement="top"
                :show-after="300"
              >
                <span class="wsr-badge is-authority">
                  <span
                    v-for="dot in 4"
                    :key="dot"
                    class="wsr-dot"
                    :class="{ 'is-on': dot <= (item.authority || 0) }"
                  ></span>
                </span>
              </el-tooltip>
            </div>
          </header>

          <a
            class="wsr-title"
            :href="item.url"
            target="_blank"
            rel="noopener noreferrer"
            :title="item.title"
            @click.stop
          >
            {{ item.title || item.url }}
          </a>

          <p class="wsr-snippet" :class="{ 'is-expanded': isExpanded(idx) }">
            {{ isExpanded(idx) ? (item.summary || item.snippet) : item.snippet }}
          </p>
          <p v-if="isExpanded(idx) && item.content" class="wsr-content">{{ item.content }}</p>

          <footer class="wsr-foot">
            <span class="wsr-url" :title="item.url">{{ displayUrl(item.url) }}</span>
            <span class="wsr-actions">
              <el-tooltip
                v-if="hasMore(item)"
                :content="isExpanded(idx) ? t('chat.message.mcp.webSearch.collapse') : t('chat.message.mcp.webSearch.expand')"
                placement="top"
                :show-after="300"
              >
                <button type="button" class="wsr-action" @click.stop="toggleExpand(idx)">
                  {{ isExpanded(idx) ? t('chat.message.mcp.webSearch.collapse') : t('chat.message.mcp.webSearch.expand') }}
                  <el-icon :class="{ 'is-up': isExpanded(idx) }"><ArrowDown /></el-icon>
                </button>
              </el-tooltip>
              <el-tooltip :content="t('chat.message.mcp.webSearch.copyLink')" placement="top" :show-after="300">
                <button type="button" class="wsr-action is-icon" @click.stop="handleCopy(item.url)">
                  <el-icon><CopyDocument /></el-icon>
                </button>
              </el-tooltip>
              <el-tooltip :content="t('chat.message.mcp.webSearch.openLink')" placement="top" :show-after="300">
                <a class="wsr-action is-icon" :href="item.url" target="_blank" rel="noopener noreferrer" @click.stop>
                  <el-icon><TopRight /></el-icon>
                </a>
              </el-tooltip>
            </span>
          </footer>
        </article>
      </div>

      <button v-if="hasHiddenItems" type="button" class="wsr-more" @click.stop="showAll = !showAll">
        {{ showAll
          ? t('chat.message.mcp.webSearch.collapseAll')
          : t('chat.message.mcp.webSearch.expandAll', { count: parsed.items.length }) }}
        <el-icon :class="{ 'is-up': showAll }"><ArrowDown /></el-icon>
      </button>
    </template>

    <!-- 空结果 / 接口错误 -->
    <div v-else-if="parsed.kind === 'error'" class="wsr-note is-error">
      <el-icon><CircleClose /></el-icon>
      <span>{{ parsed.message }}</span>
    </div>
    <div v-else class="wsr-note">
      <el-icon><Search /></el-icon>
      <span>{{ parsed.message }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { ArrowDown, CircleClose, CopyDocument, Search, TopRight } from '@element-plus/icons-vue'
import type { WebSearchEntry, WebSearchParsed } from '@/utils/webSearchResult'
import { searchUrlHost } from '@/utils/webSearchResult'
import { copyToClipboard } from '@/utils/clipboard'

const { t } = useI18n()

const props = defineProps<{
  parsed: WebSearchParsed
  /** 工具返回给 LLM 的原始结果文本，用于「原文」视图核对实际上下文 */
  rawResult?: string | null
}>()

/** 折叠态下默认展示的条目数 */
const COLLAPSED_ITEM_COUNT = 5
/** 短摘要超过该长度才提供展开（展开后显示长摘要） */
const EXPANDABLE_SNIPPET_CHARS = 110
/** rerank_score 达到该阈值视为优质结果（DeepSeek 官方口径 1.5） */
const HIGH_QUALITY_SCORE = 1.5
/** authority 达到该阈值视为极权威结果（DeepSeek 官方口径 3） */
const AUTHORITY_THRESHOLD = 3

const showAll = ref(false)
const expanded = reactive<Record<number, boolean>>({})
const failedIcons = reactive<Record<number, boolean>>({})
/** 视图模式：卡片 / 原文（LLM 实际读取到的文本） */
const view = ref<'cards' | 'raw'>('cards')

const isRawView = computed(() => view.value === 'raw' && !!props.rawResult)

const items = computed<WebSearchEntry[]>(() =>
  props.parsed.kind === 'list' ? props.parsed.items : [],
)

const visibleItems = computed<WebSearchEntry[]>(() =>
  showAll.value ? items.value : items.value.slice(0, COLLAPSED_ITEM_COUNT),
)

const hasHiddenItems = computed(() => items.value.length > COLLAPSED_ITEM_COUNT)

function isExpanded(idx: number): boolean {
  return !!expanded[idx]
}

function toggleExpand(idx: number): void {
  expanded[idx] = !expanded[idx]
}

function hasMore(item: WebSearchEntry): boolean {
  if (item.content) return true
  return (item.summary || '').length > EXPANDABLE_SNIPPET_CHARS
}

function isHighQuality(item: WebSearchEntry): boolean {
  return item.score !== null && item.score >= HIGH_QUALITY_SCORE
}

function isAuthoritative(item: WebSearchEntry): boolean {
  return item.authority !== null && item.authority >= AUTHORITY_THRESHOLD
}

function formatScore(score: number | null): string {
  return score === null ? '' : score.toFixed(1)
}

function markIconFailed(idx: number): void {
  failedIcons[idx] = true
}

/** favicon 缺失/加载失败时用站点首字母 + 稳定色块兜底 */
function fallbackLetter(item: WebSearchEntry): string {
  const source = item.siteName || searchUrlHost(item.url) || '?'
  return source.replace(/^www\./, '').charAt(0).toUpperCase()
}

function fallbackColor(item: WebSearchEntry): string {
  const source = item.siteName || item.url || ''
  let hash = 0
  for (let i = 0; i < source.length; i += 1) {
    hash = (hash * 31 + source.charCodeAt(i)) % 360
  }
  return `hsl(${hash}, 55%, 45%)`
}

/** 省略协议与末尾斜杠，压缩卡片底部链接占用 */
function displayUrl(url: string): string {
  const stripped = url.replace(/^https?:\/\//, '').replace(/\/$/, '')
  return stripped.length > 72 ? `${stripped.slice(0, 72)}…` : stripped
}

function handleCopy(
  text: string,
  successKey: string = 'chat.message.mcp.webSearch.copied',
): void {
  copyToClipboard(text)
    .then(() => ElMessage.success(t(successKey)))
    .catch(() => ElMessage.error(t('chat.message.mcp.webSearch.copyFailed')))
}
</script>

<style scoped>
.web-search-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ========== 视图切换 ========== */
.wsr-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.wsr-toolbar-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wsr-switch {
  display: inline-flex;
  flex-shrink: 0;
  padding: 1px;
  border-radius: 10px;
  background-color: var(--el-fill-color-light);
}

.wsr-switch-btn {
  padding: 1px 8px;
  border: none;
  border-radius: 9px;
  background: none;
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 16px;
  cursor: pointer;
  transition: color 0.2s, background-color 0.2s;
}

.wsr-switch-btn:hover {
  color: var(--el-color-primary);
}

.wsr-switch-btn.is-active {
  color: var(--el-color-primary);
  background-color: var(--el-bg-color);
  box-shadow: 0 1px 2px rgb(0 0 0 / 8%);
}

/* ========== 原文视图 ========== */
.wsr-raw-wrap {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wsr-raw {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow: auto;
}

.wsr-raw-copy {
  align-self: flex-end;
}

.wsr-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wsr-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background-color: var(--el-bg-color);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.wsr-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 10px rgb(0 0 0 / 6%);
}

.wsr-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 18px;
}

.wsr-site {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.wsr-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border-radius: 4px;
  object-fit: contain;
  background-color: var(--el-fill-color-light);
}

.wsr-icon-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
}

.wsr-site-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.wsr-sep,
.wsr-date {
  flex-shrink: 0;
}

.wsr-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.wsr-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 6px;
  height: 18px;
  border-radius: 9px;
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
}

.wsr-badge.is-score {
  color: var(--el-color-success);
  background-color: var(--el-color-success-light-9);
}

.wsr-badge.is-authority {
  padding: 0 4px;
  background-color: var(--el-fill-color-light);
}

.wsr-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--el-border-color);
}

.wsr-dot.is-on {
  background-color: var(--el-color-primary);
}

.wsr-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--el-color-primary);
  text-decoration: none;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.wsr-title:hover {
  text-decoration: underline;
}

.wsr-snippet {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.wsr-snippet.is-expanded {
  display: block;
  -webkit-line-clamp: unset;
  line-clamp: unset;
}

.wsr-content {
  margin: 0;
  padding-left: 8px;
  border-left: 2px solid var(--el-border-color-lighter);
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.wsr-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.wsr-url {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wsr-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.wsr-action {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0 4px;
  border: none;
  background: none;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
}

.wsr-action:hover {
  color: var(--el-color-primary);
  background-color: var(--el-fill-color-light);
}

.wsr-action.is-icon {
  padding: 2px 4px;
}

.wsr-action .el-icon {
  font-size: 12px;
  transition: transform 0.2s;
}

.wsr-action .el-icon.is-up {
  transform: rotate(180deg);
}

.wsr-more {
  align-self: center;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 14px;
  background-color: var(--el-fill-color-blank);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  cursor: pointer;
}

.wsr-more:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}

.wsr-more .el-icon {
  font-size: 12px;
  transition: transform 0.2s;
}

.wsr-more .el-icon.is-up {
  transform: rotate(180deg);
}

.wsr-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 6px;
  background-color: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.wsr-note.is-error {
  color: var(--el-color-error);
  background-color: var(--el-color-error-light-9);
}
</style>
