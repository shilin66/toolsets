# Mail Listen - 邮件监听系统

一个功能强大的邮件监听和处理系统，支持实时监听邮箱、智能过滤邮件、自动执行操作，并提供完整的 REST API 接口用于事件管理和统计查询。

## 功能特性

- **实时邮件监听**：支持 IMAP IDLE 模式和轮询模式，实时接收新邮件通知
- **智能过滤规则**：基于发件人、主题、内容等条件灵活配置过滤规则
- **自动化操作**：支持 API 转发、日志记录等多种操作，可扩展自定义操作
- **并发处理**：支持多线程并发处理邮件，提高处理效率
- **事件管理**：完整的告警和恢复事件管理，支持事件关联和持续时间统计
- **REST API**：提供丰富的 API 接口，支持事件创建、查询和统计
- **数据持久化**：使用 SQLite 数据库存储邮件和事件记录
- **时间过滤**：支持按时间范围过滤邮件，避免处理历史邮件

## 系统架构

系统由两个主要服务组成：

1. **邮件监听服务**（Mail Listener）：负责连接邮箱、监听新邮件、应用过滤规则并执行相应操作
2. **API 服务**（API Server）：提供 REST API 接口，用于事件管理、查询和统计

## 快速开始

### 环境要求

- Python 3.8+
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

```bash
# 构建镜像
docker build -t mail-listen .

# 运行容器
docker run -d \
  --name mail-listen \
  -p 5000:5000 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  mail-listen

# 使用 docker-compose
docker-compose up -d
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

### 2. 创建告警事件

```http
POST /api/alert
Content-Type: application/json

{
  "email_id": 12345,
  "email_type": "alert",
  "event_code": "SERVER01_CPU_HIGH",
  "event_type": "node_down",
  "monitor_id": "monitor_001",
  "status": "active",
  "alert_time": "2025-11-10 12:00:00"
}
```

响应：
```json
{
  "success": true,
  "message": "告警事件创建成功",
  "data": {
    "event_id": 1,
    "email_id": 12345,
    "event_code": "SERVER01_CPU_HIGH",
    "event_type": "node_down",
    "status": "active",
    "alert_time": "2025-11-10 12:00:00"
  }
}
```

### 3. 创建恢复事件

```http
POST /api/recovery
Content-Type: application/json

{
  "email_id": 12346,
  "email_type": "recovery",
  "event_code": "SERVER01_CPU_HIGH",
  "event_type": "node_down",
  "monitor_id": "monitor_001",
  "status": "resolved",
  "recovery_time": "2025-11-10 12:05:00"
}
```

响应：
```json
{
  "success": true,
  "message": "恢复事件处理成功",
  "data": {
    "event_id": 1,
    "email_id": 12346,
    "event_code": "SERVER01_CPU_HIGH",
    "status": "resolved",
    "recovery_time": "2025-11-10 12:05:00"
  }
}
```

### 4. 查询事件

```http
GET /api/event?event_code=SERVER01_CPU_HIGH&status=active&limit=10
```

响应：
```json
{
  "success": true,
  "message": "查询成功",
  "data": [
    {
      "id": 1,
      "code": "SERVER01_CPU_HIGH",
      "type": "node_down",
      "status": "active",
      "alert_time": "2025-11-10 12:00:00",
      "recovery_time": null,
      "duration_minutes": 5.0,
      "is_timeout": false
    }
  ],
  "count": 1
}
```

### 5. 查询事件列表

```http
GET /api/events?event_type=node_down&status=active&limit=10&offset=0
```

### 6. 获取统计信息

```http
GET /api/statistics
```

响应：
```json
{
  "success": true,
  "message": "查询成功",
  "data": {
    "email_records": {
      "total": 1000,
      "today": 50,
      "type_distribution": {
        "alert": 600,
        "recovery": 400
      }
    },
    "event_records": {
      "total": 500,
      "today": 25,
      "active_alerts": 10,
      "status_distribution": {
        "active": 10,
        "resolved": 490
      },
      "type_distribution": {
        "node_down": 200,
        "hardware": 150,
        "ups_failure": 150
      }
    }
  }
}
```

### 7. 告警持续时间统计

```http
GET /api/alert-duration-stats?start_time=2025-11-01 00:00:00&end_time=2025-11-30 23:59:59&threshold_seconds=300
```

响应：
```json
{
  "success": true,
  "message": "查询成功",
  "data": {
    "start_time": "2025-11-01 00:00:00",
    "end_time": "2025-11-30 23:59:59",
    "by_type": [
      {
        "type": "node_down",
        "total_count": 50,
        "timeout_count": 15,
        "avg_duration": 520.3,
        "max_duration": 1800,
        "min_duration": 60
      }
    ]
  }
}
```

## 数据库结构

### email_records 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| email_id | INTEGER | 邮件 UID（唯一） |
| sender | TEXT | 发件人 |
| event_id | INTEGER | 关联的事件 ID |
| type | TEXT | 邮件类型（alert/recovery） |
| update_time | DATETIME | 更新时间 |
| create_time | DATETIME | 创建时间 |

### event_records 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| code | TEXT | 事件代码 |
| monitor_id | TEXT | 监控 ID |
| type | TEXT | 事件类型 |
| status | TEXT | 状态（active/resolved） |
| alert_time | DATETIME | 告警时间 |
| recovery_time | DATETIME | 恢复时间 |
| duration_seconds | INTEGER | 持续时间（秒） |
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
