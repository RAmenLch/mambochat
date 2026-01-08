// src/types/markdown-it-katex.d.ts

declare module '@iktakahiro/markdown-it-katex' {
  import MarkdownIt from 'markdown-it';

  interface KatexOptions {
    /**
     * 是否抛出渲染错误，默认为 false
     */
    throwOnError?: boolean;
    /**
     * 错误时的颜色，默认为 #cc0000
     */
    errorColor?: string;
    /**
     * 其他 KaTeX 选项
     */
    [key: string]: any;
  }

  /**
   * markdown-it-katex 插件函数
   */
  const markdownItKatex: (md: MarkdownIt, options?: KatexOptions) => void;

  export default markdownItKatex;
}
