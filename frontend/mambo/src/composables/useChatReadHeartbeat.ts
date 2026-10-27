// frontend/mambo/src/composables/useChatReadHeartbeat.ts

import { onBeforeUnmount, onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useChatListStore } from '@/stores/chatListStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';

/** 前台停留心跳间隔（毫秒） */
const HEARTBEAT_INTERVAL = 20000;

/**
 * 当前打开的会话处于"生成中 / 待审核"时，周期推进其已读水位。
 *
 * 目的：用户在会话内实时观看期间不产生"未读"徽标；
 * 一旦切换离开（心跳停止），后续生成的内容才会被判定为未读。
 * 页面隐藏时暂停，避免后台标签页推进水位。
 */
export function useChatReadHeartbeat() {
  const chatListStore = useChatListStore();
  const sessionStore = useChatSessionStore();
  const { currentChatId } = storeToRefs(sessionStore);
  const { chatStatusMap } = storeToRefs(chatListStore);

  let timer: ReturnType<typeof setInterval> | null = null;

  const isActive = (): boolean => {
    const chatId = currentChatId.value;
    if (!chatId) return false;
    if (document.visibilityState !== 'visible') return false;
    const status = chatStatusMap.value[chatId];
    return !!status && (status.generating || status.pendingReview);
  };

  const stop = () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };

  const start = () => {
    if (timer !== null) return;
    timer = setInterval(() => {
      if (!isActive() || !currentChatId.value) {
        stop();
        return;
      }
      chatListStore.markChatRead(currentChatId.value);
    }, HEARTBEAT_INTERVAL);
  };

  const refresh = () => {
    if (isActive()) start();
    else stop();
  };

  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      if (currentChatId.value) chatListStore.markChatRead(currentChatId.value);
      refresh();
    } else {
      stop();
    }
  };

  watch(
    [currentChatId, () => chatStatusMap.value[currentChatId.value ?? '']],
    refresh,
    { immediate: true }
  );

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange);
  });

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    stop();
  });
}
