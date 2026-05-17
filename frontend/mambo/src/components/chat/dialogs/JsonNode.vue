<template>
  <span class="json-node" :class="[`json-depth-${Math.min(depth, 5)}`]">
    <!-- Object -->
    <template v-if="isObject">
      <span class="json-toggle" @click="toggle" :class="{ collapsed }">
        <span class="json-arrow">▶</span>
      </span>
      <span class="json-bracket" @click="toggle">{</span>
      <span v-if="collapsed" class="json-preview" @click="toggle">
        <span class="json-summary">{{ objectSummary }}</span>
      </span>
      <span v-if="collapsed" class="json-bracket">}</span>
      <span v-if="!collapsed" class="json-children">
        <div
          v-for="(val, key) in value"
          :key="key"
          class="json-entry"
        >
          <span class="json-key" :class="{ 'json-key--special': isSpecialKey(String(key)) }">
            <el-tooltip
              v-if="isSpecialKey(String(key))"
              :content="getSpecialKeyTooltip(String(key), val)"
              placement="top"
              :show-after="400"
            >
              <span>{{ quoteKey(String(key)) }}</span>
            </el-tooltip>
            <span v-else>{{ quoteKey(String(key)) }}</span>
          </span>
          <span class="json-colon">: </span>
          <JsonNode
            :value="val"
            :depth="depth + 1"
            :maxStringLength="maxStringLength"
            :maxExpandDepth="maxExpandDepth"
            :path="`${path}.${key}`"
            :keyName="String(key)"
          />
          <span v-if="!isLastEntry(String(key))" class="json-comma">,</span>
        </div>
      </span>
      <span v-if="!collapsed" class="json-bracket json-bracket--close">}</span>
      <span v-if="collapsed" class="json-null">,</span> <!-- dummy, handled by outer -->
    </template>

    <!-- Array -->
    <template v-else-if="isArray">
      <span class="json-toggle" @click="toggle" :class="{ collapsed }">
        <span class="json-arrow">▶</span>
      </span>
      <span class="json-bracket" @click="toggle">[</span>
      <span v-if="collapsed" class="json-preview" @click="toggle">
        <span class="json-summary">{{ arraySummary }}</span>
      </span>
      <span v-if="collapsed" class="json-bracket">]</span>
      <span v-if="!collapsed" class="json-children">
        <div
          v-for="(item, index) in value"
          :key="index"
          class="json-entry"
        >
          <JsonNode
            :value="item"
            :depth="depth + 1"
            :maxStringLength="maxStringLength"
            :maxExpandDepth="maxExpandDepth"
            :path="`${path}[${index}]`"
            :keyName="`[${index}]`"
          />
          <span v-if="(index as number) < value.length - 1" class="json-comma">,</span>
        </div>
      </span>
      <span v-if="!collapsed" class="json-bracket json-bracket--close">]</span>
    </template>

    <!-- String (truncatable → popup dialog) -->
    <template v-else-if="isString">
      <span class="json-string json-string--clickable" v-if="isTruncated" @click="openTextDialog">
        "{{ truncatedStr }}"
        <span class="json-truncate-hint">{{ $t('chat.logViewer.viewFullText', { count: strLength }) }}</span>
      </span>
      <span class="json-string" v-else>"{{ value }}"</span>
      <el-button
        v-if="typeof value === 'string' && value.length > 20"
        class="json-copy-btn"
        size="small"
        text
        @click.stop="copyValue"
      >
        <el-icon><CopyDocument /></el-icon>
      </el-button>
    </template>

    <!-- Number -->
    <template v-else-if="isNumber">
      <span class="json-number">{{ value }}</span>
    </template>

    <!-- Boolean -->
    <template v-else-if="isBoolean">
      <span class="json-boolean">{{ value }}</span>
    </template>

    <!-- Null -->
    <template v-else-if="isNull">
      <span class="json-null">null</span>
    </template>

    <!-- Fallback -->
    <template v-else>
      <span class="json-string">"{{ String(value) }}"</span>
    </template>
  </span>

  <!-- Text Viewer Dialog (must be root-level sibling, not inside <span>) -->
  <Teleport to="body">
    <el-dialog
      v-if="textDialogVisible"
      v-model="textDialogVisible"
      :title="textDialogTitle"
      width="750px"
      class="json-text-dialog"
      destroy-on-close
      :close-on-click-modal="true"
    >
      <div class="text-dialog-body">
        <div class="text-dialog-toolbar">
          <span class="text-dialog-info">{{ $t('chat.logViewer.charCount', { count: strLength }) }}</span>
          <div class="text-dialog-actions">
            <el-button size="small" @click="copyDialogText">
              <el-icon><CopyDocument /></el-icon>
              {{ $t('chat.logViewer.copyText') }}
            </el-button>
            <el-button size="small" @click="wrapToggle">
              <el-icon><Operation /></el-icon>
              {{ textWrap ? $t('chat.logViewer.noWrap') : $t('chat.logViewer.wrap') }}
            </el-button>
          </div>
        </div>
        <pre class="text-dialog-content" :class="{ 'text-nowrap': !textWrap }">{{ value }}</pre>
      </div>
    </el-dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { CopyDocument, Operation } from '@element-plus/icons-vue';

