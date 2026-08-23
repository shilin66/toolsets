# Mail Listen - 邮件监听系统

一个邮件监听和处理系统，支持实时监听邮箱、智能过滤邮件、自动执行操作，并记录邮件基础信息。

## 功能特性

- **实时邮件监听**：支持 IMAP IDLE 模式和轮询模式，实时接收新邮件通知
- **智能过滤规则**：基于发件人、主题、内容等条件灵活配置过滤规则
- **自动化操作**：支持 API 转发、日志记录等多种操作，可扩展自定义操作
- **并发处理**：支持多线程并发处理邮件，提高处理效率
- **REST API**：提供健康检查和模板 Excel 生成接口
- **数据持久化**：使用 SQLite 数据库存储邮件记录
- **时间过滤**：支持按时间范围过滤邮件，避免处理历史邮件

## 系统架构

系统由两个主要服务组成：

1. **邮件监听服务**（Mail Listener）：负责连接邮箱、监听新邮件、应用过滤规则并执行相应操作
2. **API 服务**（API Server）：提供健康检查和模板 Excel 生成接口

## 快速开始

### Playwright RPA 登录

当前阶段提供独立的登录机器人，尚未接入邮件监听流程。账号、密码和登录地址只从环境变量读取，成功后将浏览器会话保存到
`data/rpa/auth-state.json`，供后续自动上报流程复用。

```bash
conda activate mail-listen
python -m playwright install chromium
cp .env.example .env
# 在 .env 中填写 RPA_ 登录配置及 OPENAI_COMPATIBLE_ 视觉模型配置
python -m rpa
```

Playwright 只截取验证码元素，再由本地白名单解析器计算识别出的算式。可以通过环境变量选择识别方式。

本地 RapidOCR 不访问外部接口，适合当前这种数字算术验证码：

```env
RPA_CAPTCHA_RECOGNIZER=ocr
```

OCR 模式会先识别原图；候选不符合受限算术语法时，再依次尝试灰度、
颜色阈值和放大版本。全部失败时，错误消息会列出截断后的 OCR 候选，
便于结合失败截图定位新字形。

多模态模式使用兼容 OpenAI Chat Completions 图片输入协议的视觉模型：

```env
RPA_CAPTCHA_RECOGNIZER=multimodal
OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
OPENAI_COMPATIBLE_API_KEY=replace-with-your-api-key
OPENAI_COMPATIBLE_MODEL=replace-with-your-vision-model
OPENAI_COMPATIBLE_TIMEOUT_SECONDS=120
```

`multimodal` 是默认值，并且模型必须支持图片输入。选择 `ocr` 时不要求配置
`OPENAI_COMPATIBLE_API_KEY` 和 `OPENAI_COMPATIBLE_MODEL`。

默认选择器已按“请输入用户名 / 请输入密码 / 请输入验证码 / 登录”配置。如果实际页面的验证码不是输入框后面的第一个
`img` 元素，请用浏览器开发者工具确认验证码元素，再通过 `RPA_CAPTCHA_IMAGE_SELECTOR` 覆盖。
登录失败时会先清空表单中的账号、密码和验证码，再把诊断截图写入 `data/rpa/artifacts/`。认证会话和诊断截图均已排除在 Git 之外。
如果登录前或登录后误显示“网页已禁用开发者工具”，机器人会自动刷新一次；
连续两次仍被拦截时会判定登录失败、给出明确错误并保存失败截图，绝不会把
该红字页面保存为登录成功页面。
登录成功后会等待页面触发 `load` 事件，保存完整页面截图到
`data/rpa/artifacts/login-success.png`，然后保存浏览器会话并退出。可通过
`RPA_SUCCESS_SCREENSHOT_PATH` 修改截图路径；文件会以仅当前用户可读写的权限保存。

### 环境要求

- Python 3.12+
- IMAP 邮箱账号（支持 IMAP 协议的邮箱服务）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

复制 `.env.example` 为 `.env` 并配置参数：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必需参数：

```env
# 邮箱配置
IMAP_SERVER=imap.example.com
IMAP_PORT=993
IMAP_USE_SSL=true
EMAIL_ADDRESS=your-email@example.com
EMAIL_PASSWORD=your-password

# API 配置
API_URL=https://your-api-endpoint.com
API_TOKEN=your-api-token
API_PORT=5000
API_KEY=your-api-key

# 监听配置
CHECK_INTERVAL=30
MARK_AS_READ=false
EMAIL_HOURS_FILTER=3
IMAP_IDLE_SUPPORT=true

# 并发配置
CONCURRENT_PROCESSING=true
MAX_CONCURRENT_EMAILS=10

# 日志配置
LOG_LEVEL=INFO
```

### 启动服务

```bash
# 启动完整服务（邮件监听 + API 服务）
python main.py

# 或单独启动邮件监听服务
python mail_listener.py

# 或单独启动 API 服务
python api_server.py
```

