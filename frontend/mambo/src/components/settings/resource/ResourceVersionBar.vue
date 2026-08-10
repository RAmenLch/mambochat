<!-- frontend/mambo/src/components/settings/resource/ResourceVersionBar.vue -->
<template>
  <div class="version-top-bar">
    <div class="version-bar-header">
      <span class="version-bar-title">{{ t('resource.version.history') }}</span>
    </div>
    <el-scrollbar ref="scrollbarRef">
      <transition-group name="version-drag" tag="div" class="version-list-horizontal">
        <!-- Special KB Config Card -->
        <div
          v-if="kbId"
          key="__kb_config__"
          class="version-card-horizontal special-kb-card"
          :class="{ 'is-viewing': viewMode === 'kb_config' }"
          @click="$emit('toggle-kb-view')"
        >
          <div class="special-card-content">
            <el-icon :size="24" class="special-icon"><Setting /></el-icon>
            <span class="special-label">{{ t('resource.version.kbConfig') }}</span>
          </div>
        </div>

        <!-- Version List -->
        <template v-if="versions && versions.length > 0">
          <div
            v-for="version in versions"
            :key="version.id"
            :data-version-id="version.id"
            class="version-card-horizontal draggable-version-card"
            :class="{
              'is-active': activeVersionId === version.id,
              'is-viewing': viewMode === 'editor' && viewingVersionId === version.id,
              'is-dragging': draggedVersionId === version.id,
            }"
            draggable="true"
            @click="$emit('select-version', version)"
            @contextmenu.prevent="handleContextMenu(version, $event)"
            @dragstart="handleDragStart(version.id, $event)"
            @dragover.prevent="handleDragOver($event)"
            @dragend="handleDragEnd"
          >
            <div class="version-card-header">
              <span class="version-name" :title="version.name">{{ version.name }}</span>
              <span class="version-date">{{
                new Date(version.createdAt).toLocaleDateString()
              }}</span>
            </div>
            <div class="version-card-footer">
              <el-button
                v-if="activeVersionId !== version.id"
                type="primary"
                link
                size="small"
                @click.stop="$emit('set-active', version.id)"
              >
                {{ t('resource.version.setActive') }}
              </el-button>
              <el-tag v-else type="success" size="small" effect="plain">{{ t('resource.version.current') }}</el-tag>
            </div>
          </div>
        </template>
        <div v-else-if="!kbId" key="__empty__" class="no-versions">{{ t('resource.version.empty') }}</div>
      </transition-group>
    </el-scrollbar>

    <!-- Context Menu -->
    <teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="context-menu-overlay"
        @click="closeContextMenu"
        @contextmenu.prevent="closeContextMenu"
      />
      <div
        v-if="contextMenu.visible"
        class="version-context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <div
          class="context-menu-item"
          :class="{ 'is-disabled': contextMenu.disableDelete }"
          @click="handleDeleteClick"
        >
          <el-icon :size="14"><Delete /></el-icon>
          <span>{{ t('resource.version.delete') }}</span>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElScrollbar } from 'element-plus'
import { Setting, Delete } from '@element-plus/icons-vue'
import type { ResourceVersion } from '@/api/types'

const props = defineProps<{
  versions: ResourceVersion[]
  activeVersionId: string | null
  viewingVersionId: string | null
  kbId?: string | null
  viewMode?: 'editor' | 'kb_config'
}>()

const emit = defineEmits<{
  (e: 'select-version', version: ResourceVersion): void
  (e: 'set-active', versionId: string): void
  (e: 'toggle-kb-view'): void
  (e: 'reorder-versions', reorderedVersions: ResourceVersion[]): void
  (e: 'delete-version', versionId: string): void
}>()

const { t } = useI18n()

const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()

const draggedVersionId = ref<string | null>(null)
let lastSwapTime = 0
const SWAP_THROTTLE_MS = 150

// Context menu state
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  versionId: null as string | null,
  disableDelete: false,
})

function handleContextMenu(version: ResourceVersion, event: MouseEvent) {
  const isActive = props.activeVersionId === version.id
  const isLastOne = props.versions.length <= 1

  // Clamp position to viewport
  const menuWidth = 160
  const menuHeight = 40
  let posX = event.clientX
  let posY = event.clientY

  if (posX + menuWidth > window.innerWidth) {
    posX = window.innerWidth - menuWidth - 4
  }
  if (posY + menuHeight > window.innerHeight) {
    posY = window.innerHeight - menuHeight - 4
  }

  contextMenu.visible = true
  contextMenu.x = posX
  contextMenu.y = posY
  contextMenu.versionId = version.id
  contextMenu.disableDelete = isActive || isLastOne
}

function closeContextMenu() {
  contextMenu.visible = false
  contextMenu.versionId = null
}

function handleDeleteClick() {
  if (contextMenu.disableDelete || !contextMenu.versionId) return

  emit('delete-version', contextMenu.versionId)
  closeContextMenu()
}

const handleDragStart = (versionId: string, event: DragEvent) => {
  draggedVersionId.value = versionId
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', versionId)
  }
}

