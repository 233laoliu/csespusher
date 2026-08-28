# ---- Stage 1: 构建前端 ----
FROM node:20-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Python 运行时（后端 + 托管前端产物） ----
# 保留与本地一致的目录结构：<root>/backend/... 与 <root>/frontend/dist
# 这样 main.py 的 Path(__file__).parent.parent.parent / "frontend" / "dist" 才能命中
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
ENV PORT=8765
EXPOSE 8765
# uvicorn 需在 backend/ 下才能导入 app 包；前端由 FastAPI 静态托管
CMD ["sh", "-c", "cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8765}"]