defineOptions({ name: 'JsonNode' });

const props = withDefaults(defineProps<{
  value: any;
  depth: number;
  maxStringLength: number;
  maxExpandDepth: number;
  path: string;
  keyName?: string;
}>(), {
  maxStringLength: 200,
  maxExpandDepth: 3,
});

const collapsed = ref(props.depth >= props.maxExpandDepth || isMessageLike(props.value));

// Text dialog state
const textDialogVisible = ref(false);
const textWrap = ref(true);

const isObject = computed(() => props.value !== null && typeof props.value === 'object' && !Array.isArray(props.value));
const isArray = computed(() => Array.isArray(props.value));
const isString = computed(() => typeof props.value === 'string');
const isNumber = computed(() => typeof props.value === 'number');
const isBoolean = computed(() => typeof props.value === 'boolean');
const isNull = computed(() => props.value === null);

const strLength = computed(() => isString.value ? props.value.length : 0);
const isTruncated = computed(() => isString.value && strLength.value > props.maxStringLength);
const truncatedStr = computed(() => {
  if (!isTruncated.value) return '';
  return props.value.substring(0, props.maxStringLength) + '…';
});

// ---- Message-aware helpers ----

function isMessageLike(item: any): boolean {
  if (typeof item !== 'object' || item === null || Array.isArray(item)) return false;
  const roleKey = item.role ?? item.type;
  return typeof roleKey === 'string' && item.content !== undefined;
}

function getMessageRole(item: any): string {
  return (item.role || item.type || '?').toString();
}

function getContentPreview(content: any, maxLen: number = 35): string {
  if (typeof content === 'string') {
    const clipped = content.length > maxLen ? content.substring(0, maxLen) + '…' : content;
    return `"${clipped}"`;
  }
  if (Array.isArray(content) && content.length > 0) {
    const first = content[0];
    if (first && typeof first === 'object' && first.type) {
      if (first.type === 'text' && typeof first.text === 'string') {
        const txt = first.text.length > 20 ? first.text.substring(0, 20) + '…' : first.text;
        return `[type:"${first.type}", text:"${txt}"]`;
      }
      return `[type:"${first.type}"…]`;
    }
    return `[${content.length} items]`;
  }
  if (typeof content === 'object' && content !== null) {
    return '{…}';
  }
  return String(content).substring(0, maxLen);
}

// ---- Summaries ----

const objectSummary = computed(() => {
  if (!isObject.value) return '';
  const obj = props.value;

  // Message-like object: show role + content preview
  if (isMessageLike(obj)) {
    const role = getMessageRole(obj);
    const cp = getContentPreview(obj.content, 30);
    return `role: ${role}, content: ${cp}`;
  }

  const keys = Object.keys(props.value);
  const shown = keys.slice(0, 3);
  const extra = keys.length - shown.length;
  let summary = shown.map(k => `${k}: …`).join(', ');
  if (extra > 0) summary += `, +${extra} more`;
  return summary;
});

