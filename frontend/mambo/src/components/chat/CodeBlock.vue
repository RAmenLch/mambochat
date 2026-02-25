<template>
  <div class="code-block-container">
    <div class="code-block-header">
      <span class="language-name">{{ language || 'text' }}</span>
      <div class="actions">
        <span class="line-count">{{ t('chat.codeBlock.lines', { count: totalLines }) }}</span>
        <el-tooltip :content="t('common.action.edit')" placement="top" :show-after="500">
          <el-button
            :icon="Edit"
            circle
            text
            size="small"
            :disabled="isGenerating"
            @click="emitEdit"
          />
        </el-tooltip>
        <el-tooltip :content="t('common.action.copy')" placement="top" :show-after="500">
          <el-button
            :icon="CopyDocument"
            circle
            text
            size="small"
            :disabled="isGenerating"
            @click="emitCopy"
          />
        </el-tooltip>
        <el-tooltip
          :content="isCollapsed ? t('common.action.expand') : t('common.action.collapse')"
          placement="top"
          :show-after="500"
        >
          <el-button
            :icon="isCollapsed ? ArrowDownBold : ArrowUpBold"
            circle
            text
            size="small"
            :disabled="isGenerating"
            @click="toggleCollapse"
          />
        </el-tooltip>
      </div>
    </div>
    <div class="code-block-content" :class="{ collapsed: isCollapsed }" ref="contentRef">
      <pre class="hljs"><code v-html="highlightedCode"></code></pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PropType } from 'vue'
import { Edit, CopyDocument, ArrowUpBold, ArrowDownBold } from '@element-plus/icons-vue'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

interface CodeBlockRange {
  start: number
  end: number
}

const DEFAULT_COLLAPSE_THRESHOLD = 20

const props = defineProps({
  code: {
    type: String,
    required: true,
  },
  language: {
    type: String,
    default: '',
  },
  isGenerating: {
    type: Boolean,
    default: false,
  },
  range: {
    type: Object as PropType<CodeBlockRange>,
    required: true,
  },
  markup: {
    type: String,
    default: '```',
  },
})

const emit = defineEmits<{
  (
    e: 'edit',
    payload: { code: string; range: CodeBlockRange; language: string; markup: string },
  ): void
  (e: 'copy', code: string): void
}>()

const { t } = useI18n()

const totalLines = computed(() => props.code.split('\n').length)

const isCollapsed = ref(!props.isGenerating && totalLines.value > DEFAULT_COLLAPSE_THRESHOLD)

const highlightedCode = computed(() => {
  const lang = props.language || 'plaintext'
  if (lang && hljs.getLanguage(lang)) {
    try {
      return hljs.highlight(props.code, {
        language: lang,
        ignoreIllegals: true,
      }).value
    } catch (e) {
      console.error(e)
    }
  }
  return hljs.highlight(props.code, { language: 'plaintext', ignoreIllegals: true }).value
})

watch(
  () => props.isGenerating,
  (generating, wasGenerating) => {
    if (generating) {
      isCollapsed.value = false
    } else if (wasGenerating && !generating) {
      isCollapsed.value = totalLines.value > DEFAULT_COLLAPSE_THRESHOLD
    }
  },
)

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const emitEdit = () => {
  emit('edit', {
    code: props.code,
    range: props.range,
    language: props.language,
    markup: props.markup,
  })
}

const emitCopy = () => {
  emit('copy', props.code)
}
</script>

<style scoped>
.code-block-container {
  --hljs-background: #282c34;
  --hljs-color: #abb2bf;

  background-color: var(--hljs-background);
  color: var(--hljs-color);
  border-radius: 6px;
  margin: 1em 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color-light);
}

.code-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  background-color: rgba(255, 255, 255, 0.05);
  height: 32px;
}

.language-name {
  font-size: 12px;
  color: #ccc;
  font-family: 'Courier New', Courier, monospace;
}

.actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.line-count {
  font-size: 12px;
  color: #999;
  margin-right: 8px;
  user-select: none;
}

.actions .el-button {
  color: #ccc;
}

.actions .el-button:hover {
  color: #fff;
  background-color: rgba(255, 255, 255, 0.1);
}

.code-block-content {
  position: relative;
  max-height: 800px;
  overflow: auto;
  transition: max-height 0.25s ease-out;
}

.code-block-content.collapsed {
  max-height: 6.5em;
  overflow: hidden;
}

.code-block-content::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  background: linear-gradient(to bottom, transparent, var(--hljs-background));
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.25s ease-out;
}

.code-block-content.collapsed::after {
  opacity: 1;
}

.code-block-content pre,
.code-block-content code {
  color: inherit;
  font-family: 'Courier New', Courier, monospace;
}

.code-block-content pre {
  margin: 0;
}

.hljs {
  padding: 1em !important;
  font-size: 14px;
  line-height: 1.5;
  background-color: transparent !important;
}
</style>
