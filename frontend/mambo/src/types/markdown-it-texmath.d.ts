// src/types/markdown-it-texmath.d.ts

declare module 'markdown-it-texmath' {
  import MarkdownIt = require('markdown-it')

  type Delimiter =
    | 'dollars'
    | 'brackets'
    | 'doxygen'
    | 'gitlab'
    | 'julia'
    | 'kramdown'
    | 'beg_end'

  interface Rule {
    /** 注册到 markdown-it 的规则名，同时用作 renderer 规则名 */
    name: string
    /** 带 g/y 标记的正则，匹配内容放在第 1 个捕获组 */
    rex: RegExp
    /** 渲染模板，`$1` 为公式内容、`$2` 为公式编号 */
    tmpl: string
    /** 起始分隔符，用于快速前置判断 */
    tag: string
    displayMode?: boolean
    outerSpace?: boolean
    pre?: (str: string, outerSpace: boolean, pos: number) => boolean
    post?: (str: string, outerSpace: boolean, end: number) => boolean
  }

  interface RuleSet {
    inline: Rule[]
    block: Rule[]
  }

  interface Delimiters {
    inline: Rule[]
    block: Rule[]
  }

  /** 实际传入的是 KaTeX 模块对象 */
  type RenderEngine = {
    renderToString(tex: string, options?: Record<string, unknown>): string
  }

  interface TexMathOptions {
    engine?: RenderEngine
    delimiters?: Delimiter | Delimiter[]
    katexOptions?: Record<string, unknown>
    macros?: Record<string, string>
    /** 行内公式是否要求两侧为空格（仅 dollars 生效） */
    outerSpace?: boolean
  }

  type MarkdownItBlockRule = (
    state: any,
    startLine: number,
    endLine: number,
    silent: boolean,
  ) => boolean

  type MarkdownItInlineRule = (state: any, silent: boolean) => boolean

  function texmath(md: MarkdownIt, options?: TexMathOptions): void

  namespace texmath {
    const rules: Record<Delimiter, RuleSet>
    const katex: RenderEngine
    const inlineRuleNames: string[]
    const blockRuleNames: string[]
    function mergeDelimiters(delims?: Delimiter | Delimiter[]): Delimiters
    function inline(rule: Rule): MarkdownItInlineRule
    function block(rule: Rule): MarkdownItBlockRule
    function render(tex: string, displayMode: boolean, options: Record<string, unknown>): string
  }

  export = texmath
}
