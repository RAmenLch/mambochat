import axios, { isAxiosError } from 'axios';
import { ElMessage } from 'element-plus';
import i18n from '@/i18n';

const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Update the API client's base URL.
 * Called by the Electron adapter when the backend port is resolved.
 */
export function setApiBaseUrl(url: string): void {
  apiClient.defaults.baseURL = url;
}

// 响应拦截器, 用于全局处理 API 错误
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const { t } = i18n.global;
    let errorMessage = t('common.error.unknown');

    if (isAxiosError(error)) {
      const responseData = error.response?.data;

      // 优先使用 error_code 进行 i18n 映射
      if (responseData?.error_code) {
        const i18nKey = `common.backendError.${responseData.error_code}`;
        const translated = t(i18nKey);
        // 若 i18n 中没有对应 key，t() 会返回 key 本身，此时回退到 detail
        if (translated !== i18nKey) {
          errorMessage = translated;
        } else if (responseData?.detail) {
          errorMessage = responseData.detail;
        }
      }
      // 其次使用后端返回的业务错误信息
      else if (responseData?.detail) {
        errorMessage = responseData.detail;
      } else if (error.response) {
        // 如果没有 detail, 但有 response, 则根据状态码提供通用提示
        errorMessage = t('common.error.requestStatus', { status: error.response.status });
      } else if (error.request) {
        // 请求已发出但没有收到响应
        errorMessage = t('common.error.network');
      } else {
        // 设置请求时发生错误
        errorMessage = error.message;
      }
    } else if (error instanceof Error) {
      errorMessage = error.message;
    }

    ElMessage.error(errorMessage);

    // 将原始错误继续向下传递, 以便业务代码中需要捕获错误的地方(如状态回滚)可以正常工作
    return Promise.reject(error);
  }
);

export default apiClient;