### Docker 部署

完整部署说明（环境变量加载、数据持久化、生产配置、运维命令）见 [DOCKER_DEPLOY.md](./DOCKER_DEPLOY.md)。快速开始：

```bash
# 准备配置
cp .env.example .env   # 填写邮箱、API 等配置

# 构建并启动（环境变量自动从 .env 加载）
docker compose up -d --build

# 验证
curl http://localhost:5001/health
```

## 配置说明

### 邮箱配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| IMAP_SERVER | IMAP 服务器地址 | - |
| IMAP_PORT | IMAP 端口 | 993 |
| IMAP_USE_SSL | 是否使用 SSL | true |
| EMAIL_ADDRESS | 邮箱地址 | - |
| EMAIL_PASSWORD | 邮箱密码或授权码 | - |

### 监听配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| CHECK_INTERVAL | 轮询模式检查间隔（秒） | 30 |
| MARK_AS_READ | 是否标记邮件为已读 | true |
| EMAIL_HOURS_FILTER | 只处理指定小时内的邮件（0=全部） | 0 |
| IMAP_IDLE_SUPPORT | 是否启用 IDLE 模式 | true |
| IDLE_TIMEOUT | IDLE 超时时间（秒） | 1800 |
| IDLE_CHECK_INTERVAL | IDLE 检查间隔（秒） | 30 |
| MAX_EMAILS_PER_BATCH | 每批最大处理邮件数 | 50 |

### 并发配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| CONCURRENT_PROCESSING | 是否启用并发处理 | true |
| MAX_CONCURRENT_EMAILS | 最大并发处理数 | 5 |

### API 配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| API_URL | 外部 API 地址（用于转发） | - |
| API_TOKEN | 外部 API 认证令牌 | - |
| API_PORT | 本地 API 服务端口 | 5000 |
| API_KEY | 本地 API 认证密钥 | - |
| API_TIMEOUT | API 请求超时时间（秒） | 30 |

## 过滤规则

### 规则配置

在 `filters.py` 中的 `create_default_rules()` 函数中配置默认规则：

```python
FilterRule(
    name="规则名称",
    conditions={
        "sender": {"type": "contains", "value": "example@domain.com"},
        "subject": {"type": "regex", "value": "告警|报警"}
    },
    action="api_forward",
    action_params={"priority": "high"}
)
```

### 条件类型

- `contains`：包含指定文本
- `equals`：完全匹配
- `starts_with`：以指定文本开头
- `ends_with`：以指定文本结尾
- `regex`：正则表达式匹配
- `not_contains`：不包含指定文本

### 支持的操作

- `api_forward`：转发到外部 API
- `log`：记录到日志
- `ignore`：忽略邮件

### 自定义操作

继承 `BaseAction` 类创建自定义操作：

```python
from actions import BaseAction, ActionResult

class CustomAction(BaseAction):
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        # 实现自定义逻辑
        return ActionResult(success=True, message="操作成功")

# 注册自定义操作
action_manager.register_action('custom_action', CustomAction())
```

## API 接口

所有 API 请求需要在 Header 中携带认证信息：

```
Authorization: Bearer <your-api-key>
```

### 1. 健康检查

```http
GET /health
```

响应：
```json
{
  "status": "ok",
  "message": "服务运行正常",
  "timestamp": "2025-11-10 12:00:00"
}
```

### 2. 新增工单记录

```http
POST /api/tickets
Content-Type: application/json

{
  "email_records_id": 1,
  "carrier_ticket_no": "RT123456",
  "cut_start_time": "2026-06-11 10:00:00",
  "cut_end_time": "2026-06-11 12:00:00",
  "status": "created",
  "cut_task_id": "CUT-001"
}
```

响应：
```json
{
  "success": true,
  "message": "工单记录创建成功",
  "data": {
    "id": 1,
    "email_records_id": 1,
    "status": "created",
    "carrier_ticket_no": "RT123456",
    "cut_task_id": "CUT-001",
    "cut_start_time": "2026-06-11 10:00:00",
    "cut_end_time": "2026-06-11 12:00:00",
    "update_time": "2026-06-11 12:30:00",
    "create_time": "2026-06-11 12:30:00"
  }
}
```

### 3. 查询线路表

先按 `supplier` 精确匹配 `Supplier` 列，再查询 `Supplier Circuit ID` 包含 `keywords` 任意一个关键词的数据。
线路表会在 API 服务启动时从 `data/线路表.xlsx` 加载到内存；如果更新该文件，需要重启服务后生效。

```http
POST /api/circuits/query
Content-Type: application/json

{
  "supplier": "RT",
  "keywords": ["751630", "1285332"]
}
```

响应：
```json
{
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "supplier": "RT",
      "supplier_circuit_id": "751630",
      "circuit_id": "语音电路",
      "line_type": "",
      "status":"正常",
      "remark": "中断才通知..."
    }
  ]
}
```

