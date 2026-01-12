import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { FileResponse, Resource } from '@/api/types';

// --- Constants ---
const DB_NAME = 'mambo_db';
const DB_VERSION = 1;

const STORE_HISTORY = 'history_store';
const STORE_INPUT_CACHE = 'input_cache_store';

// --- Types ---

/**
 * 历史记录条目在数据库中的存储结构
 */
export interface HistoryEntryDB {
  id?: number; // 自增主键
  chatId: string;
  content: string;
  timestamp: number;
  size: number; // 字节大小
  isLatest: number; // 1: true (最新), 0: false (历史)。IndexedDB 不支持 boolean 索引。
}

/**
 * 会话输入缓存条目在数据库中的存储结构
 */
export interface InputCacheEntryDB {
  chatId: string; // 主键
  isMultiPartMode: boolean;
  uploadedFiles: FileResponse[];
  attachedSubmessageResources: Resource[];
  timestamp: number; // 用于 LRU 淘汰
}

/**
 * MamboDB 数据库 Schema 定义
 */
interface MamboDB extends DBSchema {
  [STORE_HISTORY]: {
    key: number;
    value: HistoryEntryDB;
    indexes: {
      'by-chat-id': string;
      'by-timestamp': number;
      'by-is-latest': number; // Fix: boolean is not a valid IDB key type
    };
  };
  [STORE_INPUT_CACHE]: {
    key: string;
    value: InputCacheEntryDB;
    indexes: {
      'by-timestamp': number;
    };
  };
}

// --- Service Implementation ---

let dbPromise: Promise<IDBPDatabase<MamboDB>> | null = null;

/**
 * 初始化并获取数据库实例
 */
function getDB(): Promise<IDBPDatabase<MamboDB>> {
  if (!dbPromise) {
    dbPromise = openDB<MamboDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        // 创建历史记录 Store
        if (!db.objectStoreNames.contains(STORE_HISTORY)) {
          const historyStore = db.createObjectStore(STORE_HISTORY, {
            keyPath: 'id',
            autoIncrement: true,
          });
          historyStore.createIndex('by-chat-id', 'chatId');
          historyStore.createIndex('by-timestamp', 'timestamp');
          historyStore.createIndex('by-is-latest', 'isLatest');
        }

        // 创建输入缓存 Store
        if (!db.objectStoreNames.contains(STORE_INPUT_CACHE)) {
          const cacheStore = db.createObjectStore(STORE_INPUT_CACHE, {
            keyPath: 'chatId',
          });
          cacheStore.createIndex('by-timestamp', 'timestamp');
        }
      },
    });
  }
  return dbPromise;
}

// --- Exception Handling Wrapper ---

async function runWithResult<T>(operation: (db: IDBPDatabase<MamboDB>) => Promise<T>): Promise<T | null> {
  try {
    const db = await getDB();
    return await operation(db);
  } catch (error) {
    console.warn('[IndexedDB] Database operation failed:', error);
    return null;
  }
}

// --- History Operations ---

/**
 * 获取指定会话的所有历史记录，按时间升序排列
 */
export async function getHistoryByChatId(chatId: string): Promise<HistoryEntryDB[]> {
  const result = await runWithResult(async (db) => {
    return db.getAllFromIndex(STORE_HISTORY, 'by-chat-id', chatId);
  });
  return (result || []).sort((a, b) => a.timestamp - b.timestamp);
}

/**
 * 获取指定会话的历史记录数量
 */
export async function getHistoryCountByChatId(chatId: string): Promise<number> {
  const result = await runWithResult(async (db) => {
    return db.countFromIndex(STORE_HISTORY, 'by-chat-id', chatId);
  });
  return result || 0;
}

/**
 * 获取全局历史记录总数
 */
export async function getGlobalHistoryCount(): Promise<number> {
  const result = await runWithResult(async (db) => {
    return db.count(STORE_HISTORY);
  });
  return result || 0;
}

/**
 * 添加一条新的历史记录
 */
export async function addHistoryEntry(entry: HistoryEntryDB): Promise<number | null> {
  return runWithResult(async (db) => {
    return db.add(STORE_HISTORY, entry);
  });
}

/**
 * 更新历史记录（主要用于更新 isLatest 状态）
 */
export async function updateHistoryEntry(entry: HistoryEntryDB): Promise<number | null> {
  return runWithResult(async (db) => {
    return db.put(STORE_HISTORY, entry);
  });
}

/**
 * 删除指定的历史记录
 */
export async function deleteHistoryEntry(id: number): Promise<void> {
  await runWithResult(async (db) => {
    await db.delete(STORE_HISTORY, id);
  });
}

/**
 * 获取指定会话中最旧的一条历史记录
 */
export async function getOldestHistoryEntryByChatId(chatId: string): Promise<HistoryEntryDB | null> {
  return runWithResult(async (db) => {
    const cursor = await db.transaction(STORE_HISTORY).store.index('by-chat-id').openCursor(IDBKeyRange.only(chatId), 'next');
    return cursor ? cursor.value : null;
  });
}

/**
 * 获取全局最旧的一条历史记录
 */
export async function getOldestGlobalHistoryEntry(): Promise<HistoryEntryDB | null> {
  return runWithResult(async (db) => {
    const cursor = await db.transaction(STORE_HISTORY).store.index('by-timestamp').openCursor(null, 'next');
    return cursor ? cursor.value : null;
  });
}

/**
 * 获取所有非最新草稿（isLatest=0）的历史记录，按时间升序排列
 * 用于容量清理逻辑
 */
export async function getNonLatestHistoryEntries(): Promise<HistoryEntryDB[]> {
  const result = await runWithResult(async (db) => {
    // 查询 isLatest === 0 的记录
    const entries = await db.getAllFromIndex(STORE_HISTORY, 'by-is-latest', 0);
    return entries;
  });
  return (result || []).sort((a, b) => a.timestamp - b.timestamp);
}

// --- Input Cache Operations ---

/**
 * 保存会话输入缓存
 */
export async function setInputCache(entry: InputCacheEntryDB): Promise<string | null> {
  return runWithResult(async (db) => {
    return db.put(STORE_INPUT_CACHE, entry);
  });
}

/**
 * 获取指定会话的输入缓存
 */
export async function getInputCache(chatId: string): Promise<InputCacheEntryDB | undefined | null> {
  return runWithResult(async (db) => {
    return db.get(STORE_INPUT_CACHE, chatId);
  });
}

/**
 * 删除指定会话的输入缓存
 */
export async function deleteInputCache(chatId: string): Promise<void> {
  await runWithResult(async (db) => {
    await db.delete(STORE_INPUT_CACHE, chatId);
  });
}

/**
 * 获取输入缓存的总条数
 */
export async function getInputCacheCount(): Promise<number> {
  const result = await runWithResult(async (db) => {
    return db.count(STORE_INPUT_CACHE);
  });
  return result || 0;
}

/**
 * 获取最旧的输入缓存记录（用于淘汰）
 */
export async function getOldestInputCache(): Promise<InputCacheEntryDB | null> {
  return runWithResult(async (db) => {
    const cursor = await db.transaction(STORE_INPUT_CACHE).store.index('by-timestamp').openCursor(null, 'next');
    return cursor ? cursor.value : null;
  });
}
