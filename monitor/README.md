# 服务器监控平台

集中管理和监控 GPU 服务器运行状态。

## 架构

```
客户端 (各服务器)  ──HTTP POST──▶  FastAPI 后端 (30252)  ──▶  MongoDB
                                                                  │
Vue.js 前端 (30251)  ──HTTP GET──▶  FastAPI 后端  ──▶  MongoDB  ──┘
```

- **Web 前端** (端口 30251): Vue.js 3 + ECharts，展示所有服务器状态和指标图表
- **Web 后端** (端口 30252): FastAPI + MongoDB，被动接收数据，不主动向客户端推送
- **客户端**: Python 脚本，每 30 分钟采集一次系统指标并上报到服务端

## 快速开始

### 1. 启动服务端

```bash
# 需要 Docker 和 Docker Compose
cd monitor
docker compose up -d
```

服务端将在以下端口启动：
- **30252**: API 后端（接收客户端数据 + 提供前端查询接口）
- MongoDB: 27017

更改后端代码后需要重建：
```bash
sudo docker compose up -d --build
```

### 2. 构建并部署前端

```bash
# 需要 Node.js >= 18
cd monitor/web
npm install
npm run build    # 构建产物输出到 ../server/static/
```

构建完成后重启后端容器即可：
```bash
docker compose restart server
```

然后通过 `http://<服务器IP>:30252` 访问前端页面。

### 3. 在被监控服务器上安装客户端

```bash
# 方式一：使用安装脚本（推荐）
cd monitor/client
sudo bash install.sh --server http://<监控服务端IP>:30252

# 方式二：手动运行
pip3 install psutil requests
python3 monitor_client.py --server http://<监控服务端IP>:30252

# 后台运行
nohup python3 monitor_client.py --server http://<监控服务端IP>:30252 &
```

## 目录结构

```
monitor/
├── docker-compose.yml       # Docker 编排（MongoDB + FastAPI）
├── server/                  # Web 后端
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置
│   ├── database.py          # MongoDB 连接管理
│   ├── models.py            # 数据模型
│   ├── routers/
│   │   ├── servers.py       # 客户端上报 API
│   │   └── monitor.py       # 前端查询 API
│   ├── Dockerfile
│   └── requirements.txt
├── web/                     # Vue.js 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── api/index.js     # API 请求封装
│   │   ├── views/           # 页面
│   │   └── components/      # 组件
│   ├── vite.config.js
│   └── package.json
└── client/                  # 客户端
    ├── monitor_client.py    # 采集 + 上报脚本
    ├── install.sh           # 一键安装 + systemd 配置
    └── requirements.txt
```

## API 接口

### 客户端上报（POST）

| 接口 | 说明 |
|------|------|
| `POST /api/servers/register` | 服务器注册（首次上报硬件信息） |
| `POST /api/servers/{hostname}/metrics` | 上报监控数据 |

### 前端查询（GET）

| 接口 | 说明 |
|------|------|
| `GET /api/servers` | 服务器列表（含在线状态） |
| `GET /api/servers/{hostname}` | 单台服务器详情 |
| `GET /api/servers/{hostname}/metrics?hours=24` | 历史指标数据 |
| `GET /api/servers/{hostname}/metrics/latest` | 最新指标 |
| `GET /api/stats/overview` | 总览统计 |

## 监控指标

| 指标 | 说明 |
|------|------|
| CPU 使用率 | 整体 CPU 使用百分比 |
| 内存使用率 | 内存使用百分比和 GB 数 |
| 磁盘使用率 | 根分区磁盘使用百分比 |
| 系统负载 | 1/5/15 分钟平均负载 |
| 网络流量 | 累计收发 MB 数 |
| GPU 使用率 | 每张 GPU 的计算和显存使用率 |
| GPU 温度 | 每张 GPU 的温度 |
| GPU 功耗 | 每张 GPU 的实时功耗 |

数据保留 7 天自动过期。
