<!-- MobileAskUserDialog.vue — 移动端用户问答弹窗 -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="au-overlay" @click="handleClose">
        <div class="au-sheet" @click.stop>
          <div class="sheet-handle"></div>

          <div class="au-header">
            <el-icon :size="20" color="var(--el-color-warning)"><Warning /></el-icon>
            <span class="au-title">需要您确认</span>
            <span class="au-count" v-if="askUserMessages.length > 1">{{ activeIndex + 1 }}/{{ askUserMessages.length }}</span>
          </div>

          <div class="au-body" v-if="activeEntry">
            <div
              v-for="(q, qIdx) in activeEntry.content.questions"
              :key="qIdx"
              class="au-question"
            >
              <div class="au-q-text">
                <span class="au-q-num">{{ qIdx + 1 }}.</span>
                {{ q.question }}
                <span v-if="q.required === false" class="au-optional">(可选)</span>
              </div>

              <!-- 单选题 -->
              <div v-if="q.type === 'multiple_choice' && q.choices?.length" class="au-choices">
                <button
                  v-for="choice in q.choices"
                  :key="choice.value"
                  class="au-choice-btn"
                  :class="{ active: answers[activeEntry.subMsg.id]?.[qIdx] === choice.value }"
                  @click="answers[activeEntry.subMsg.id][qIdx] = choice.value"
                >{{ choice.value }}</button>
                <button
                  class="au-choice-btn"
                  :class="{ active: answers[activeEntry.subMsg.id]?.[qIdx] === '__other__' }"
                  @click="answers[activeEntry.subMsg.id][qIdx] = '__other__'"
                >其他</button>
                <input
                  v-if="answers[activeEntry.subMsg.id]?.[qIdx] === '__other__'"
                  v-model="otherTexts[activeEntry.subMsg.id][qIdx]"
                  placeholder="请输入..."
                  class="au-other-input"
                  @input="(e: Event) => { const t = (e.target as HTMLInputElement).value; if (t) answers[activeEntry.subMsg.id][qIdx] = t }"
                />
              </div>

              <!-- 文本输入 -->
              <textarea
                v-else
                v-model="answers[activeEntry.subMsg.id][qIdx]"
                rows="3"
                placeholder="请输入..."
                class="au-textarea"
              ></textarea>
            </div>
          </div>

          <div class="au-footer">
            <button class="au-btn outline" @click="handleClose">取消</button>
            <button class="au-btn primary" :disabled="!isCurrentValid" @click="submitCurrent">提交回答</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch, reactive } from 'vue'
import type { Message, SubMessage, AskUserContent } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { ElMessage } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'

