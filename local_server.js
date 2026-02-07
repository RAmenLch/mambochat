// local_proxy.js
// 这是一个轻量级的 Node.js 服务器，用于替代 Docker 环境中的 Nginx
// 功能：托管前端静态文件 + 反向代理 API 请求

const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');
const history = require('connect-history-api-fallback');

const app = express();
const PORT = 24911; // 前端访问端口
const BACKEND_URL = 'http://127.0.0.1:8000'; // 后端运行端口

// 1. 启用 History API Fallback (解决 Vue 路由在刷新时 404 的问题)
app.use(history({
    rewrites: [
        { from: /^\/api\/.*$/, to: function(context) { return context.parsedUrl.path; } } // 排除 API 请求
    ]
}));

// 2. 配置反向代理 (对应 Nginx 的 location /api/)
app.use('/api', createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true, // 支持 WebSocket
    pathRewrite: {
        // 如果后端不需要 /api 前缀，可以在这里去掉，但你的项目似乎保留了 /api
    },
    onProxyReq: (proxyReq, req, res) => {
        // 禁用缓存，防止流式响应卡顿
        proxyReq.setHeader('Cache-Control', 'no-cache');
    },
    onError: (err, req, res) => {
        console.error('Proxy Error:', err);
        res.status(500).send('Backend connection error. Is Python running?');
    }
}));

// 3. 托管静态文件 (对应 Nginx 的 root /usr/share/nginx/html)
// 指向 frontend/mambo/dist 目录
const distPath = path.join(__dirname, 'frontend', 'mambo', 'dist');
app.use(express.static(distPath));

// 启动服务
app.listen(PORT, () => {
    console.log(`\n==================================================`);
    console.log(`  Mambo Chat 本地版已启动!`);
    console.log(`  访问地址: http://localhost:${PORT}`);
    console.log(`==================================================\n`);
});