const arraySummary = computed(() => {
  if (!isArray.value) return '';
  const len = props.value.length;
  if (len === 0) return '';

  // If items are message-like, show role + content preview for each
  if (len > 0 && isMessageLike(props.value[0])) {
    const preview = props.value.slice(0, 3).map((item: any) => {
      const role = getMessageRole(item);
      const cp = getContentPreview(item.content, 25);
      return `type:${role}, content:${cp}`;
    }).join('  ·  ');
    let result = preview;
    if (len > 3) result += `  ·  +${len - 3} more`;
    return result;
  }

  const preview = props.value.slice(0, 2).map((item: any) => {
    if (typeof item === 'string') return `"${item.substring(0, 20)}${item.length > 20 ? '…' : ''}"`;
    if (typeof item === 'object' && item !== null) {
      if (Array.isArray(item)) return '[…]';
      return '{…}';
    }
    return String(item);
  }).join(', ');
  let result = `${preview}`;
  if (len > 2) result += `, … +${len - 2} items`;
  return result;
});

function toggle() {
  collapsed.value = !collapsed.value;
}

const textDialogTitle = computed(() => {
  if (props.keyName) return `${props.keyName}`;
  return props.path || 'Text';
});

function openTextDialog() {
  textDialogVisible.value = true;
}

function copyDialogText() {
  const text = typeof props.value === 'string' ? props.value : JSON.stringify(props.value, null, 2);
  navigator.clipboard.writeText(text).catch(() => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  });
}

function wrapToggle() {
  textWrap.value = !textWrap.value;
}

function isLastEntry(key: string): boolean {
  if (!isObject.value) return false;
  const keys = Object.keys(props.value);
  return keys[keys.length - 1] === key;
}

function isSpecialKey(key: string): boolean {
  const specialKeys = ['content', 'messages', 'tools', 'tool_calls', 'function_call', 'arguments', 'input', 'output', 'system', 'instructions'];
  return specialKeys.includes(key.toLowerCase());
}

function getSpecialKeyTooltip(key: string, val: any): string {
  const lowerKey = key.toLowerCase();
  if (lowerKey === 'content' && typeof val === 'string') {
    return val.length > 500 ? val.substring(0, 500) + '…' : val;
  }
  if (lowerKey === 'messages' && Array.isArray(val)) {
    return `${val.length} messages`;
  }
  if (lowerKey === 'tools' && Array.isArray(val)) {
    return `${val.length} tools defined`;
  }
  if (lowerKey === 'tool_calls' && Array.isArray(val)) {
    return `${val.length} tool calls`;
  }
  return '';
}

function quoteKey(key: string): string {
  // Keys that need quoting
  if (/^[a-zA-Z_$][a-zA-Z0-9_$]*$/.test(key)) {
    return key;
  }
  return `"${key}"`;
}

function copyValue() {
  const text = typeof props.value === 'string' ? props.value : JSON.stringify(props.value, null, 2);
  navigator.clipboard.writeText(text).catch(() => {
    // fallback
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  });
}
</script>

<style scoped>
/* ===== Color Variables ===== */
.json-key {
  color: #881391;
}
.json-string {
  color: #0a7040;
}
.json-number {
  color: #1c6cb9;
}
.json-boolean {
  color: #c92c2c;
}
.json-null {
  color: #999;
}
.json-bracket {
  color: #555;
}
.json-colon {
  color: #555;
}
.json-comma {
  color: #555;
}

/* ===== Layout ===== */
.json-node {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.json-children {
  display: block;
  padding-left: 20px;
  border-left: 1px dashed #e0e0e0;
  margin-left: 4px;
}

.json-entry {
  display: block;
  white-space: nowrap;
}

/* ===== Toggle Arrow ===== */
.json-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  cursor: pointer;
  user-select: none;
  vertical-align: middle;
  margin-right: 2px;
  border-radius: 3px;
  transition: background 0.15s;
}
.json-toggle:hover {
  background: #e8e8e8;
}
.json-arrow {
  display: inline-block;
  font-size: 9px;
  color: #777;
  transition: transform 0.15s ease;
  line-height: 1;
}
.json-toggle:not(.collapsed) .json-arrow {
  transform: rotate(90deg);
}

