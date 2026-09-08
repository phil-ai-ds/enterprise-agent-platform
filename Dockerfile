# Enterprise Agent Platform —— 部署镜像（Vercel Docker / Railway / 任意容器平台）
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 依赖层（利用缓存）
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 代码与前端静态资源
COPY backend/app /app/backend/app
COPY frontend /app/frontend

# 数据落在 /tmp（serverless 容器无持久盘，冷启动 seed 重建演示数据；带 Volume 平台可改挂 /data）
ENV EAP_DATA_DIR=/tmp/eap-data \
    EAP_DATABASE_URL=sqlite:////tmp/eap.db \
    EAP_FRONTEND_DIR=/app/frontend

EXPOSE 8000

CMD ["sh", "-c", "cd /app/backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
