// frontend/mambo/src/utils/fileIcons.ts

import {
  Document,
  Picture as PictureIcon,
  Headset,
  Film,
  Folder,
  Tickets,
} from '@element-plus/icons-vue';
import type { Component } from 'vue';

// 定义MIME类型到图标的映射关系
const mimeTypeIconMap: { [key: string]: Component } = {
  'application/pdf': Document,
  'application/zip': Folder,
  'application/x-rar-compressed': Folder,
  'application/vnd.ms-excel': Tickets,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': Tickets,
  'application/msword': Document,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': Document,
  'application/vnd.ms-powerpoint': Document,
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': Document,
};

/**
 * 根据文件的MIME类型返回一个合适的图标组件。
 *
 * @param mimeType - 文件的MIME类型字符串。
 * @returns 一个Vue组件，用于渲染图标。
 */
export function getIconForMimeType(mimeType: string): Component {
  // 检查精确匹配
  if (mimeTypeIconMap[mimeType]) {
    return mimeTypeIconMap[mimeType];
  }

  // 检查通用类型匹配
  if (mimeType.startsWith('image/')) {
    return PictureIcon;
  }
  if (mimeType.startsWith('audio/')) {
    return Headset;
  }
  if (mimeType.startsWith('video/')) {
    return Film;
  }
  if (mimeType.startsWith('text/')) {
    return Document;
  }

  // 默认图标
  return Document;
}
