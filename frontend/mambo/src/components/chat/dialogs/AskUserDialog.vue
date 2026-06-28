<template>
  <el-dialog
    v-model="internalVisible"
    :title="t('chat.askUser.title')"
    width="560px"
    :close-on-click-modal="false"
    destroy-on-close
    @close="handleClose"
  >
    <el-tabs v-if="askUserSubMessages.length > 0" v-model="activeTabId">
      <el-tab-pane
        v-for="(entry, vi) in askUserSubMessages"
        :key="entry.subMsg.id"
        :label="t('chat.askUser.questionTab', { index: vi + 1, total: askUserSubMessages.length })"
        :name="entry.subMsg.id"
      >
        <div class="ask-user-form">
          <div
            v-for="(q, qIdx) in entry.content.questions"
            :key="qIdx"
            class="question-item"
          >
            <div class="question-text">
              <span class="question-index">{{ qIdx + 1 }}.</span>
              {{ q.question }}
              <el-tag v-if="q.required === false" size="small" type="info" style="margin-left: 8px">
                {{ t('chat.askUser.optional') }}
              </el-tag>
            </div>

            <template v-if="q.type === 'multiple_choice' && q.choices && q.choices.length > 0">
              <el-radio-group v-model="answersState[entry.subMsg.id][qIdx]" class="question-choices">
                <el-radio
                  v-for="choice in q.choices"
                  :key="choice.value"
                  :value="choice.value"
                  style="margin-bottom: 8px"
                >
                  {{ choice.value }}
                </el-radio>
              </el-radio-group>
              <div class="other-option">
                <el-radio
                  v-model="answersState[entry.subMsg.id][qIdx]"
                  value="__other__"
                  style="margin-bottom: 4px"
                >
                  {{ t('chat.askUser.other') }}
                </el-radio>
                <el-input
                  v-if="answersState[entry.subMsg.id][qIdx] === '__other__'"
                  v-model="otherTextsState[entry.subMsg.id][qIdx]"
                  :placeholder="t('chat.askUser.otherPlaceholder')"
                  size="small"
                  style="margin-top: 4px; margin-left: 28px; max-width: 400px"
                  @input="(val: string) => { if (val) answersState[entry.subMsg.id][qIdx] = val }"
                />
              </div>
            </template>

            <template v-else>
              <el-input
                v-model="answersState[entry.subMsg.id][qIdx]"
                type="textarea"
                :rows="2"
                :placeholder="t('chat.askUser.answerPlaceholder')"
              />
            </template>
          </div>

          <div class="tab-actions">
            <el-button
              type="primary"
              :disabled="!isTabValid(entry.subMsg.id)"
              @click="submitSingleTab(entry.subMsg.id)"
            >
              {{ t('common.action.submit') }}
            </el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-empty v-else :description="t('chat.askUser.noPending')" />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import type { AskUserContent, SubMessage } from '@/api/types';

interface ParsedAskUserEntry {
  subMsg: SubMessage;
  content: AskUserContent;
}

const props = defineProps<{
  visible: boolean;
  parentMessageId: string | null;
  /** 单合模式：指定 subMessageId（从时间线点击），null = 多合模式 */
  initialSubMessageId?: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
}>();

const { t } = useI18n();
const chatInteractionStore = useChatInteractionStore();
const sessionStore = useChatSessionStore();

const internalVisible = ref(false);
const activeTabId = ref('');

/** subMsgId → questionIndex → answer */
const answersState = ref<Record<string, string[]>>({});
/** subMsgId → questionIndex → text */
const otherTextsState = ref<Record<string, Record<number, string>>>({});

// ── 与 McpToolDialog 完全一致的 store → computed 级联模式 ──

const liveParentMessage = computed(() => {
  if (!props.parentMessageId) return null;
  return sessionStore.currentChatMessages.find(m => m.id === props.parentMessageId) || null;
});

const askUserSubMessages = computed<ParsedAskUserEntry[]>(() => {
  if (!liveParentMessage.value) return [];

  const all = liveParentMessage.value.sub_messages.filter(sm => {
    if (sm.type !== 'AskUser') return false;
    if (sm.status !== 'pending_review') return false;
    try {
      const c = JSON.parse(sm.content) as AskUserContent;
      return c.answers === null;
    } catch { return false; }
  });

  if (props.initialSubMessageId) {
    const target = all.find(sm => sm.id === props.initialSubMessageId);
    if (!target) return [];
    return [parseEntry(target)!].filter(Boolean);
  }

  return all.map(parseEntry).filter(Boolean) as ParsedAskUserEntry[];
});

function parseEntry(sm: SubMessage): ParsedAskUserEntry | null {
  try {
    const content = JSON.parse(sm.content) as AskUserContent;
    if (!content?.questions) return null;
    return { subMsg: sm, content };
  } catch { return null; }
}

// ── 校验 ──

function isTabValid(subMsgId: string): boolean {
  const ans = answersState.value[subMsgId];
  const entry = askUserSubMessages.value.find(e => e.subMsg.id === subMsgId);
  if (!entry || !ans) return false;
  return entry.content.questions.every((q, qIdx) => {
    if (q.required === false) return true;
    return (ans[qIdx] ?? '')?.trim();
  });
}

// ── 打开/关闭 ──

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal) {
    for (const entry of askUserSubMessages.value) {
      if (!answersState.value[entry.subMsg.id]) {
        answersState.value[entry.subMsg.id] = entry.content.questions.map(() => '');
      }
      if (!otherTextsState.value[entry.subMsg.id]) {
        otherTextsState.value[entry.subMsg.id] = {};
      }
    }
    if (askUserSubMessages.value.length > 0) {
      const targetId = askUserSubMessages.value.find(
        m => m.subMsg.id === props.initialSubMessageId
      ) ? props.initialSubMessageId : askUserSubMessages.value[0].subMsg.id;
      activeTabId.value = targetId || '';
    }
  }
});

watch(() => askUserSubMessages.value, (newVal) => {
  if (internalVisible.value) {
    if (newVal.length === 0) {
      emit('update:visible', false);
    } else if (!newVal.find(m => m.subMsg.id === activeTabId.value)) {
      activeTabId.value = newVal[0].subMsg.id;
    }
  }
});

function handleClose() {
  emit('update:visible', false);
}

// ── 提交 ──

function submitSingleTab(subMsgId: string) {
  if (!props.parentMessageId) return;
  const ans = answersState.value[subMsgId];
  const entry = askUserSubMessages.value.find(e => e.subMsg.id === subMsgId);
  if (!entry || !ans) return;

  const otherTexts = otherTextsState.value[subMsgId] || {};
  const finalAnswers = ans.map((a, i) => {
    if (a === '__other__') return otherTexts[i] || '';
    return a;
  });

  chatInteractionStore.submitAskUserAnswer(
    props.parentMessageId,
    subMsgId,
    finalAnswers,
    'answered'
  );
}
</script>

<style scoped>
.ask-user-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.question-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.question-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  line-height: 1.6;
}

.question-index {
  color: var(--el-color-primary);
  font-weight: 600;
}

.question-choices {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.other-option {
  margin-top: 4px;
}

.tab-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-light);
}
</style>
