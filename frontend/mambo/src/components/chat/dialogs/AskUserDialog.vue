<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="$t('chat.askUser.title')"
    width="560px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-if="content" class="ask-user-form">
      <div
        v-for="(q, index) in content.questions"
        :key="index"
        class="question-item"
      >
        <div class="question-text">
          <span class="question-index">{{ index + 1 }}.</span>
          {{ q.question }}
          <el-tag v-if="q.required === false" size="small" type="info" style="margin-left: 8px">
            {{ $t('chat.askUser.optional') }}
          </el-tag>
        </div>

        <!-- 多选类型 -->
        <template v-if="q.type === 'multiple_choice' && q.choices && q.choices.length > 0">
          <el-radio-group v-model="answers[index]" class="question-choices">
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
              v-model="answers[index]"
              value="__other__"
              style="margin-bottom: 4px"
            >
              {{ $t('chat.askUser.other') }}
            </el-radio>
            <el-input
              v-if="answers[index] === '__other__'"
              v-model="otherTexts[index]"
              :placeholder="$t('chat.askUser.otherPlaceholder')"
              size="small"
              style="margin-top: 4px; margin-left: 28px; max-width: 400px"
              @input="(val: string) => { if (val) answers[index] = val }"
            />
          </div>
        </template>

        <!-- 文本类型 -->
        <template v-else>
          <el-input
            v-model="answers[index]"
            type="textarea"
            :rows="2"
            :placeholder="$t('chat.askUser.answerPlaceholder')"
          />
        </template>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">
          {{ $t('common.action.cancel') }}
        </el-button>
        <el-button type="primary" @click="handleSubmit" :disabled="!isValid">
          {{ $t('common.action.submit') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import type { AskUserContent } from '@/api/types';

const props = defineProps<{
  visible: boolean;
  parentMessageId: string | null;
  subMessageId: string | null;
  askUserContent: AskUserContent | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
}>();

const { t } = useI18n();
const chatInteractionStore = useChatInteractionStore();

const content = ref<AskUserContent | null>(null);
const answers = ref<string[]>([]);
const otherTexts = ref<Record<number, string>>({});

const isValid = computed(() => {
  if (!content.value) return false;
  return content.value.questions.every((q, i) => {
    if (q.required === false) return true;
    return answers.value[i]?.trim();
  });
});

watch(
  () => props.visible,
  (newVal) => {
    if (newVal) {
      content.value = props.askUserContent;
      if (content.value) {
        answers.value = content.value.questions.map(() => '');
        otherTexts.value = {};
      }
    }
  }
);

function handleCancel() {
  if (!content.value || !props.parentMessageId || !props.subMessageId) return;

  const cancelledAnswers = content.value.questions.map(() => '');
  emit('update:visible', false);
  chatInteractionStore.submitAskUserAnswer(
    props.parentMessageId,
    props.subMessageId,
    cancelledAnswers,
    'cancelled'
  );
}

function handleSubmit() {
  if (!content.value || !props.parentMessageId || !props.subMessageId) return;

  const finalAnswers = answers.value.map((a, i) => {
    if (a === '__other__') return otherTexts.value[i] || '';
    return a;
  });
  emit('update:visible', false);
  chatInteractionStore.submitAskUserAnswer(
    props.parentMessageId,
    props.subMessageId,
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

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