const handleDragOver = (event: DragEvent) => {
  if (!draggedVersionId.value) return

  const now = Date.now()
  if (now - lastSwapTime < SWAP_THROTTLE_MS) return

  const target = event.target as HTMLElement
  const targetCard = target.closest('.draggable-version-card') as HTMLElement | null
  if (!targetCard) return

  const targetVersionId = targetCard.dataset.versionId
  if (!targetVersionId || targetVersionId === draggedVersionId.value) return

  const list = [...props.versions]
  const draggedIndex = list.findIndex(v => v.id === draggedVersionId.value)
  const targetIndex = list.findIndex(v => v.id === targetVersionId)

  if (draggedIndex !== -1 && targetIndex !== -1) {
    const [draggedItem] = list.splice(draggedIndex, 1)
    list.splice(targetIndex, 0, draggedItem)
    emit('reorder-versions', list)
    lastSwapTime = now
  }
}

const handleDragEnd = () => {
  draggedVersionId.value = null
  lastSwapTime = 0
  scheduleScrollToActive()
}

/**
 * 将 active 版本卡片滚动到可视区域内：
 * - 已完整可见则不滚动；
 * - 不可见时以居中为目标，但 clamp 到有效滚动范围，
 *   避免居中导致视口两侧出现空白区域（靠边缘的版本贴边显示）。
 */
function scrollActiveIntoView() {
  const wrap = scrollbarRef.value?.wrapRef
  const activeId = props.activeVersionId
  if (!wrap || !activeId) return

  const card = wrap.querySelector<HTMLElement>(`[data-version-id="${activeId}"]`)
  if (!card) return

  const wrapRect = wrap.getBoundingClientRect()
  const cardRect = card.getBoundingClientRect()

  if (cardRect.left >= wrapRect.left && cardRect.right <= wrapRect.right) return

  const cardLeftInContent = cardRect.left - wrapRect.left + wrap.scrollLeft
  const target = cardLeftInContent - (wrap.clientWidth - card.clientWidth) / 2
  const maxScroll = Math.max(0, wrap.scrollWidth - wrap.clientWidth)
  const clamped = Math.max(0, Math.min(target, maxScroll))

  if (Math.abs(clamped - wrap.scrollLeft) < 1) return
  wrap.scrollTo({ left: clamped, behavior: 'smooth' })
}

function scheduleScrollToActive() {
  if (draggedVersionId.value) return
  nextTick(() => {
    requestAnimationFrame(() => scrollActiveIntoView())
  })
}

/**
 * 鼠标悬停时滚轮横向滚动版本列表。
 * 列表未溢出时不拦截滚轮，保持页面正常纵向滚动。
 */
function handleWheel(event: WheelEvent) {
  const wrap = scrollbarRef.value?.wrapRef
  if (!wrap) return
  if (wrap.scrollWidth - wrap.clientWidth <= 0) return
  event.preventDefault()
  wrap.scrollLeft += event.deltaY + event.deltaX
}

onMounted(() => {
  scheduleScrollToActive()
  scrollbarRef.value?.wrapRef?.addEventListener('wheel', handleWheel, { passive: false })
})
watch(() => props.activeVersionId, scheduleScrollToActive)
watch(() => props.versions, scheduleScrollToActive)
</script>

<style scoped>
.version-top-bar {
  flex-shrink: 0;
  height: 110px;
  border-bottom: 1px solid var(--el-border-color);
  background-color: var(--el-fill-color-lighter);
  display: flex;
  flex-direction: column;
}

.version-bar-header {
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
}

.version-list-horizontal {
  display: flex;
  padding: 0 12px 12px 12px;
  gap: 12px;
}

.version-card-horizontal {
  flex-shrink: 0;
  width: 200px;
  height: 62px;
  background-color: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.version-card-horizontal:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.version-card-horizontal.is-active {
  border-color: var(--el-color-success);
  background-color: var(--el-color-success-light-9);
}

.version-card-horizontal.is-viewing {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

.draggable-version-card {
  cursor: grab;
  user-select: none;
}

.draggable-version-card:active {
  cursor: grabbing;
}

.draggable-version-card.is-dragging {
  opacity: 0.3;
  background-color: var(--el-color-info-light-8);
  border-style: dashed;
}

.version-drag-move {
  transition: transform 0.3s ease;
}

.version-drag-leave-active {
  display: none;
}

.version-card-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
}

.version-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 8px;
}

.version-date {
  font-weight: normal;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.version-card-footer {
  display: flex;
  justify-content: flex-end;
}

.no-versions {
  padding: 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

/* Special KB Card Styles */
.special-kb-card {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
  justify-content: center;
  align-items: center;
  width: 140px; /* Slightly narrower than version cards */
}

.special-kb-card:hover {
  background-color: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}

.special-kb-card.is-viewing {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

.special-card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: var(--el-color-primary);
}

.special-label {
  font-size: 12px;
  font-weight: 600;
}

/* Context Menu */
.version-context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 150px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 4px 0;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  transition: background-color 0.15s;
}

.context-menu-item:hover:not(.is-disabled) {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.context-menu-item.is-disabled {
  color: var(--el-text-color-placeholder);
  cursor: not-allowed;
}

.context-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: transparent;
}
</style>
