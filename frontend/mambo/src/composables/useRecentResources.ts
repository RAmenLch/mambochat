// frontend/mambo/src/composables/useRecentResources.ts

import { computed, ref } from 'vue';

export interface RecentResourceEntry {
  id: string;
  name: string;
  resourceType: string | null;
  lastUsedAt: number;
  useCount: number;
}

export interface RecentResourceInput {
  id: string;
  name: string;
  resourceType?: string | null;
}

const STORAGE_KEY = 'resource_selector_recent_resources_v1';
const MAX_ENTRIES = 24;

const entries = ref<RecentResourceEntry[]>([]);
let isLoaded = false;

function isValidEntry(value: unknown): value is RecentResourceEntry {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<RecentResourceEntry>;
  return typeof item.id === 'string' && item.id.length > 0 && typeof item.name === 'string';
}

function loadEntries() {
  isLoaded = true;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return;
    entries.value = parsed
      .filter(isValidEntry)
      .map((item) => ({
        id: item.id,
        name: item.name,
        resourceType: item.resourceType ?? null,
        lastUsedAt: Number(item.lastUsedAt) || 0,
        useCount: Number(item.useCount) || 1,
      }))
      .sort((a, b) => b.lastUsedAt - a.lastUsedAt)
      .slice(0, MAX_ENTRIES);
  } catch (error) {
    console.warn('[useRecentResources] Failed to load recent resources', error);
  }
}

function persistEntries() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.value));
  } catch (error) {
    console.warn('[useRecentResources] Failed to persist recent resources', error);
  }
}

function ensureLoaded() {
  if (!isLoaded) loadEntries();
}

/**
 * 记录一次资源选择/查看行为，按 id 去重并按最近使用时间倒序排列。
 */
export function recordRecentResource(input: RecentResourceInput) {
  ensureLoaded();
  if (!input?.id) return;

  const previous = entries.value.find((item) => item.id === input.id);
  const next: RecentResourceEntry = {
    id: input.id,
    name: input.name || previous?.name || '',
    resourceType: input.resourceType ?? previous?.resourceType ?? null,
    lastUsedAt: Date.now(),
    useCount: (previous?.useCount || 0) + 1,
  };

  entries.value = [next, ...entries.value.filter((item) => item.id !== input.id)].slice(0, MAX_ENTRIES);
  persistEntries();
}

export function removeRecentResource(id: string) {
  ensureLoaded();
  entries.value = entries.value.filter((item) => item.id !== id);
  persistEntries();
}

export function clearRecentResources() {
  ensureLoaded();
  entries.value = [];
  persistEntries();
}

/**
 * 最近使用的资源（内存单例，桌面端与移动端共享同一份记录）。
 */
export function useRecentResources(limit = 12) {
  ensureLoaded();

  const recentResources = computed(() => entries.value.slice(0, limit));

  return {
    recentResources,
    recordRecentResource,
    removeRecentResource,
    clearRecentResources,
  };
}