const props = defineProps<{
  visible: boolean
  parentMessageId: string | null
  initialSubMessageId?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()

const activeIndex = ref(0)
const answers = reactive<Record<string, Record<number, string>>>({})
const otherTexts = reactive<Record<string, Record<number, string>>>({})

interface AskUserEntry {
  subMsg: SubMessage
  content: AskUserContent
}

const parentMessage = computed<Message | null>(() => {
  if (!props.parentMessageId) return null
  return sessionStore.currentChatMessages.find(m => m.id === props.parentMessageId) || null
})

const askUserMessages = computed<AskUserEntry[]>(() => {
  if (!parentMessage.value) return []
  return parentMessage.value.sub_messages
    .filter(sm => sm.type === 'AskUser')
    .map(sm => {
      try {
        return { subMsg: sm, content: JSON.parse(sm.content) as AskUserContent }
      } catch {
        return null
      }
    })
    .filter((e): e is AskUserEntry => e !== null)
})

const activeEntry = computed(() => askUserMessages.value[activeIndex.value] || null)

const isCurrentValid = computed(() => {
  if (!activeEntry.value) return false
  const entry = activeEntry.value
  return entry.content.questions.every((q, i) => {
    if (q.required === false) return true
    const ans = answers[entry.subMsg.id]?.[i]
    return ans && ans.trim()
  })
})

watch(() => props.visible, (v) => {
  if (v) {
    activeIndex.value = 0
    askUserMessages.value.forEach(entry => {
      if (!answers[entry.subMsg.id]) {
        answers[entry.subMsg.id] = {}
        otherTexts[entry.subMsg.id] = {}
        entry.content.questions.forEach((_q, i) => {
          answers[entry.subMsg.id][i] = ''
          otherTexts[entry.subMsg.id][i] = ''
        })
      }
    })
    // Jump to initial if specified (single mode)
    if (props.initialSubMessageId) {
      const idx = askUserMessages.value.findIndex(e => e.subMsg.id === props.initialSubMessageId)
      if (idx >= 0) activeIndex.value = idx
    }
  }
})

function handleClose() {
  emit('update:visible', false)
}

async function submitCurrent() {
  if (!activeEntry.value) return
  const entry = activeEntry.value
  const finalAnswers: string[] = entry.content.questions.map((q, i) => {
    let ans = answers[entry.subMsg.id]?.[i] || ''
    if (ans === '__other__') {
      ans = otherTexts[entry.subMsg.id]?.[i] || ans
    }
    return ans
  })

  try {
    await interactionStore.submitAskUserAnswer(
      props.parentMessageId!,
      entry.subMsg.id,
      finalAnswers,
      'answered'
    )
    ElMessage.success('已提交回答')

    // Remove this entry and move to next or close
    const remaining = askUserMessages.value.filter(e => e.subMsg.id !== entry.subMsg.id)
    if (remaining.length > 0) {
      // Recalculate index
      const newIdx = Math.min(activeIndex.value, remaining.length - 1)
      activeIndex.value = newIdx
      // Clean up answers for submitted entry
      delete answers[entry.subMsg.id]
      delete otherTexts[entry.subMsg.id]
    } else {
      emit('update:visible', false)
    }
  } catch {
    ElMessage.error('提交失败')
  }
}
</script>

<style scoped>
.au-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 2000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.au-sheet {
  width: 100%;
  max-width: 500px;
  max-height: 80vh;
  background: var(--color-background);
  border-radius: 16px 16px 0 0;
  padding: 8px 16px;
  padding-bottom: max(16px, env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--el-border-color);
  border-radius: 2px;
  margin: 8px auto 12px;
  flex-shrink: 0;
}

.au-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.au-title {
  font-size: 17px;
  font-weight: 600;
  flex: 1;
}

.au-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.au-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.au-question {
  margin-bottom: 20px;
}

.au-q-text {
  font-size: 15px;
  font-weight: 500;
  margin-bottom: 10px;
  line-height: 1.5;
}

.au-q-num {
  color: var(--el-color-primary);
  font-weight: 700;
}

.au-optional {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-left: 4px;
}

.au-choices {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.au-choice-btn {
  width: 100%;
  padding: 12px 14px;
  border: 1.5px solid var(--el-border-color);
  border-radius: 10px;
  background: transparent;
  font-size: 15px;
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.au-choice-btn.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.au-other-input {
  width: 100%;
  margin-top: 4px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  font-size: 15px;
  outline: none;
  font-family: inherit;
}

.au-other-input:focus {
  border-color: var(--el-color-primary);
}

.au-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  font-size: 15px;
  font-family: inherit;
  resize: none;
  outline: none;
}

.au-textarea:focus {
  border-color: var(--el-color-primary);
}

.au-footer {
  display: flex;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.au-btn {
  flex: 1;
  padding: 13px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  border: none;
  transition: all 0.15s;
}

.au-btn.primary {
  background: var(--el-color-primary);
  color: #fff;
}

.au-btn.primary:disabled {
  opacity: 0.4;
}

.au-btn.outline {
  background: transparent;
  border: 1.5px solid var(--el-border-color);
  color: var(--el-text-color-secondary);
}

.au-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.sheet-enter-active { transition: all 0.25s ease-out; }
.sheet-leave-active { transition: all 0.2s ease-in; }
.sheet-enter-from .au-sheet,
.sheet-leave-to .au-sheet { transform: translateY(100%); }
.sheet-enter-from { opacity: 0; }
.sheet-leave-to { opacity: 0; }
</style>
