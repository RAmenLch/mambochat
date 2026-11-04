/**
 * Agent 默认头像（名称首字符）的配色方案。
 *
 * 配色桶均为「浅色背景 + 同色系深色文字」：色相 24 档均匀铺开（每档 15°），
 * 每档再配「浅底 / 稍深浅底」两种深浅，共 48 个桶，既有足够区分度又不刺眼。
 * 具体使用哪一组由 Agent 名称哈希决定，同名稳定复用同一组颜色。
 */

export interface AvatarPalette {
  /** 背景色 */
  background: string;
  /** 文字色 */
  color: string;
}

/**
 * 24 个色相（每档 15°），按步长 7 重排
 * 使相邻配色桶的色相相隔约 105°，避免相邻桶看起来像同一种颜色
 */
const HUES = Array.from({ length: 24 }, (_, i) => ((i * 7) % 24) * 15);

interface TintConfig {
  /** 背景饱和度 / 亮度 */
  bgSaturation: number;
  bgLightness: number;
  /** 文字饱和度 / 亮度 */
  fgSaturation: number;
  fgLightness: number;
}

/** 两档深浅：浅底和稍深浅底，保证同名色系一致但层次更多（文字对比度均 ≥ 4.2） */
const TINTS: TintConfig[] = [
  { bgSaturation: 78, bgLightness: 94, fgSaturation: 62, fgLightness: 30 },
  { bgSaturation: 55, bgLightness: 87, fgSaturation: 52, fgLightness: 27 },
];

const buildPalette = (tint: TintConfig): AvatarPalette[] =>
  HUES.map((hue) => ({
    background: `hsl(${hue}, ${tint.bgSaturation}%, ${tint.bgLightness}%)`,
    color: `hsl(${hue}, ${tint.fgSaturation}%, ${tint.fgLightness}%)`,
  }));

const lightTints = buildPalette(TINTS[0]);
const deepTints = buildPalette(TINTS[1]);

/** 浅底 / 深底交错铺开：相邻桶色相不同，深浅交替，48 个桶 */
export const AVATAR_PALETTE: AvatarPalette[] = lightTints.flatMap((palette, i) => [palette, deepTints[i]]);

/** FNV-1a 32bit 哈希，按码点遍历，中英文/emoji 名称都能稳定分布 */
export function hashAvatarName(name: string): number {
  let hash = 0x811c9dc5;
  for (const char of name) {
    hash ^= char.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/** 依据名称取配色桶 */
export function getAvatarPalette(name?: string | null): AvatarPalette {
  const key = (name ?? '').trim();
  if (!key) return AVATAR_PALETTE[0];
  return AVATAR_PALETTE[hashAvatarName(key) % AVATAR_PALETTE.length];
}

/** 取名称首字符（按码点切分，避免截断 emoji / 代理对） */
export function getAvatarInitial(name?: string | null): string {
  const key = (name ?? '').trim();
  if (!key) return '';
  const [first] = Array.from(key);
  return first.toUpperCase();
}
