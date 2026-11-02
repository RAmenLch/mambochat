<!-- frontend/mambo/src/mobile/components/settings/agent/dialogs/MobilePathPickerSheet.vue — 目录 / 资源文件夹选择器（移动端） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="sheet-overlay" @click="close">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>

          <div class="sheet-header">
            <span class="sheet-title">{{ title }}</span>
            <button class="sheet-close" @click="close">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <!-- 路径导航 -->
          <div class="crumb-bar">
            <button class="crumb-home" :disabled="mode === 'resource' ? false : currentPath === '/'" @click="navigate('/')">
              {{ mode === 'resource' ? '/' : '根目录' }}
            </button>
            <template v-for="(part, idx) in breadcrumbParts" :key="idx">
              <span class="crumb-sep">/</span>
              <button class="crumb-btn" @click="navigate(part.path)">{{ part.name }}</button>
            </template>
          </div>

          <div class="pick-hint">{{ t('backend.selectedCount', { count: selected.size }) }}</div>

          <div class="sheet-body" v-loading="isLoading">
            <div v-if="loadError" class="load-error">{{ loadError }}</div>
            <div v-else-if="!isLoading && entries.length === 0" class="dir-empty">{{ t('backend.dirEmpty') }}</div>

            <div v-for="entry in entries" :key="entry.path" class="dir-row">
              <el-checkbox
                :model-value="selected.has(entry.path)"
                :disabled="!multiple && selected.size > 0 && !selected.has(entry.path)"
                class="dir-check"
                @change="() => toggle(entry.path)"
                @click.stop
              />
              <button class="dir-body" @click="openDir(entry)">
                <el-icon><Folder /></el-icon>
                <span class="dir-name">{{ entry.name }}</span>
              </button>
            </div>
          </div>

          <div class="sheet-footer">
            <button class="footer-btn" @click="close">{{ t('common.action.cancel') }}</button>
            <button class="footer-btn primary" :disabled="selected.size === 0" @click="confirm">
              {{ t('backend.confirmSelection', { count: selected.size }) }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import { Close, Folder } from '@element-plus/icons-vue'
import { listDirectory } from '@/api/backendService'
import { useResourceStore } from '@/stores/resourceStore'
import type { BackendType } from '@/api/types'

interface BackendContext {
  backendId: string | null
  hostname?: string | null
  port?: number
  username?: string | null
  password?: string | null
  rootDir?: string
}

const props = defineProps<{
  visible: boolean
  /** local / ssh 走文件系统；resource 走资源树 */
  mode: BackendType | 'resource'
  title: string
  multiple?: boolean
  context?: BackendContext
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'confirm', paths: string[]): void
}>()

const { t } = useI18n()
const resourceStore = useResourceStore()
const { resourceTree } = storeToRefs(resourceStore)

const currentPath = ref('/')
const entries = ref<Array<{ path: string; name: string }>>([])
const selected = ref<Set<string>>(new Set())
const isLoading = ref(false)
const loadError = ref('')

const breadcrumbParts = computed(() => {
  const parts = currentPath.value.split('/').filter(Boolean)
  return parts.map((name, idx) => ({ name, path: '/' + parts.slice(0, idx + 1).join('/') }))
})

function close() {
  emit('update:visible', false)
}

function toggle(path: string) {
  const next = new Set(selected.value)
  if (next.has(path)) next.delete(path)
  else {
    if (!props.multiple) next.clear()
    next.add(path)
  }
  selected.value = next
}

function confirm() {
  emit('confirm', [...selected.value])
  close()
}

function navigate(path: string) {
  currentPath.value = path || '/'
  void load()
}

function openDir(entry: { path: string; name: string }) {
  // 目录行：点击进入；同时允许勾选当前目录本身
  navigate(entry.path)
}

// --- 资源树模式 ---
function collectResourceFolders(nodes: any[] | undefined, out: Array<{ path: string; name: string }> = []) {
  if (!nodes) return out
  for (const node of nodes) {
    if (node.itemType !== 'folder') continue
    out.push({ path: node.id, name: node.name })
    if (node.children) collectResourceFolders(node.children, out)
  }
  return out
}

async function load() {
  loadError.value = ''
  if (props.mode === 'resource') {
    entries.value = collectResourceFolders(resourceTree.value as any[])
    return
  }
  isLoading.value = true
  try {
    const res = await listDirectory({
      backend_type: props.mode as BackendType,
      path: currentPath.value,
      root_dir: props.context?.rootDir || '/',
      hostname: props.context?.hostname ?? null,
      port: props.context?.port,
      username: props.context?.username ?? null,
      password: props.context?.password ?? null,
      backend_id: props.context?.backendId ?? null,
    })
    if (!res.success) {
      loadError.value = res.message || t('common.error.general')
      entries.value = []
      return
    }
    entries.value = (res.entries || [])
      .filter(e => e.is_dir)
      .map(e => ({ path: e.path, name: e.path.split('/').filter(Boolean).pop() || e.path }))
  } catch (error: any) {
    console.error('Directory listing failed:', error)
    loadError.value = error?.response?.data?.detail || t('common.error.general')
    entries.value = []
  } finally {
    isLoading.value = false
  }
}

watch(
  () => props.visible,
  visible => {
    if (!visible) return
    currentPath.value = '/'
    selected.value = new Set()
    void load()
  },
)
</script>

<style scoped>
.sheet-overlay { position: fixed; inset: 0; z-index: 2200; background: rgba(0, 0, 0, 0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 560px; max-height: 88vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0, 0, 0, 0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 16px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); }
.crumb-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; padding: 0 16px 6px; font-size: 12px; }
.crumb-home, .crumb-btn { border: none; background: transparent; color: var(--el-color-primary); font-size: 12px; padding: 2px 4px; }
.crumb-sep { color: var(--el-text-color-placeholder); }
.pick-hint { padding: 0 16px 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.sheet-body { flex: 1; min-height: 0; overflow-y: auto; padding: 0 16px 8px; }
.dir-row { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 0.5px solid var(--el-border-color-lighter); }
.dir-check { flex-shrink: 0; }
.dir-body { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; border: none; background: transparent; font-size: 14px; color: var(--el-text-color-primary); text-align: left; }
.dir-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dir-empty, .load-error { padding: 20px 0; text-align: center; font-size: 13px; color: var(--el-text-color-placeholder); }
.load-error { color: var(--el-color-danger); }
.sheet-footer { display: flex; gap: 10px; padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid var(--el-border-color-lighter); flex-shrink: 0; }
.footer-btn { flex: 1; height: 44px; font-size: 15px; font-weight: 600; border: none; border-radius: 10px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); }
.footer-btn.primary { background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); color: #fff; }
.footer-btn:disabled { opacity: 0.5; }
.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
</style>