### 4. 生成模板 Excel

```http
GET /api/template-xlsx
```

响应：
```json
{
  "success": true,
  "message": "Excel 文件生成成功",
  "data": {
    "filename": "template.xlsx",
    "file_path": "/app/data/template.xlsx",
    "download_url": "http://localhost:5000/api/template-xlsx/download/template.xlsx"
  }
}
```

### 5. 生成并填充模板 Excel

```http
POST /api/template-xlsx
Content-Type: application/json

{
  "filename": "output.xlsx",
  "circuits": [
    {
      "客户名称": "客户A",
      "电路代号": "CIRCUIT-001"
    }
  ],
  "reasons": [
    {
      "割接线路/设备名称": "线路A",
      "割接原因": "维护"
    }
  ]
}
```

## 数据库结构

### email_records 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| email_id | INTEGER | 邮件 UID（唯一） |
| sender | TEXT | 发件人 |
| receiver | TEXT | 收件人 |
| subject | TEXT | 邮件主题 |
| subject_hash | TEXT | 邮件主题 SHA-256 |
| content | TEXT | 邮件正文 |
| content_hash | TEXT | 邮件正文 SHA-256 |
| update_time | DATETIME | 更新时间 |
| create_time | DATETIME | 创建时间 |

### ticket_records 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| email_records_id | INTEGER | 关联的 email_records.id |
| status | TEXT | 工单状态 |
| carrier_ticket_no | TEXT | 运营商单号 |
| cut_task_id | TEXT | 割接任务号 |
| cut_start_time | DATETIME | 割接开始时间 |
| cut_end_time | DATETIME | 割接结束时间 |
| update_time | DATETIME | 更新时间 |
| create_time | DATETIME | 创建时间 |

## 日志

日志文件存储在 `logs/` 目录：

- `main.log`：主服务日志
- `mail_listener.log`：邮件监听服务日志

日志配置：
- 自动按天轮转
- 保留 30 天
- 可通过 `LOG_LEVEL` 环境变量调整日志级别（DEBUG/INFO/WARNING/ERROR）

## 常见问题

### 1. 邮箱连接失败

- 检查 IMAP 服务器地址和端口是否正确
- 确认邮箱已开启 IMAP 服务
- 使用授权码而非邮箱密码（如 QQ 邮箱、Gmail 等）
- 检查防火墙和网络连接

### 2. IDLE 模式不工作

- 确认邮箱服务器支持 IDLE 命令
- 设置 `IMAP_IDLE_SUPPORT=false` 切换到轮询模式
- 调整 `IDLE_TIMEOUT` 和 `IDLE_CHECK_INTERVAL` 参数

### 3. 邮件处理缓慢

- 启用并发处理：`CONCURRENT_PROCESSING=true`
- 增加并发数：`MAX_CONCURRENT_EMAILS=10`
- 设置时间过滤：`EMAIL_HOURS_FILTER=3`（只处理 3 小时内的邮件）
- 减少 `MAX_EMAILS_PER_BATCH` 避免一次处理过多邮件

### 4. API 认证失败

- 检查 `API_KEY` 配置是否正确
- 确认请求 Header 格式：`Authorization: Bearer <api-key>`
- 查看 API 服务日志确认错误信息

## 开发指南

### 项目结构

```
mail-listen/
├── main.py                 # 主程序入口
├── mail_listener.py        # 邮件监听服务
├── api_server.py          # API 服务
├── email_client.py        # 邮件客户端
├── config.py              # 配置管理
├── models.py              # 数据模型
├── database.py            # 数据库操作
├── filters.py             # 过滤规则
├── actions.py             # 操作处理
├── custom_actions.py      # 自定义操作
├── requirements.txt       # 依赖列表
├── .env.example          # 配置示例
├── Dockerfile            # Docker 镜像
├── docker-compose.yml    # Docker Compose 配置
├── data/                 # 数据库文件
└── logs/                 # 日志文件
```

### 添加新的过滤规则

编辑 `filters.py`：

```python
def create_default_rules() -> List[FilterRule]:
    rules = [
        # 添加新规则
        FilterRule(
            name="新规则",
            conditions={
                "sender": {"type": "contains", "value": "example@domain.com"}
            },
            action="api_forward",
            action_params={"priority": "high"}
        ),
        # ... 其他规则
    ]
    return rules
```

### 扩展自定义操作

在 `custom_actions.py` 中实现：

```python
from actions import BaseAction, ActionResult
from models import EmailMessage
from typing import Dict, Any

class MyCustomAction(BaseAction):
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        # 实现自定义逻辑
        try:
            # 处理邮件
            result = self.process_email(email, params)
            return ActionResult(
                success=True,
                message="处理成功",
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"处理失败: {str(e)}"
            )
```
