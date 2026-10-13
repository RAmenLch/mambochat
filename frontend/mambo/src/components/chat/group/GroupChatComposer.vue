<!-- frontend/mambo/src/components/chat/group/GroupChatComposer.vue -->
<template>
  <div class="group-composer">
    <el-input
      v-model="content"
      type="textarea"
      :rows="3"
      resize="none"
      :placeholder="$t('groupChat.window.composerPlaceholder')"
      @keydown.enter.exact.prevent="onSend"
    />
    <div class="composer-footer">
      <div class="recipient-hint">
        <template v-if="mentionedNames.length">
          <el-tag v-for="n in mentionedNames" :key="n" size="small" class="recipient-tag">{{ n }}</el-tag>
        </template>
        <span v-else class="broadcast-hint">{{ $t('groupChat.window.broadcastHint') }}</span>
      </div>
      <el-button type="primary" :disabled="!content.trim()" @click="onSend">
        {{ mentionedNames.length ? $t('groupChat.window.send') : $t('groupChat.window.sendBroadcast') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { GroupMember } from '@/api/types/groupChatTypes';

const props = defineProps<{
  members: GroupMember[];
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'send', payload: { content: string; recipientNames: string[] }): void;
}>();

const content = ref('');

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * 结构化 @ 提及：按成员别名精确匹配 @别名，去重并保留成员顺序。
 * 未使用 @ 时返回空数组，后端将广播给全部成员。
 */
const mentionedNames = computed(() => {
  const text = content.value;
  if (!text.includes('@')) return [];
  const result: string[] = [];
  const seen = new Set<string>();
  for (const m of props.members) {
    const alias = m.memberAlias;
    if (!alias || seen.has(alias)) continue;
    const re = new RegExp(`@${escapeRegExp(alias)}(?=$|[\\s，,。.！!？?：:]|$)`);
    if (re.test(text)) {
      seen.add(alias);
      result.push(alias);
    }
  }
  return result;
});

function onSend() {
  const text = content.value.trim();
  if (!text) return;
  emit('send', { content: text, recipientNames: mentionedNames.value });
  content.value = '';
}
</script>

<style scoped>
.group-composer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.composer-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  gap: 12px;
}
.recipient-hint {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 22px;
  align-items: center;
}
.broadcast-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
