# Mail Listen（NOC 工作台）Docker 部署文档

本文档介绍如何使用 Docker / Docker Compose 部署 Mail Listen 服务（邮件监听 + API + 管理台一体化服务），并说明如何从 `.env` 文件加载环境变量。

## 1. 部署架构概览

| 项目 | 说明 |
|------|------|
| 基础镜像 | `python:3.12-slim` |
| 服务入口 | `python main.py`（邮件监听 + API 一体化） |
| 服务端口 | `5001`（由 `.env` 中 `API_PORT` 控制） |
| 管理台地址 | `http://<服务器IP>:5001/`（或 `/admin`） |
| 健康检查 | `GET /health` |
| 数据持久化 | 容器内 `/app/data`（SQLite 数据库、线路表、邮件附件、RPA 会话） |
| 日志持久化 | 容器内 `/app/logs` |
| 时区 | 镜像内置 `Asia/Shanghai` |

镜像构建时已内置 Playwright Chromium（RPA 登录/验证码识别使用），体积较大属正常现象。

## 2. 环境变量加载方式（.env）

应用通过以下任一方式从 `.env` 文件加载环境变量，三选一即可：

1. **Docker Compose `env_file`（推荐）**：`docker-compose.yml` 中已配置 `env_file: .env`，compose 启动时自动把 `.env` 中的变量注入容器环境。
2. **`docker run --env-file`**：裸 docker 运行时通过 `--env-file .env` 注入。
3. **挂载文件到容器**：将 `.env` 挂载为 `/app/.env`（`-v $(pwd)/.env:/app/.env`），应用内 `python-dotenv` 会在启动时自动加载该文件。

> 注意：`.env` 含邮箱密码、API Key 等敏感信息，已通过 `.dockerignore` 排除在镜像之外，**不会被打包进镜像**，只在运行时注入。

## 3. 部署前准备

### 3.1 环境要求

- Docker 20.10+，Docker Compose v2（`docker compose` 命令）
- 建议内存 ≥ 2GB（Playwright Chromium 运行时占用较高）
- 服务器可访问邮箱 IMAP/SMTP 服务器及外部 API

### 3.2 准备 .env 文件

复制示例文件并填写：

```bash
cp .env.example .env
vim .env
```

必填项（缺失会导致启动失败）：

```env
# 邮箱配置（必填）
IMAP_SERVER=imap.example.com
IMAP_PORT=993
IMAP_USE_SSL=true
EMAIL_ADDRESS=your-email@example.com
EMAIL_PASSWORD=你的授权码

# SMTP（需要邮件回复功能时必填）
SMTP_SERVER=smtp.example.com
SMTP_PORT=465
SMTP_USE_SSL=true

# API 配置（必填）
API_URL=https://your-api-endpoint.com
API_TOKEN=your-api-token
API_PORT=5001

# 管理台 API 认证密钥（前端请求 Header: Authorization: Bearer <API_KEY>）
API_KEY=your-api-key
```

常用可选项：

```env
CHECK_INTERVAL=30          # 轮询间隔（秒）
EMAIL_HOURS_FILTER=3       # 只处理最近 N 小时邮件，0 表示全部
LOG_LEVEL=INFO             # 日志级别
FE_DOMAIN=                 # 前端域名（配置后用于生成图片访问地址）
API_PUBLIC_BASE_URL=       # 本地资源 URL 的外部可访问地址
```

RPA（集团综合调度系统自动登录）相关 `RPA_*` 与 `OPENAI_COMPATIBLE_*` 变量按需配置，完整清单见 `.env.example`。

> 若修改了 `.env` 中的 `API_PORT`，compose 文件的端口映射会自动跟随（使用 `${API_PORT:-5001}` 变量插值）；裸 `docker run` 时需自行调整 `-p` 参数。

> **注意**：Docker Compose 会对 `.env` 中的 `$` 字符做变量插值（启动时出现 `The "xxx" variable is not set` 警告即为此）。若密码/令牌中含 `$`，请写成 `$$` 转义，例如 `EMAIL_PASSWORD=Abc$$123`。

## 4. 方式一：Docker Compose 部署（推荐）

### 4.1 开发/单机部署

```bash
# 构建并启动（后台运行）
docker compose up -d --build

# 查看状态与健康检查
docker compose ps

# 查看日志
docker compose logs -f mail-listener
```

说明：

- 数据与日志使用命名卷 `mail-data` / `mail-logs` 持久化，容器重建不丢数据。
- 可选的独立 API 服务（共享同一数据卷）：`docker compose --profile api-only up -d`

### 4.2 生产环境部署

生产编排使用宿主机目录挂载，便于备份：

