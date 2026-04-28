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
          v-if="!isSvg && !isMermaid"
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
    <div v-if="isMermaid && closed" class="mermaid-container" :class="{ collapsed: isCollapsed }">
      <div v-if="mermaidError" class="mermaid-error">{{ mermaidError }}</div>
      <el-image
        v-else-if="mermaidSvg && mermaidDataUrl"
        :src="mermaidDataUrl"
        :preview-src-list="[mermaidDataUrl]"
        :initial-index="0"
        fit="contain"
        class="mermaid-image"
        :z-index="9999"
        :preview-teleported="true"
        hide-on-click-modal
      >
        <template #error>
          <div v-html="mermaidSvg" class="mermaid-svg" @click="openMermaidPreview"></div>
        </template>
      </el-image>
      <div v-else class="mermaid-loading">{{ t('chat.codeBlock.rendering') }}</div>
    </div>
    <div v-else-if="isSvg" class="svg-container" :class="{ collapsed: isCollapsed }">
      <el-image
        :src="svgDataUrl"
        :preview-src-list="[svgDataUrl]"
        :initial-index="0"
        fit="contain"
        class="svg-image"
        :z-index="9999"
        :preview-teleported="true"
        hide-on-click-modal
      >
        <template #error>
          <div v-html="sanitizedSvg" class="raw-svg" @click="openSvgPreview"></div>
        </template>
      </el-image>
    </div>
    <div v-else class="code-block-content" :class="{ collapsed: isCollapsed }" ref="contentRef">
      <pre class="hljs"><code v-html="highlightedCode"></code></pre>
    </div>
    <el-image-viewer
      v-if="showSvgPreview"
      :url-list="[svgDataUrl]"
      :initial-index="0"
      @close="closeSvgPreview"
      :z-index="9999"
      :teleported="true"
    />
    <el-image-viewer
      v-if="showMermaidPreview"
      :url-list="[mermaidDataUrl]"
      :initial-index="0"
      @close="closeMermaidPreview"
      :z-index="9999"
      :teleported="true"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElImageViewer } from 'element-plus'
import type { PropType } from 'vue'
import { Edit, CopyDocument, ArrowUpBold, ArrowDownBold } from '@element-plus/icons-vue'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import mermaid from 'mermaid'
import DOMPurify from 'dompurify'

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
  closed: {
    type: Boolean,
    default: true,
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

const isMermaid = computed(() => ['mermaid'].includes((props.language || '').toLowerCase()))
const isSvg = computed(() => ['svg'].includes((props.language || '').toLowerCase()))

const isCollapsed = ref(!props.isGenerating && !isSvg.value && !(isMermaid.value && props.closed) && totalLines.value > DEFAULT_COLLAPSE_THRESHOLD)

const mermaidSvg = ref<string>('')
const mermaidError = ref<string>('')
const showSvgPreview = ref(false)
const showMermaidPreview = ref(false)

const svgDataUrl = computed(() => {
  if (!isSvg.value || !props.code) return ''
  const blob = new Blob([props.code.trim()], { type: 'image/svg+xml;charset=utf-8' })
  return URL.createObjectURL(blob)
})

const mermaidDataUrl = computed(() => {
  if (!mermaidSvg.value) return ''
  const blob = new Blob([mermaidSvg.value], { type: 'image/svg+xml;charset=utf-8' })
  return URL.createObjectURL(blob)
})

const sanitizedSvg = computed(() => {
  if (!isSvg.value || !props.code) return ''
  let code = props.code
  const hasWidth = /<svg[^>]*\bwidth\s*=/.test(code)
  const hasHeight = /<svg[^>]*\bheight\s*=/.test(code)
  const viewBoxMatch = code.match(/viewBox="([^"]+)"/)
  if (viewBoxMatch && (!hasWidth || !hasHeight)) {
    const parts = viewBoxMatch[1].split(/[\s,]+/).map(Number)
    const vw = parts[2], vh = parts[3]
    if (vw > 0 && vh > 0) {
      const insert: string[] = []
      if (!hasWidth) insert.push(`width="${vw}"`)
      if (!hasHeight) insert.push(`height="${vh}"`)
      if (insert.length) code = code.replace(/<svg/, `<svg ${insert.join(' ')}`)
    }
  }
  return DOMPurify.sanitize(code, {
    USE_PROFILES: { svg: true, html: true },
    ADD_TAGS: [
      'svg', 'path', 'circle', 'rect', 'line', 'polyline', 'polygon', 'g', 'text', 'foreignObject', 'title', 'desc', 'defs', 'linearGradient', 'radialGradient', 'stop', 'animate', 'animateTransform', 'animateMotion', 'ellipse', 'use', 'clipPath', 'mask', 'pattern', 'image', 'filter', 'feGaussianBlur', 'feOffset', 'feMerge', 'feMergeNode', 'feColorMatrix', 'feComponentTransfer', 'feFuncR', 'feFuncG', 'feFuncB', 'feFuncA', 'tspan', 'symbol', 'marker'
    ],
    ADD_ATTR: [
      'xmlns', 'viewBox', 'width', 'height', 'preserveAspectRatio', 'fill', 'stroke', 'stroke-width',
      'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'stroke-miterlimit', 'stroke-opacity', 'd',
      'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'y1', 'x2', 'y2',
      'points', 'transform', 'text-anchor', 'font-size', 'font-family', 'font-weight',
      'style', 'class', 'id', 'opacity', 'offset', 'attributeName', 'type', 'values', 'from', 'to', 'dur',
      'repeatCount', 'repeatDur', 'begin', 'end', 'fill-rule', 'clip-rule', 'clip-path',
      'filter', 'flood-color', 'flood-opacity', 'stdDeviation', 'dx', 'dy', 'result', 'in', 'in2', 'mode',
      'color-interpolation', 'color-interpolation-filters', 'xlink:href', 'href',
      'gradientUnits', 'gradientTransform', 'patternUnits', 'patternTransform',
      'markerWidth', 'markerHeight', 'markerUnits', 'refX', 'refY', 'orient', 'overflow',
      'baseFrequency', 'numOctaves', 'seed', 'tableValues', 'slope', 'intercept', 'amplitude', 'exponent',
      'enable-background', 'xml:space', 'dominant-baseline', 'alignment-baseline', 'baseline-shift',
      'letter-spacing', 'word-spacing', 'textLength', 'lengthAdjust',
      'maskContentUnits', 'maskUnits', 'xlink', 'xmlns:xlink',
      'fx', 'fy', 'spreadMethod', 'stop-color', 'stop-opacity',
      'keyPoints', 'keyTimes', 'keySplines', 'calcMode', 'additive', 'accumulate'
    ]
  })
})

