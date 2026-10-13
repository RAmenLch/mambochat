<!-- frontend/mambo/src/components/chat/group/GroupChatCreateDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="$t('groupChat.create.title')"
    width="560px"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <el-form label-position="top" @submit.prevent>
      <el-form-item :label="$t('groupChat.create.name')">
        <el-input v-model="name" :placeholder="$t('groupChat.create.namePlaceholder')" maxlength="100" />
      </el-form-item>

      <el-form-item :label="$t('groupChat.create.autoRoundLimit')">
        <el-input-number v-model="autoRoundLimit" :min="1" :max="100000" />
      </el-form-item>

      <el-form-item :label="$t('groupChat.create.mailMode')">
        <el-select v-model="mailMode" class="mail-mode-select">
          <el-option :label="$t('groupChat.create.mailModeAuto')" value="auto" />
          <el-option :label="$t('groupChat.create.mailModeReview')" value="review" />
        </el-select>
      </el-form-item>

      <el-form-item :label="$t('groupChat.create.members')">
        <div class="member-rows">
          <div v-for="(row, idx) in members" :key="idx" class="member-row">
            <el-select
              v-model="row.agentId"
              :placeholder="$t('groupChat.create.pickAgent')"
              class="agent-select"
              filterable
              @change="() => onAgentChange(idx)"
            >
              <el-option
                v-for="opt in agentOptions"
                :key="opt.id"
                :label="opt.name"
                :value="opt.id"
              />
            </el-select>
            <el-input
              v-model="row.memberAlias"
              :placeholder="$t('groupChat.create.aliasPlaceholder')"
              class="alias-input"
              maxlength="64"
              @input="() => onAliasInput(idx)"
            />
            <el-button
              :icon="Delete"
              circle
              :disabled="members.length <= 3"
              @click="removeMember(idx)"
            />
          </div>
        </div>
        <el-button :icon="Plus" plain class="add-member-btn" @click="addMember">
          {{ $t('groupChat.create.addMember') }}
        </el-button>
        <div class="hint">{{ $t('groupChat.create.aliasHint') }}</div>
        <div v-if="duplicateAliases.length" class="hint warn">
          {{ $t('groupChat.create.aliasDuplicateHint', { aliases: duplicateAliases.join('、') }) }}
        </div>
        <div v-if="members.length < 3" class="hint warn">
          {{ $t('groupChat.create.minMembersHint') }}
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:visible', false)">{{ $t('groupChat.create.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
        {{ $t('groupChat.create.submit') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Plus, Delete } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import { createGroupChat } from '@/api/groupChatService';
import type { GroupCreatedResponse, GroupMailMode } from '@/api/types/groupChatTypes';
import { useAgentStore } from '@/stores/agentStore';

const props = defineProps<{
  visible: boolean;
  parentId?: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'created', detail: GroupCreatedResponse): void;
}>();

const { t } = useI18n();
const agentStore = useAgentStore();
const { allAgents } = storeToRefs(agentStore);

// 成员可选列表来自平铺的 allAgents（agentList 是懒加载的树缓存，未展开文件夹时为空）
const agentOptions = computed(() =>
  (allAgents.value || []).filter((a) => a.itemType === 'agent'),
);

const agentById = computed(() => {
  const map = new Map<string, { id: string; name: string }>();
  for (const a of agentOptions.value) map.set(a.id, a);
  return map;
});

/** 按别名规则清洗 Agent 名称：去控制字符与 @/英文逗号、折叠空白、NFC、截断 64 */
function sanitizeAlias(raw: string): string {
  return (raw || '')
    .normalize('NFC')
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .replace(/[@,]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 64)
    .trim();
}

/** 群内别名唯一：与其它成员已填别名冲突时追加序号 */
function uniqueAlias(base: string, selfIdx: number): string {
  const used = new Set(
    members.value
      .filter((_, i) => i !== selfIdx)
      .map((m) => sanitizeAlias(m.memberAlias))
      .filter(Boolean),
  );
  const fallback = base || t('groupChat.create.defaultMemberAlias');
  let candidate = fallback;
  let n = 2;
  while (used.has(candidate)) {
    const suffix = String(n);
    candidate = `${fallback.slice(0, 64 - suffix.length)}${suffix}`;
    n += 1;
  }
  return candidate;
}

/** 选择 Agent 时自动补充别名（别名为空或仍为自动填充时才覆盖） */
function onAgentChange(idx: number) {
  const row = members.value[idx];
  if (!row || !row.agentId) return;
  if (row.memberAlias.trim() && !row.aliasAuto) return;
  const base = sanitizeAlias(agentById.value.get(row.agentId)?.name || '');
  row.memberAlias = uniqueAlias(base, idx);
  row.aliasAuto = true;
}

/** 用户手动编辑别名后不再自动覆盖 */
function onAliasInput(idx: number) {
  const row = members.value[idx];
  if (row) row.aliasAuto = false;
}

const name = ref('');
const autoRoundLimit = ref(50);
const mailMode = ref<GroupMailMode>('auto');
const submitting = ref(false);

interface MemberRow {
  agentId: string | null;
  memberAlias: string;
  /** 别名是否仍为自动填充（用户手动编辑后置 false，切换 Agent 时才允许覆盖） */
  aliasAuto: boolean;
}

function emptyMember(): MemberRow {
  return { agentId: null, memberAlias: '', aliasAuto: false };
}

const members = ref<MemberRow[]>([emptyMember(), emptyMember(), emptyMember()]);

watch(
  () => props.visible,
  (v) => {
    if (v) {
      name.value = '';
      autoRoundLimit.value = 50;
      mailMode.value = 'auto';
      submitting.value = false;
      members.value = [emptyMember(), emptyMember(), emptyMember()];
      if (agentStore.allAgents.length === 0) {
        agentStore.fetchAllAgents();
      }
    }
  },
);

function addMember() {
  members.value.push(emptyMember());
}

function removeMember(idx: number) {
  if (members.value.length <= 3) return;
  members.value.splice(idx, 1);
}

/** 群内重复别名（会造成地址冲突） */
const duplicateAliases = computed(() => {
  const seen = new Map<string, number>();
  for (const m of members.value) {
    const key = sanitizeAlias(m.memberAlias);
    if (!key) continue;
    seen.set(key, (seen.get(key) || 0) + 1);
  }
  return Array.from(seen.entries())
    .filter(([, count]) => count > 1)
    .map(([alias]) => alias);
});

const canSubmit = computed(() => {
  if (!name.value.trim()) return false;
  if (members.value.length < 3) return false;
  if (duplicateAliases.value.length > 0) return false;
  return members.value.every((m) => !!m.agentId && !!m.memberAlias.trim());
});

async function submit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  try {
    const detail = await createGroupChat({
      name: name.value.trim(),
      parentId: props.parentId ?? null,
      autoRoundLimit: autoRoundLimit.value,
      mailMode: mailMode.value,
      members: members.value.map((m) => ({
        agentId: m.agentId as string,
        memberAlias: m.memberAlias.trim(),
      })),
    });
    ElMessage.success(t('common.msg.createSuccess'));
    emit('created', detail);
    emit('update:visible', false);
  } catch (error) {
    // 拦截器已提示错误，保留表单以便修改
    console.error('Failed to create group chat:', error);
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.member-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.mail-mode-select {
  width: 100%;
}
.member-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.agent-select {
  flex: 1 1 45%;
}
.alias-input {
  flex: 1 1 45%;
}
.add-member-btn {
  margin-top: 8px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.hint.warn {
  color: var(--el-color-warning);
}
</style>