```bash
# 创建宿主机数据目录
sudo mkdir -p /opt/mail-listener/data /opt/mail-listener/logs

# 首次部署若已有存量线路表，放入数据目录（可选，见第 6 节）
# sudo cp 线路表.xlsx /opt/mail-listener/data/

# 构建并启动
docker compose -f docker-compose.prod.yml up -d --build
```

生产配置包含：`restart: always`、日志轮转（10MB × 3 个文件）、资源限制（512MB 内存 / 0.5 CPU）。

## 5. 方式二：裸 Docker 部署

```bash
# 1. 构建镜像
docker build -t mail-listen:latest .

# 2. 运行容器（--env-file 从 .env 加载环境变量）
docker run -d \
  --name mail-listener \
  --restart unless-stopped \
  --env-file .env \
  -p 5001:5001 \
  -v mail-listen-data:/app/data \
  -v mail-listen-logs:/app/logs \
  mail-listen:latest
```

也可以改为挂载 `.env` 文件本身（应用内 `python-dotenv` 自动加载）：

```bash
docker run -d \
  --name mail-listener \
  --restart unless-stopped \
  -v $(pwd)/.env:/app/.env:ro \
  -p 5001:5001 \
  -v mail-listen-data:/app/data \
  -v mail-listen-logs:/app/logs \
  mail-listen:latest
```

## 6. 数据初始化说明

- **SQLite 数据库**：首次启动自动在 `/app/data/mail_listener.db` 创建。
- **线路表**：首次启动时若数据库为空，会把 `/app/data/线路表.xlsx` 迁移进数据库。如有存量线路表，启动前放入数据卷/挂载目录：

  ```bash
  # compose 命名卷方式：先启动一次生成卷，再拷入文件
  docker compose up -d
  docker cp 线路表.xlsx mail-listener:/app/data/线路表.xlsx
  docker compose restart
  ```

- **邮件附件**：保存在 `/app/data/email_attachments/`，随数据卷持久化。
- **Excel 模板**：镜像内自带 `template.xlsx`，管理台填报功能开箱即用。

## 7. RPA 登录（可选）

集团综合调度系统的 RPA 自动登录会话保存在 `/app/data/rpa/auth-state.json`，随数据卷持久化。如需在容器内初始化登录会话：

```bash
# .env 中需已配置 RPA_* 与 OPENAI_COMPATIBLE_* 变量
docker compose exec mail-listener python -m rpa
```

登录成功后会话自动保存，后续流程复用；验证码识别默认使用多模态模型（`RPA_CAPTCHA_RECOGNIZER=multimodal`），纯本地 OCR 可改为 `ocr`。

## 8. 验证部署

```bash
# 健康检查
curl http://localhost:5001/health
# 期望返回: {"status": "ok", ...}

# 容器健康状态
docker ps --filter name=mail-listener
```

浏览器访问 `http://<服务器IP>:5001/` 进入 NOC 工作台管理台。

## 9. 日常运维

```bash
# 查看实时日志（文件日志在 logs/ 目录，stdout 日志用以下命令）
docker compose logs -f mail-listener

# 重启服务（修改 .env 后需重启生效）
docker compose restart

# 更新部署：拉取新代码后重建镜像
docker compose up -d --build

# 停止并删除容器（数据卷保留）
docker compose down

# 备份数据（生产目录挂载方式）
tar czf mail-listener-backup-$(date +%F).tar.gz /opt/mail-listener/data
```

## 10. 常见问题

| 问题 | 排查方法 |
|------|----------|
| 启动即退出，提示配置不能为空 | `.env` 未生效：确认 compose 文件同目录下存在 `.env`，或 `docker run` 时带了 `--env-file`；用 `docker compose config` 检查变量是否注入 |
| 端口冲突 | 修改 `.env` 的 `API_PORT`（compose 会自动跟随），或修改 compose 中宿主机侧端口 |
| 健康检查一直 unhealthy | 服务启动需加载线路表/模板，`start_period` 已设 40s；仍失败则 `docker compose logs` 查看报错 |
| 邮箱连接失败 | 确认服务器到 IMAP 服务器网络可达；QQ/163 邮箱需使用授权码而非登录密码 |
| IDLE 模式异常 | `.env` 设置 `IMAP_IDLE_SUPPORT=false` 切换轮询模式后重启 |
| 管理台页面不更新 | 静态资源按文件 mtime 注入版本号，重建镜像或重启容器即可；仍异常时强制刷新浏览器 |
| 镜像构建慢 | 首次构建需下载依赖与 Chromium（约 1~2GB），后续利用层缓存会显著加快 |