const renderMermaid = async () => {
  if (!isMermaid.value || !props.code || !props.closed) return

  try {
    mermaidError.value = ''
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose'
    })
    const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`
    const { svg } = await mermaid.render(id, props.code)
    mermaidSvg.value = svg
  } catch (err: any) {
    console.error('Mermaid rendering failed', err)
    mermaidError.value = err.message || 'Failed to render mermaid diagram'
  }
}

onMounted(() => {
  if (isMermaid.value) {
    renderMermaid()
  }
})

watch(() => props.code, () => {
  if (isMermaid.value && (props.closed || !props.isGenerating)) {
    renderMermaid()
  }
})

watch(() => props.isGenerating, (generating) => {
  if (!generating && isMermaid.value) {
    renderMermaid()
  }
})

watch(() => props.closed, (closed) => {
  if (closed && isMermaid.value) {
    renderMermaid()
  }
})

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
      isCollapsed.value = !isSvg.value && !isMermaid.value && totalLines.value > DEFAULT_COLLAPSE_THRESHOLD
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

const openSvgPreview = () => {
  showSvgPreview.value = true
}

const closeSvgPreview = () => {
  showSvgPreview.value = false
}

const openMermaidPreview = () => {
  showMermaidPreview.value = true
}

const closeMermaidPreview = () => {
  showMermaidPreview.value = false
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

.mermaid-container, .svg-container {
  padding: 1rem;
  background-color: var(--el-bg-color);
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: auto;
  position: relative;
  transition: max-height 0.25s ease-out;
}

.mermaid-container.collapsed, .svg-container.collapsed {
  max-height: 6.5em;
  overflow: hidden;
}

.mermaid-svg :deep(svg), .raw-svg :deep(svg) {
  max-width: 100%;
  height: auto;
}

.mermaid-error {
  color: var(--el-color-danger);
  padding: 1rem;
  font-family: monospace;
  white-space: pre-wrap;
}

.mermaid-loading {
  color: var(--el-text-color-secondary);
}

.hljs {
  padding: 1em !important;
  font-size: 14px;
  line-height: 1.5;
  background-color: transparent !important;
}

:deep(.raw-svg > svg) {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 auto;
}

.svg-image {
  max-width: 100%;
  cursor: zoom-in;
}

.svg-image :deep(.el-image__inner) {
  max-height: 600px;
  object-fit: contain;
}

.svg-image :deep(.el-image__error) {
  display: block;
}

.raw-svg {
  cursor: zoom-in;
}

.mermaid-image {
  max-width: 100%;
  cursor: zoom-in;
}

.mermaid-image :deep(.el-image__inner) {
  max-height: 600px;
  object-fit: contain;
}

.mermaid-image :deep(.el-image__error) {
  display: block;
}

.mermaid-svg {
  cursor: zoom-in;
}
</style>
