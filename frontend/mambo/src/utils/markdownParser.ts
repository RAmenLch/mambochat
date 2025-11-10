// frontend/mambo/src/utils/markdownParser.ts

import MarkdownIt from 'markdown-it';
import markdownItLinkAttributes from 'markdown-it-link-attributes';
import DOMPurify from 'dompurify';

/**
 * 定义解析后的内容块的结构。
 */
export interface ParsedBlock {
  type: 'html' | 'code' | 'base64_image';
  content: string;
  language?: string;
  alt?: string;
}

/**
 * 配置并导出一个 markdown-it 实例。
 * - `breaks: true`: 将单个换行符 (\n) 渲染为 <br>。
 * - `linkify: true`: 自动将 URL 文本转换为链接。
 * - `markdown-it-link-attributes`: 为所有生成的链接添加 target="_blank" 和 rel="noopener noreferrer"。
 */
export const md = new MarkdownIt({
  html: false, // 禁止原始 HTML 标签以增强安全性
  breaks: true,
  linkify: true,
}).use(markdownItLinkAttributes, {
  attrs: {
    target: '_blank',
    rel: 'noopener noreferrer',
  },
});

// 正则表达式，用于匹配 Base64 图片的 Markdown 语法
const base64ImageRegex = /!\[(.*?)\]\((data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+)\)/g;

/**
 * 辅助函数，用于解析不含 Base64 图片的纯文本和代码块。
 * @param text - 不含 Base64 图片的 Markdown 文本。
 * @returns ParsedBlock[] - 只包含 'html' 和 'code' 类型的块。
 */
function parseTextAndCode(text: string): ParsedBlock[] {
  if (!text) return [];

  const tokens = md.parse(text, {});
  const blocks: ParsedBlock[] = [];

  // Markdown-it Token 的具体类型
  type MarkdownItToken = (typeof tokens)[number];

  let currentHtmlTokens: MarkdownItToken[] = [];

  const renderAndPushHtmlBlock = () => {
    if (currentHtmlTokens.length > 0) {
      const rawHtml = md.renderer.render(currentHtmlTokens, md.options, {});
      // 在插入到DOM前，使用DOMPurify清理HTML，防止XSS攻击
      blocks.push({
        type: 'html',
        content: DOMPurify.sanitize(rawHtml),
      });
      currentHtmlTokens = [];
    }
  };

  for (const token of tokens) {
    if (token.type === 'fence') {
      // 当前累积的HTML块结束，先进行渲染和推送
      renderAndPushHtmlBlock();
      // 推送代码块
      blocks.push({
        type: 'code',
        content: token.content,
        language: token.info.split(/\s+/g)[0], // 获取语言标识符, 如 'python'
      });
    } else {
      currentHtmlTokens.push(token);
    }
  }

  // 推送最后一个累积的HTML块
  renderAndPushHtmlBlock();

  return blocks;
}

/**
 * 将Markdown文本解析为HTML、代码块和Base64图片块的数组。
 * 此函数会先分离出Base64图片，再将剩余文本交给Markdown解析器，以避免性能问题。
 *
 * @param markdownText - 原始的Markdown格式字符串。
 * @returns ParsedBlock[] - 一个包含HTML、代码和图片块对象的数组。
 */
export function parseMarkdown(markdownText: string): ParsedBlock[] {
  if (!markdownText) return [];

  const finalBlocks: ParsedBlock[] = [];
  let lastIndex = 0;
  let match;

  // 重置正则表达式的 lastIndex，以确保从头开始匹配
  base64ImageRegex.lastIndex = 0;

  // 遍历所有匹配到的 Base64 图片
  while ((match = base64ImageRegex.exec(markdownText)) !== null) {
    // 1. 处理图片之前的所有文本
    const textBefore = markdownText.substring(lastIndex, match.index);
    if (textBefore.trim()) {
      finalBlocks.push(...parseTextAndCode(textBefore));
    }

    // 2. 将图片作为一个独立的块添加
    finalBlocks.push({
      type: 'base64_image',
      alt: match[1],      // alt text
      content: match[2],  // data:image/...
    });

    // 更新下一个搜索的起始位置
    lastIndex = base64ImageRegex.lastIndex;
  }

  // 3. 处理最后一个图片之后的所有剩余文本
  const textAfter = markdownText.substring(lastIndex);
  if (textAfter.trim()) {
    finalBlocks.push(...parseTextAndCode(textAfter));
  }

  return finalBlocks;
}
