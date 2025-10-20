// frontend/mambo/src/utils/markdownParser.ts

import MarkdownIt from 'markdown-it';
import markdownItLinkAttributes from 'markdown-it-link-attributes';
import DOMPurify from 'dompurify';

/**
 * 定义解析后的内容块的结构。
 */
export interface ParsedBlock {
  type: 'html' | 'code';
  content: string;
  language?: string;
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

/**
 * 将Markdown文本解析为HTML块和代码块的数组。
 * 代码块 (```...```) 被单独提取出来，其余部分被渲染为HTML并进行安全过滤。
 *
 * @param markdownText - 原始的Markdown格式字符串。
 * @returns ParsedBlock[] - 一个包含HTML和代码块对象的数组。
 */
export function parseMarkdown(markdownText: string): ParsedBlock[] {
  if (!markdownText) return [];

  const tokens = md.parse(markdownText, {});
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
