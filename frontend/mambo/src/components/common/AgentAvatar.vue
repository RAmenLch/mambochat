<!-- frontend/mambo/src/components/common/AgentAvatar.vue -->
<template>
  <el-avatar
    :size="size"
    :shape="shape"
    :src="resolvedSrc"
    class="agent-avatar"
    :style="letterStyle"
  >
    <el-icon v-if="fallbackIcon && !initial" class="agent-avatar-fallback">
      <component :is="fallbackIcon" />
    </el-icon>
    <span v-else class="agent-avatar-letter">{{ initial }}</span>
  </el-avatar>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue';
import { getAvatarInitial, getAvatarPalette } from '@/utils/avatarColor';

const props = withDefaults(
  defineProps<{
    /** Agent 名称：无自定义头像时取首字符作为头像 */
    name?: string | null;
    /** 自定义头像地址 */
    src?: string | null;
    size?: number;
    shape?: 'circle' | 'square';
    /** 无名称时使用的图标（如内置 AI / 未知实体） */
    fallbackIcon?: Component;
  }>(),
  {
    name: '',
    src: null,
    size: 40,
    shape: 'circle',
  }
);

const resolvedSrc = computed(() => props.src || undefined);
const initial = computed(() => getAvatarInitial(props.name));
const letterStyle = computed(() => {
  const palette = getAvatarPalette(props.name);
  return {
    backgroundColor: palette.background,
    color: palette.color,
    fontSize: `${Math.max(10, Math.round(props.size * 0.44))}px`,
    fontWeight: 600,
    userSelect: 'none',
  };
});
</script>

<style scoped>
.agent-avatar-letter {
  line-height: 1;
}
</style>
