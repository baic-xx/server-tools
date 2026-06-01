FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制代码
COPY . .

# 复制前端构建产物（由 CI 或手动构建时复制）
# COPY static/ /app/static/

# 端口由 docker-compose.yml 的 ports 和 SERVER_PORT 环境变量控制
CMD uvicorn main:app --host 0.0.0.0 --port ${SERVER_PORT:-30252}
