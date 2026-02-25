// frontend/mambo/src/utils/markdownParser.ts

import MarkdownIt from 'markdown-it'
import markdownItLinkAttributes from 'markdown-it-link-attributes'
import markdownItKatex from '@iktakahiro/markdown-it-katex'
import DOMPurify from 'dompurify'

/**
 * 定义解析后的内容块的结构。
 */
export interface ParsedBlock {
  type: 'html' | 'code' | 'base64_image'
  content: string
  language?: string
  alt?: string
  /**
   * 记录该块在原始 Markdown 字符串中的字符位置范围。
   * 用于精准定位和替换操作。
   */
  range: {
    start: number
    end: number
  }
  /**
   * 代码块的围栏字符 (如 ``` 或 ~~~)，用于编辑时保持格式一致。
   */
  markup?: string
}

/**
 * 配置并导出一个 markdown-it 实例。
 */
export const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
})
  .use(markdownItLinkAttributes, {
    attrs: {
      target: '_blank',
      rel: 'noopener noreferrer',
    },
  })
  .use(markdownItKatex)

const base64ImageRegex = /!\[(.*?)\]\((data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+)\)/g

/**
 * 计算文本中每一行的起始字符偏移量。
 * @param text 输入文本
 * @returns 偏移量数组，索引为行号，值为该行首字符在文本中的索引
 */
function getLineOffsets(text: string): number[] {
  const offsets = [0]
  let index = text.indexOf('\n')
  while (index !== -1) {
    offsets.push(index + 1)
    index = text.indexOf('\n', index + 1)
  }
  return offsets
}

/**
 * 辅助函数，用于解析不含 Base64 图片的纯文本和代码块。
 * @param text - 不含 Base64 图片的 Markdown 文本片段。
 * @param baseOffset - 该片段在原始完整文本中的起始偏移量。
 * @returns ParsedBlock[] - 包含位置信息的块数组。
 */
function parseTextAndCode(text: string, baseOffset: number): ParsedBlock[] {
  if (!text) return []

  const tokens = md.parse(text, {})
  const blocks: ParsedBlock[] = []
  const lineOffsets = getLineOffsets(text)

  type MarkdownItToken = (typeof tokens)[number]

  let currentHtmlTokens: MarkdownItToken[] = []

  /**
   * 渲染当前累积的 HTML tokens 并推送到 blocks 数组。
   * @param endOffset 当前 HTML 块的结束位置（在原始文本中的绝对偏移量）。
   */
  const renderAndPushHtmlBlock = (endOffset: number) => {
    if (currentHtmlTokens.length === 0) return

    // 计算 HTML 块的起始位置
    // 取第一个有 map 信息的 token 来确定起始行
    const firstMappedToken = currentHtmlTokens.find((t) => t.map)
    let startOffset = baseOffset

    if (firstMappedToken && firstMappedToken.map) {
      const startLine = firstMappedToken.map[0]
      startOffset = baseOffset + (lineOffsets[startLine] ?? 0)
    }

    // 只有当计算出的范围有效时才添加块
    if (startOffset < endOffset) {
      const rawHtml = md.renderer.render(currentHtmlTokens, md.options, {})
      blocks.push({
        type: 'html',
        content: DOMPurify.sanitize(rawHtml, {
          ADD_TAGS: [
            'math',
            'semantics',
            'mrow',
            'mi',
            'mo',
            'mn',
            'msup',
            'msub',
            'mfrac',
            'msqrt',
            'table',
            'tr',
            'td',
            'th',
            'tbody',
            'thead',
            'annotation',
            'annotation-xml',
          ],
          ADD_ATTR: ['xmlns', 'display', 'mathvariant', 'class', 'style', 'target', 'rel'],
        }),
        range: {
          start: startOffset,
          end: endOffset,
        },
      })
    }

    currentHtmlTokens = []
  }

  for (const token of tokens) {
    if (token.type === 'fence' && token.map) {
      // 遇到 Fence 代码块，先处理之前累积的 HTML 内容
      const fenceStartLine = token.map[0]
      const htmlEndOffset = baseOffset + (lineOffsets[fenceStartLine] ?? 0)
      renderAndPushHtmlBlock(htmlEndOffset)

      // 处理 Fence 代码块本身
      const startLine = token.map[0]
      const endLine = token.map[1] // map[1] 是结束后的下一行

      const startOffset = baseOffset + (lineOffsets[startLine] ?? 0)
      // 结束位置：结束行的上一行末尾，或者文件末尾
      let endOffset: number
      if (endLine < lineOffsets.length) {
        // 如果有下一行，结束位置就是下一行的开始位置
        endOffset = baseOffset + lineOffsets[endLine]
      } else {
        // 否则是文件末尾
        endOffset = baseOffset + text.length
      }

      blocks.push({
        type: 'code',
        content: token.content,
        language: token.info.trim(),
        markup: token.markup,
        range: {
          start: startOffset,
          end: endOffset,
        },
      })
    } else {
      // 累积普通文本/HTML token
      currentHtmlTokens.push(token)
    }
  }

  // 处理最后剩余的 HTML 块
  if (currentHtmlTokens.length > 0) {
    const lastMappedToken = currentHtmlTokens.reduceRight(
      (acc, t) => acc || t,
      null as MarkdownItToken | null,
    )
    let endOffset = baseOffset + text.length

    // 尝试更精确地确定结束位置
    if (lastMappedToken && lastMappedToken.map) {
      const endLine = lastMappedToken.map[1]
      if (endLine < lineOffsets.length) {
        endOffset = baseOffset + lineOffsets[endLine]
      }
    }

    renderAndPushHtmlBlock(endOffset)
  }

  return blocks
}

/**
 * 将Markdown文本解析为HTML、代码块和Base64图片块的数组。
 * 此函数会先分离出Base64图片，再将剩余文本交给Markdown解析器。
 *
 * @param markdownText - 原始的Markdown格式字符串。
 * @returns ParsedBlock[] - 一个包含 HTML、代码和图片块对象的数组，每个块均包含精确的位置信息。
 */
export function parseMarkdown(markdownText: string): ParsedBlock[] {
  if (!markdownText) return []

  const finalBlocks: ParsedBlock[] = []
  let lastIndex = 0
  let match

  base64ImageRegex.lastIndex = 0

  while ((match = base64ImageRegex.exec(markdownText)) !== null) {
    // 1. 处理图片之前的文本
    const textBefore = markdownText.substring(lastIndex, match.index)
    if (textBefore) {
      finalBlocks.push(...parseTextAndCode(textBefore, lastIndex))
    }

    // 2. 将图片作为一个独立的块添加
    finalBlocks.push({
      type: 'base64_image',
      alt: match[1],
      content: match[2],
      range: {
        start: match.index,
        end: base64ImageRegex.lastIndex,
      },
    })

    lastIndex = base64ImageRegex.lastIndex
  }

  // 3. 处理最后一个图片之后的所有剩余文本
  const textAfter = markdownText.substring(lastIndex)
  if (textAfter) {
    finalBlocks.push(...parseTextAndCode(textAfter, lastIndex))
  }

  return finalBlocks
}
