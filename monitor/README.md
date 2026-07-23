# 服务器监控平台

集中管理和监控 GPU 服务器运行状态。

## 架构

```
客户端 (各被监控服务器)  ──HTTP POST──▶  FastAPI 后端 (30252)  ──▶  MongoDB (内部 27017)
                                                 │
浏览器  ──HTTP──▶  FastAPI 后端 (30252)  ──▶  MongoDB
                    │
                    └── 同时托管 Vue 前端构建产物 (静态 SPA)
```

- **后端** (端口 30252): FastAPI + MongoDB。被动接收客户端上报数据，同时对外提供查询 API 并托管前端静态页面。
- **前端**: Vue.js 3 + Element Plus + ECharts。开发时通过 Vite 单独运行；生产环境构建产物输出到 `server/static/`，由后端一并伺服（SPA fallback），无需独立前端服务。
- **客户端**: Python 脚本，默认每 10 分钟采集一次系统指标并上报到服务端。
- **MongoDB**: 容器内监听 27017，宿主机映射端口 **30253**，默认**不对外暴露**（仅 Docker 内部网络通信，本地调试可在 `docker-compose.yml` 取消注释 `ports`）。

端口统一在 [.env](.env) 中配置（`FRONTEND_PORT` / `BACKEND_PORT` / `MONGODB_PORT`），改一处所有组件自动读取。

## 快速开始

### 1. 启动服务端

```bash
# 需要 Docker 和 Docker Compose
cd monitor
docker compose up -d
```

服务端启动后：
- **30252**: API 后端（接收客户端数据 + 提供前端查询接口 + 托管前端页面），同时也是浏览器访问入口。
- **30253**: MongoDB 宿主机端口（仅本机可达，用于备份/运维脚本）。

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

构建完成后重启后端容器即可加载新的静态资源：

```bash
docker compose restart server
```

然后通过 `http://<服务器IP>:30252` 访问前端页面。

开发期可用 `npm run dev` 在 30251 起热更新开发服务器（已配置 `/api` 代理到后端）。

### 3. 在被监控服务器上安装客户端

```bash
# 方式一：使用安装脚本（推荐，自动配置 systemd）
cd monitor/client
sudo bash install.sh --server http://<监控服务端IP>:30252

# 方式二：手动运行
pip3 install psutil requests
python3 monitor_client.py --server http://<监控服务端IP>:30252

# 后台运行
nohup python3 monitor_client.py --server http://<监控服务端IP>:30252 &
```

`monitor_client.py` 常用参数：
- `--server`：监控服务端地址（必填）
- `--interval`：上报间隔秒数，默认 600（10 分钟）
- `--ip`：手动指定本机展示 IP（可选）

## 运维脚本

根目录下的辅助脚本（均在宿主机直接运行，默认连接本机 30253 的 MongoDB）：

| 脚本 | 作用 |
|------|------|
| [mongo_tools.py](mongo_tools.py) | MongoDB 工具（检查 / 备份 / 还原）。备份输出为单个 archive 文件，默认写入 `mongo_backups/`。 |
| [update_user.py](update_user.py) | 服务器↔用户/公网 IP 映射管理。`sync` 从 [servers.json](servers.json) 导入映射、`show` 查看、`clear` 清空。 |
| [servers.json](servers.json) | 映射源数据：服务器 hostname → 公网 IP，以及每台服务器的归属人。 |
| [test_ports.py](test_ports.py) | 端口可达性测试工具，在前端/后端端口各起一个简单 HTTP 服务，便于从外网验证连通性。 |
| [fix_offline_gap.py](fix_offline_gap.py) | 一次性历史修复脚本（用于补齐某次故障窗口的离线空缺），日常无需运行。 |

常用运维操作：

```bash
# 查看数据库概况（集合数量、条目数、大小、日期范围）
python mongo_tools.py inspect

# 备份 MongoDB（输出单个 archive 文件）
python mongo_tools.py backup

# 从 archive 文件还原数据库
python mongo_tools.py restore /path/to/server_monitor_YYYYMMDD_HHMMSS.archive

# 同步服务器归属/公网 IP 映射到数据库（修改 servers.json 后执行）
python update_user.py sync
python update_user.py show
```

## 目录结构

```
monitor/
├── docker-compose.yml       # Docker 编排（MongoDB + FastAPI）
├── .env                     # 端口配置（前端/后端/MongoDB）
├── mongo_tools.py           # MongoDB 工具（检查 / 备份 / 还原）
├── mongo_bk.py              # 兼容入口（指向 mongo_tools.py）
├── update_user.py           # 服务器↔用户映射管理工具
├── servers.json             # 服务器归属与公网 IP 映射源数据
├── test_ports.py            # 端口可达性测试工具
├── fix_offline_gap.py       # 一次性离线空缺修复脚本
├── mongo_backups/           # 备份产物输出目录（git 忽略）
├── server/                  # Web 后端
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置（端口、在线阈值等）
│   ├── database.py          # MongoDB 连接管理 + 索引
│   ├── models.py            # 数据模型 / 主机名匹配
│   ├── routers/
│   │   ├── servers.py       # 客户端上报 API
│   │   └── monitor.py       # 前端查询 API
│   ├── static/              # Vue 构建产物（由后端托管）
│   ├── Dockerfile
│   └── requirements.txt
├── web/                     # Vue.js 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.js
│   │   ├── api/index.js     # API 请求封装
│   │   ├── views/           # 页面（Dashboard / ServerDetail）
│   │   └── components/      # 组件（ServerCard / MetricChart / GpuTable …）
│   ├── vite.config.js
│   └── package.json
└── client/                  # 客户端
    ├── monitor_client.py    # 采集 + 上报脚本
    ├── install.sh           # 一键安装 + systemd 配置
    └── requirements.txt
```

## API 接口

所有接口前缀 `/api`。

### 客户端上报（POST）

| 接口 | 说明 |
|------|------|
| `POST /api/servers/register` | 服务器注册（首次上报硬件信息） |
| `POST /api/servers/{hostname}/metrics` | 上报监控数据 |

### 前端查询（GET）

| 接口 | 说明 |
|------|------|
| `GET /api/servers` | 服务器列表（含在线状态、最新指标、公网 IP、归属人） |
| `GET /api/servers/{hostname}` | 单台服务器详情 |
| `GET /api/servers/{hostname}/metrics?hours=24` | 历史指标数据（默认 24 小时，上限 168） |
| `GET /api/servers/{hostname}/metrics/latest` | 最新一条指标 |
| `GET /api/stats/overview` | 总览统计（在线/离线数、平均 CPU/内存、GPU 总数） |
| `GET /api/offline-events?days=7` | 离线记录（相邻上报间隔 > 20 分钟视为一次离线） |
| `GET /api/gpu-overall?hours=12` | 所有服务器 GPU 平均使用率曲线（10 分钟刻度） |
| `GET /api/gpu-ranking?hours=6` | GPU 使用率排行（按平均利用率升序） |

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

## 在线/离线判定

- 在线阈值：距 `last_seen`（最近一次成功上报）不超过 `ONLINE_THRESHOLD`（默认 1205 秒 ≈ 20 分钟，可在环境变量覆盖）即视为在线。
- 离线记录（`/api/offline-events`）：相邻两条 metrics 间隔超过 20 分钟记为一次离线事件。

> 注意：当前**没有**自动过期/清理策略，历史 metrics 会一直保留在 MongoDB 中。需要时可用 `mongo_tools.py` 做备份，或手动清理旧数据。
