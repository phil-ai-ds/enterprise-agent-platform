# Enterprise Agent Platform —— 部署镜像（保持仓库结构）
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

# 运行时数据落在 /data（Railway Volume 挂载；本地 docker 亦可用 -v）
ENV EAP_DATA_DIR=/data \
    EAP_DATABASE_URL=sqlite:////data/eap.db \
    EAP_FRONTEND_DIR=/app/frontend

VOLUME /data
EXPOSE 8000

CMD ["sh", "-c", "cd /app/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