/* ===== Brackets ===== */
.json-bracket {
  cursor: pointer;
  user-select: none;
}
.json-bracket:hover {
  color: #333;
}
.json-bracket--close {
  display: block;
}

/* ===== Collapsed Preview ===== */
.json-preview {
  cursor: pointer;
  user-select: none;
  margin: 0 4px;
}
.json-summary {
  color: #888;
  font-style: italic;
  font-size: 12px;
}

/* ===== String Truncation ===== */
.json-truncate-hint {
  color: #1a73e8;
  font-size: 11px;
  font-style: italic;
  cursor: pointer;
  margin-left: 4px;
  user-select: none;
}
.json-string--clickable {
  cursor: pointer;
}
.json-string--clickable:hover {
  text-decoration: underline;
  text-decoration-color: #1a73e8;
  text-decoration-style: dotted;
}

/* ===== Copy Button ===== */
.json-copy-btn {
  padding: 0 4px;
  margin-left: 2px;
  height: 18px;
  min-height: 18px;
  vertical-align: middle;
  opacity: 0;
  transition: opacity 0.15s;
}
.json-entry:hover .json-copy-btn,
.json-node:hover > .json-copy-btn {
  opacity: 0.7;
}
.json-copy-btn:hover {
  opacity: 1 !important;
}

/* ===== Special Key Highlight ===== */
.json-key--special {
  font-weight: 600;
  color: #6b21a8;
}

/* ===== Depth-based indentation marker ===== */
.json-depth-0 { /* root */ }
.json-depth-1 { /* first level */ }
.json-depth-2 { /* second level */ }
.json-depth-3 { /* third level */ }
.json-depth-4 { /* deeper */ }
.json-depth-5 { /* very deep */ }

/* ===== Dark Mode Overrides ===== */
@media (prefers-color-scheme: dark) {
  .json-key {
    color: #c586c0;
  }
  .json-key--special {
    color: #d4a0d4;
  }
  .json-string {
    color: #6a9955;
  }
  .json-number {
    color: #569cd6;
  }
  .json-boolean {
    color: #f44747;
  }
  .json-null {
    color: #808080;
  }
  .json-bracket,
  .json-colon,
  .json-comma {
    color: #999;
  }
  .json-bracket:hover {
    color: #ccc;
  }
  .json-toggle:hover {
    background: #333;
  }
  .json-arrow {
    color: #999;
  }
  .json-children {
    border-left-color: #444;
  }
  .json-summary {
    color: #777;
  }
  .json-truncate-hint {
    color: #569cd6;
  }
}

/* ===== Text Dialog (scoped穿透) ===== */
/* Note: el-dialog is teleported to body, so these use :deep() or global */
</style>

<style>
/* Text dialog - global styles since teleported */
.json-text-dialog .el-dialog__header {
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 16px 20px;
}
.json-text-dialog .el-dialog__title {
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  color: #881391;
  font-weight: 600;
}
.json-text-dialog .el-dialog__body {
  padding: 0;
}

.text-dialog-body {
  display: flex;
  flex-direction: column;
  max-height: 65vh;
}

.text-dialog-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 20px;
  background: var(--el-fill-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.text-dialog-info {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
}
.text-dialog-actions {
  display: flex;
  gap: 4px;
}

.text-dialog-content {
  margin: 0;
  padding: 16px 20px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  overflow-x: hidden;
  overflow-y: auto;
  max-height: calc(65vh - 48px);
  tab-size: 4;
}
.text-dialog-content.text-nowrap {
  white-space: pre;
  overflow-x: auto;
  word-break: normal;
  overflow-wrap: normal;
}

/* Dark mode for text dialog */
@media (prefers-color-scheme: dark) {
  .json-text-dialog .el-dialog__title {
    color: #c586c0;
  }
}
</style>
