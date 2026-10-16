<!-- frontend/mambo/src/components/chat/group/GroupMailReviewPanel.vue -->
<template>
  <div class="mail-review-panel">
    <GroupMailAttachmentViewer
      v-model:visible="viewerVisible"
      v-model:index="viewerIndex"
      :attachments="viewerAttachments"
    />
    <!-- 待审核 -->
    <div v-if="pending.length" class="review-block">
      <div class="block-head">
        <span class="block-title">
          {{ $t('groupChat.review.pendingTitle', { count: pending.length }) }}
        </span>
        <div class="block-actions">
          <el-button size="small" type="primary" :disabled="busy" @click="emit('approve-all')">
            {{ $t('groupChat.review.approveAll') }}
          </el-button>
          <el-button size="small" type="danger" plain :disabled="busy" @click="toggleBulkReject">
            {{ $t('groupChat.review.rejectAll') }}
          </el-button>
        </div>
      </div>

      <div v-if="bulkRejecting" class="reject-box">
        <el-input
          v-model="bulkReason"
          type="textarea"
          :rows="2"
          maxlength="500"
          :placeholder="$t('groupChat.review.reasonPlaceholder')"
        />
        <div class="reject-actions">
          <el-button size="small" @click="cancelBulkReject">{{ $t('groupChat.review.cancel') }}</el-button>
          <el-button
            size="small"
            type="danger"
            :disabled="!bulkReason.trim() || busy"
            @click="confirmBulkReject"
          >{{ $t('groupChat.review.confirmReject') }}</el-button>
        </div>
      </div>

      <div v-for="mail in pending" :key="mail.id" class="review-card">
        <div class="card-head">
          <span class="card-title">{{ mail.title || $t('groupChat.mail.noTitle') }}</span>
          <span class="card-meta">
            {{ mail.senderAliasSnapshot }} → {{ recipientsOf(mail) }}
          </span>
        </div>
        <div class="card-content">{{ mail.content }}</div>
        <GroupMailAttachments
          v-if="mail.attachments && mail.attachments.length"
          :attachments="mail.attachments"
          @preview="openAttachment"
        />
        <div class="card-actions">
          <el-button
            size="small"
            type="primary"
            :loading="busyId === mail.id"
            :disabled="busy"
            @click="emit('approve', mail.id)"
          >{{ $t('groupChat.review.approve') }}</el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="busy"
            @click="openReject(mail.id)"
          >{{ $t('groupChat.review.reject') }}</el-button>
        </div>
        <div v-if="rejectingId === mail.id" class="reject-box">
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="2"
            maxlength="500"
            :placeholder="$t('groupChat.review.reasonPlaceholder')"
          />
          <div class="reject-actions">
            <el-button size="small" @click="cancelReject">{{ $t('groupChat.review.cancel') }}</el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="!rejectReason.trim() || busy"
              @click="confirmReject(mail.id)"
            >{{ $t('groupChat.review.confirmReject') }}</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 已决策（被拒的默认折叠） -->
    <div v-if="decided.length" class="decided-block">
      <div class="block-title">{{ $t('groupChat.review.decidedTitle') }}</div>
      <div
        v-for="mail in decided"
        :key="mail.id"
        class="decided-item"
        :class="{ 'is-rejected': mail.state === 'rejected' }"
      >
        <div
          class="decided-row"
          :title="expandedIds.includes(mail.id) ? $t('groupChat.review.collapse') : $t('groupChat.review.expand')"
          @click="toggleExpand(mail.id)"
        >
          <el-tag size="small" :type="mail.state === 'rejected' ? 'danger' : 'success'">
            {{ mail.state === 'rejected' ? $t('groupChat.review.rejected') : $t('groupChat.review.deferred') }}
          </el-tag>
          <span class="decided-title">{{ mail.title || $t('groupChat.mail.noTitle') }}</span>
          <span v-if="mail.state === 'rejected' && mail.rejectReason" class="decided-reason">
            {{ mail.rejectReason }}
          </span>
          <el-icon class="decided-toggle">
            <ArrowUp v-if="expandedIds.includes(mail.id)" />
            <ArrowDown v-else />
          </el-icon>
        </div>
        <div v-if="expandedIds.includes(mail.id)" class="decided-body">
          <div class="card-meta">{{ mail.senderAliasSnapshot }} → {{ recipientsOf(mail) }}</div>
          <div class="card-content">{{ mail.content }}</div>
          <GroupMailAttachments
            v-if="mail.attachments && mail.attachments.length"
            :attachments="mail.attachments"
            @preview="openAttachment"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { ArrowDown, ArrowUp } from '@element-plus/icons-vue';
