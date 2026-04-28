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
  /**
   * 代码块是否已闭合。
   * markdown-it 仅对已闭合的围栏产生 fence token（此时为 true）；
   * 对于流式输出中尚未闭合的围栏，由额外检测逻辑产生（此时为 false）。
   */
  closed?: boolean
}

/**
 * markdown-it 插件：将文档开头的 YAML Frontmatter 渲染为 HTML 表格。
 * 仅匹配文档首行 `---` 开始、以 `---` 结束的围栏块，
 * 解析其中的 key: value 键值对（支持多行续行），输出为两列表格。
 */
function frontMatterTablePlugin(md: MarkdownIt) {
  md.block.ruler.before('hr', 'front_matter_table', function (state, startLine, endLine, silent) {
    // 仅匹配文档最开头、且顶层缩进为 0
    if (startLine !== 0 || state.blkIndent !== 0) return false

    // 检查第一行是否为 ---
    const firstLineStart = state.bMarks[startLine] + state.tShift[startLine]
    const firstLineEnd = state.eMarks[startLine]
    const firstLine = state.src.slice(firstLineStart, firstLineEnd).trim()
    if (firstLine !== '---') return false

    // 向下搜索闭合的 ---
    let closingLine = startLine + 1
    let found = false
    while (closingLine < endLine) {
      const pos = state.bMarks[closingLine] + state.tShift[closingLine]
      const max = state.eMarks[closingLine]
      const line = state.src.slice(pos, max).trim()
      if (line === '---') {
        found = true
        break
      }
      closingLine++
    }
    if (!found) return false
    if (silent) return true

    // 提取 frontmatter 区域的每一行
    const contentLines: string[] = []
    for (let i = startLine + 1; i < closingLine; i++) {
      const pos = state.bMarks[i] + state.tShift[i]
      const max = state.eMarks[i]
      contentLines.push(state.src.slice(pos, max))
    }

    // 解析 key: value 键值对（支持值跨多行续写）
    const entries: Array<{ key: string; value: string }> = []
    let currentKey = ''
    let currentValue = ''

    for (const line of contentLines) {
      // 非空白字符开头 + 包含冒号 → 视为新键值对
      if (line.length > 0 && line[0] !== ' ' && line[0] !== '\t') {
        const colonIdx = line.indexOf(':')
        if (colonIdx > 0) {
          if (currentKey) {
            entries.push({ key: currentKey, value: currentValue.trim() })
          }
          currentKey = line.slice(0, colonIdx).trim()
          currentValue = line.slice(colonIdx + 1).trim()
          continue
        }
      }
      // 续行：追加到当前 value
      if (currentKey) {
        currentValue += ' ' + line.trim()
      }
    }
    if (currentKey) {
      entries.push({ key: currentKey, value: currentValue.trim() })
    }

    // 构建 HTML 表格
    const escape = md.utils.escapeHtml
    let html =
      '<table class="frontmatter-table">\n<thead><tr><th>Property</th><th>Value</th></tr></thead>\n<tbody>\n'
    for (const { key, value } of entries) {
      html += `<tr><td><strong>${escape(key)}</strong></td><td>${escape(value)}</td></tr>\n`
    }
    html += '</tbody>\n</table>\n'

    // 生成 html_block token，融入 markdown-it 的标准渲染流程
    const token = state.push('html_block', '', 0)
    token.content = html
    token.map = [startLine, closingLine + 1]

    state.line = closingLine + 1
    return true
  })
}

/**
 * 配置并导出一个 markdown-it 实例。
 */
