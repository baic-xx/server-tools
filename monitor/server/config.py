"""服务端配置"""
import os

# MongoDB 配置
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "server_monitor")

# 服务端口
SERVER_PORT = int(os.getenv("SERVER_PORT", "30252"))

# 服务器在线判定阈值（秒）
ONLINE_THRESHOLD = int(os.getenv("ONLINE_THRESHOLD", "1205"))

# 静态文件目录（Vue 构建产物）
STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.path.dirname(__file__), "static"))

# API 前缀
API_PREFIX = "/api"
