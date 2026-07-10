<!-- MobileFetchModelsDialog.vue — 获取模型选择器（Bottom Sheet） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="internalVisible" class="sheet-overlay" @click="internalVisible = false">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>
          <div class="sheet-header">
            <span class="sheet-title">{{ t('model.fetch.title') }}</span>
            <button class="sheet-close" @click="internalVisible = false">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-search">
            <el-icon :size="16" class="search-icon"><Search /></el-icon>
            <input
              v-model="searchQuery"
              :placeholder="t('model.fetch.placeholder')"
              class="search-input"
            />
            <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">
              <el-icon :size="14"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-body">
            <div v-if="filteredModels.length === 0" class="sheet-empty">
              <el-empty :description="t('common.noData')" :image-size="60" />
            </div>
            <div class="model-chips">
              <button
                v-for="model in filteredModels"
                :key="model.modelId"
                class="model-chip"
                :class="{ selected: selectedIds.includes(model.modelId) }"
                @click="toggleSelection(model.modelId)"
              >
                {{ model.modelId }}
              </button>
            </div>
          </div>

          <div class="sheet-footer">
            <span class="footer-count">{{ selectedIds.length }} {{ t('model.fetch.selected') }}</span>
            <button class="footer-confirm" @click="handleConfirm">
              {{ t('model.fetch.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Search, Close } from '@element-plus/icons-vue';
import type { AIModelBase } from '@/api/types';

const props = defineProps<{
  visible: boolean;
  fetchedModels: AIModelBase[];
  existingModelIds: string[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'confirm', selectedIds: string[]): void;
}>();

const { t } = useI18n();
const searchQuery = ref('');
const selectedIds = ref<string[]>([]);

const internalVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const filteredModels = computed(() => {
  if (!searchQuery.value) return props.fetchedModels;
  return props.fetchedModels.filter(m =>
    m.modelId.toLowerCase().includes(searchQuery.value.toLowerCase())
  );
});

watch(() => props.visible, (val) => {
  if (val) {
    searchQuery.value = '';
    selectedIds.value = [...props.existingModelIds];
  }
});

const toggleSelection = (id: string) => {
  const index = selectedIds.value.indexOf(id);
  if (index > -1) selectedIds.value.splice(index, 1);
  else selectedIds.value.push(id);
};

const handleConfirm = () => {
  emit('confirm', selectedIds.value);
  internalVisible.value = false;
};
</script>

<style scoped>
.sheet-overlay { position: fixed; inset: 0; z-index: 2100; background: rgba(0,0,0,0.35); display: flex; align-items: flex-end; justify-content: center; }
.sheet-panel { width: 100%; max-width: 500px; max-height: 70vh; background: var(--el-bg-color); border-radius: 16px 16px 0 0; display: flex; flex-direction: column; overflow: hidden; }
.sheet-handle { width: 36px; height: 4px; background: rgba(0,0,0,0.15); border-radius: 2px; margin: 10px auto 0; flex-shrink: 0; }
.sheet-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 8px; flex-shrink: 0; }
.sheet-title { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.sheet-close { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: none; background: var(--el-fill-color-light); border-radius: 50%; color: var(--el-text-color-secondary); cursor: pointer; }
.sheet-search { display: flex; align-items: center; margin: 0 16px 8px; padding: 0 12px; height: 36px; background: var(--color-background-soft); border-radius: 10px; flex-shrink: 0; }
.search-icon { color: var(--el-text-color-placeholder); flex-shrink: 0; }
.search-input { flex: 1; margin-left: 6px; border: none; background: transparent; font-size: 15px; color: var(--el-text-color-primary); outline: none; font-family: inherit; }
.search-input::placeholder { color: var(--el-text-color-placeholder); }
.search-clear { display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; border: none; background: var(--el-fill-color); border-radius: 50%; color: var(--el-text-color-secondary); cursor: pointer; flex-shrink: 0; }
.sheet-body { flex: 1; overflow-y: auto; padding: 8px 16px; -webkit-overflow-scrolling: touch; }
.sheet-empty { padding: 30px 0; }
.model-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.model-chip { padding: 8px 14px; font-size: 13px; font-weight: 500; color: var(--el-text-color-primary); background: var(--color-background-soft); border: 1.5px solid transparent; border-radius: 20px; cursor: pointer; transition: all 0.15s; -webkit-tap-highlight-color: transparent; }
.model-chip.selected { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.model-chip:active { background: var(--el-fill-color); }
.sheet-footer { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; padding-bottom: max(10px, env(safe-area-inset-bottom)); border-top: 0.5px solid rgba(0,0,0,0.08); flex-shrink: 0; }
.footer-count { font-size: 14px; color: var(--el-text-color-secondary); }
.footer-confirm { height: 40px; padding: 0 28px; font-size: 15px; font-weight: 600; color: #fff; background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); border: none; border-radius: 10px; box-shadow: 0 4px 12px rgba(64,158,255,0.3); cursor: pointer; }
.footer-confirm:active { transform: scale(0.97); }

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.25s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }

@media (prefers-color-scheme: dark) {
  .sheet-handle { background: rgba(255,255,255,0.2); }
  .sheet-footer { border-top-color: rgba(255,255,255,0.08); }
}
</style>
