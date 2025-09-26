import axios from 'axios';

const apiClient = axios.create({
  // baseURL 将会指向 Vite 开发服务器的代理
  // 在生产环境中，它会指向同源的 /api 路径
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 你可以在这里添加请求或响应拦截器
// 例如，处理全局的错误提示
apiClient.interceptors.response.use(
  response => response,
  error => {
    // 简单地打印错误，后续可以替换为 ElMessage 等UI提示
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

export default apiClient;