export const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
})
  .use(frontMatterTablePlugin)
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
 * 检测文本末尾是否存在未闭合的围栏代码块。
 * 流式输出时，代码块可能尚未收到闭合的 ```，markdown-it 不会将其识别为 fence token，
 * 而是作为普通段落文本处理。此函数检测这种情况并返回未闭合围栏的信息。
 *
 * @param text 完整的 Markdown 文本
 * @param baseOffset 该文本在原始完整文本中的起始偏移量
 * @param lineOffsets 行偏移量数组
 * @returns 未闭合围栏信息，如果没有则返回 null
 */
function detectUnclosedFence(
  text: string,
  baseOffset: number,
  lineOffsets: number[],
): {
  language: string
  content: string
  markup: string
  startOffset: number
  endOffset: number
} | null {
  const lines = text.split('\n')
  let inFence = false
  let fenceChar = ''
  let fenceLen = 0
  let language = ''
  let contentStartLine = -1
  let fenceStartLine = -1

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    // 按 CommonMark 规范：尾部空白不影响围栏判定
    const trimmed = line.replace(/\s+$/, '')

    if (!inFence) {
      // 匹配围栏开头：最多3空格缩进，3个及以上反引号或波浪号，可选语言标识
      const match = trimmed.match(/^( {0,3})((`{3,})|(~{3,}))(.*)/)
      if (match) {
        inFence = true
        fenceChar = match[2][0]
        fenceLen = match[2].length
        language = match[5].trim()
        contentStartLine = i + 1
        fenceStartLine = i
        continue
      }
    } else {
      // 匹配围栏闭合：相同字符，长度 >= 开头，仅允许尾部空白
      const escapedChar = fenceChar === '`' ? '`' : '~'
      const closeRegex = new RegExp(`^ {0,3}${escapedChar}{${fenceLen},}\\s*$`)
      if (closeRegex.test(trimmed)) {
        inFence = false
        continue
      }
    }
  }

  // 文本扫描完毕后仍然处于围栏内部 → 未闭合
  if (inFence && fenceStartLine >= 0) {
    const startOffset = baseOffset + (lineOffsets[fenceStartLine] ?? 0)
    const endOffset = baseOffset + text.length
    const content = lines.slice(contentStartLine).join('\n')
    return {
      language,
      content,
      markup: fenceChar.repeat(fenceLen),
      startOffset,
      endOffset,
    }
  }

  return null
}

/**
 * 辅助函数，用于解析不含 Base64 图片的纯文本和代码块。
 * @param text - 不含 Base64 图片的 Markdown 文本片段。
 * @param baseOffset - 该片段在原始完整文本中的起始偏移量。
 * @returns ParsedBlock[] - 包含位置信息的块数组。
 */
function parseTextAndCode(text: string, baseOffset: number): ParsedBlock[] {
  if (!text) return []

  // 先用完整文本检测末尾是否有未闭合的围栏代码块（流式输出场景）
  const fullLineOffsets = getLineOffsets(text)
  const unclosedFence = detectUnclosedFence(text, baseOffset, fullLineOffsets)

  let textToParse = text
  let unclosedFenceBlock: ParsedBlock | null = null

  if (unclosedFence) {
    // 只将围栏开始位置之前的文本交给 markdown-it 解析
    textToParse = text.substring(0, unclosedFence.startOffset - baseOffset)
    unclosedFenceBlock = {
      type: 'code',
      content: unclosedFence.content,
      language: unclosedFence.language,
      markup: unclosedFence.markup,
      range: {
        start: unclosedFence.startOffset,
        end: unclosedFence.endOffset,
      },
      closed: false,
    }
  }

  if (!textToParse) {
    // 整个文本都是未闭合围栏内容
    return unclosedFenceBlock ? [unclosedFenceBlock] : []
  }

  const tokens = md.parse(textToParse, {})
  const blocks: ParsedBlock[] = []
  const lineOffsets = getLineOffsets(textToParse)

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
            // 添加 svg 和 path 支持
            'svg',
            'path',
            'circle',
            'rect',
            'line',
            'polyline',
            'polygon',
            'g',
            'text',
            'foreignObject',
            'title',
            'desc',
            'defs',
            'linearGradient',
            'radialGradient',
            'stop',
            'animate',
            'animateTransform',
            'ellipse',
            'use'
          ],
          ADD_ATTR: [
            'xmlns',
            'display',
            'mathvariant',
            'class',
            'style',
            'target',
            'rel',
            // svg 相关属性
            'viewBox',
            'width',
            'height',
            'fill',
            'stroke',
            'stroke-width',
            'stroke-linecap',
            'stroke-linejoin',
            'stroke-dasharray',
            'd',
            'cx', 'cy', 'r', 'rx', 'ry',
            'x', 'y', 'x1', 'y1', 'x2', 'y2',
            'points',
            'transform',
            'text-anchor',
            'font-size',
            'font-family',
            'id',
            'opacity',
            'offset',
            'attributeName',
            'type',
            'values',
            'from',
            'to',
            'dur',
            'repeatCount',
            'href'
          ],
          USE_PROFILES: { html: true, svg: true }
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
        endOffset = baseOffset + textToParse.length
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
        closed: true,
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
    let endOffset = baseOffset + textToParse.length

    // 尝试更精确地确定结束位置
    if (lastMappedToken && lastMappedToken.map) {
      const endLine = lastMappedToken.map[1]
      if (endLine < lineOffsets.length) {
        endOffset = baseOffset + lineOffsets[endLine]
      }
    }

    renderAndPushHtmlBlock(endOffset)
  }

  // 添加未闭合的代码块（流式输出场景）
  if (unclosedFenceBlock) {
    blocks.push(unclosedFenceBlock)
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
