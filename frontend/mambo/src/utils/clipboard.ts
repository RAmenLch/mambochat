/**
 * 将文本复制到剪贴板，并处理不同安全上下文的兼容性问题。
 *
 * @param text 要复制的文本。
 * @returns 一个 Promise，在成功时 resolve，失败时 reject。
 */
export const copyToClipboard = (text: string): Promise<void> => {
  return new Promise((resolve, reject) => {
    // 优先使用 navigator.clipboard API (在 HTTPS 或 localhost 环境下可用)
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(resolve).catch(reject);
    } else {
      // 降级方案: 使用 document.execCommand (在 HTTP+IP 等不安全环境下可用)
      const textArea = document.createElement('textarea');
      textArea.value = text;

      // 避免在屏幕上闪烁
      textArea.style.position = 'fixed';
      textArea.style.top = '-9999px';
      textArea.style.left = '-9999px';

      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();

      try {
        const successful = document.execCommand('copy');
        if (successful) {
          resolve();
        } else {
          reject(new Error('Copy command was unsuccessful'));
        }
      } catch (err) {
        reject(err);
      }

      document.body.removeChild(textArea);
    }
  });
};
