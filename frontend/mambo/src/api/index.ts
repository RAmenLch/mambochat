import axios, { isAxiosError } from 'axios';
import { ElMessage } from 'element-plus';

const apiClient = axios.create({
  // baseURL 将会指向 Vite 开发服务器的代理
  // 在生产环境中，它会指向同源的 /api 路径
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 响应拦截器, 用于全局处理 API 错误
apiClient.interceptors.response.use(
  response => response.data,
  error => {
    let errorMessage = '发生未知错误';

    if (isAxiosError(error)) {
      // 优先使用后端返回的业务错误信息
      if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      } else if (error.response) {
        // 如果没有 detail, 但有 response, 则根据状态码提供通用提示
        errorMessage = `请求错误, 状态码: ${error.response.status}`;
      } else if (error.request) {
        // 请求已发出但没有收到响应
        errorMessage = '网络错误, 请检查您的连接';
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
