# frontend/mambo/Dockerfile

# --- Stage 1: Build Stage ---
# 使用 Node.js 22-alpine 镜像作为构建环境
FROM node:22-alpine AS builder

# 设置工作目录
WORKDIR /app

# 复制 package.json 和 package-lock.json
COPY package*.json ./

# 安装项目依赖
RUN npm install

# 复制所有前端源代码
COPY . .

# 执行构建命令，生成静态文件到 dist 目录
RUN npm run build


# --- Stage 2: Production Stage ---
# 使用轻量的 Nginx 镜像作为最终的生产环境
FROM nginx:stable-alpine

# 从构建阶段（builder）复制构建好的静态文件到 Nginx 的网站根目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制自定义的 Nginx 配置文件
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露 80 端口
EXPOSE 80

# Nginx 默认的启动命令会由基础镜像执行，无需我们再写 CMD