import type { GroupMail, GroupMailAttachment } from '@/api/types/groupChatTypes';
import GroupMailAttachmentViewer from './GroupMailAttachmentViewer.vue';
import GroupMailAttachments from './GroupMailAttachments.vue';

const props = defineProps<{
  pending: GroupMail[];
  decided: GroupMail[];
  /** 单封邮件处理中的 mailId */
  busyId?: string | null;
  /** 批量处理中（全部同意 / 全部拒绝） */
  busy?: boolean;
}>();

const emit = defineEmits<{
  (e: 'approve', mailId: string): void;
  (e: 'reject', mailId: string, reason: string): void;
  (e: 'approve-all'): void;
  (e: 'reject-all', reason: string): void;
}>();

const rejectingId = ref<string | null>(null);
const rejectReason = ref('');
const bulkRejecting = ref(false);
const bulkReason = ref('');
const expandedIds = ref<string[]>([]);

function recipientsOf(mail: GroupMail): string {
  return (mail.recipientSnapshot || []).map((r) => r.memberName).join('，');
}

const viewerVisible = ref(false);
const viewerAttachments = ref<GroupMailAttachment[]>([]);
const viewerIndex = ref(0);

function openAttachment(list: GroupMailAttachment[], index: number) {
  viewerAttachments.value = list;
  viewerIndex.value = index;
  viewerVisible.value = true;
}

function openReject(mailId: string) {
  rejectingId.value = mailId;
  rejectReason.value = '';
  bulkRejecting.value = false;
}

function cancelReject() {
  rejectingId.value = null;
  rejectReason.value = '';
}

function confirmReject(mailId: string) {
  const reason = rejectReason.value.trim();
  if (!reason) return;
  emit('reject', mailId, reason);
  cancelReject();
}

function toggleBulkReject() {
  bulkRejecting.value = !bulkRejecting.value;
  bulkReason.value = '';
  cancelReject();
}

function cancelBulkReject() {
  bulkRejecting.value = false;
  bulkReason.value = '';
}

function confirmBulkReject() {
  const reason = bulkReason.value.trim();
  if (!reason) return;
  emit('reject-all', reason);
  cancelBulkReject();
}

function toggleExpand(mailId: string) {
  const idx = expandedIds.value.indexOf(mailId);
  if (idx === -1) expandedIds.value.push(mailId);
  else expandedIds.value.splice(idx, 1);
}

// props 仅用于渲染，避免未使用告警
void props;
</script>

<style scoped>
.mail-review-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.review-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--el-color-warning-light-9);
  box-shadow: inset 0 0 0 1px var(--el-color-warning-light-5);
}
.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-warning-dark-2);
}
.block-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.review-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-bg-color);
}
.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.card-title {
  font-weight: 600;
}
.card-meta,
.decided-reason {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.card-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
}
.card-actions,
.reject-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.reject-actions {
  justify-content: flex-end;
  margin-top: 6px;
}
.reject-box {
  margin-top: 4px;
}
.decided-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.decided-item {
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}
.decided-item.is-rejected {
  background: var(--el-color-danger-light-9);
}
.decided-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
}
.decided-title {
  font-size: 13px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.decided-toggle {
  color: var(--el-text-color-secondary);
}
.decided-body {
  padding: 0 8px 8px;
}
</style>
