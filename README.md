# Toolsets - 运维自动化工具集

- 1. Mail Listen - 邮件监听系统
- 2. SSH Agent - 网络设备自动化接口
- 3. Charts - 图表生成服务
## 项目概览

本项目目前包含以下三个独立的工具模块：

### 1. Mail Listen - 邮件监听系统

智能邮件监听和事件管理系统，支持实时监听邮箱、自动过滤处理邮件，并提供完整的告警事件管理 API。

**核心功能：**
- 🔔 实时邮件监听（IMAP IDLE / 轮询模式）
- 🎯 智能过滤规则引擎
- ⚡ 并发邮件处理
- 📊 告警事件管理和统计
- 🔌 REST API 接口
- 💾 SQLite 数据持久化

**适用场景：**
- 监控告警邮件自动化处理
- 邮件触发的工单系统
- 告警事件统计分析
- 邮件内容提取和转发

[查看详细文档 →](./mail-listen/README.md)

---

### 2. SSH Agent - 网络设备自动化接口

基于 FastAPI 和 Netmiko 的高性能网络设备自动化 API 服务，支持批量执行网络设备命令。

**核心功能：**
- 🚀 高性能并发处理
- 🔌 支持 SSH/Telnet 协议
- 🛡️ 智能错误容错
- ⚙️ 自动命令识别
- 📊 详细执行结果
- 🔧 慢速设备优化

**适用场景：**
- 批量设备配置备份
- 网络设备巡检
- 批量配置变更
- 设备信息采集
- 网络自动化运维

[查看详细文档 →](./ssh-agent/README.md)

---

### 3. Charts - 图表生成服务

美观的图表生成 API 服务，支持本地存储和 MinIO 对象存储，提供阈值高亮等高级功能。

**核心功能：**
- 📈 折线图生成
- 🎨 美观的 Ant Design 风格
- 🔴 阈值高亮显示
- 💾 本地/MinIO 双存储模式
- 🔐 API Key 认证
- 🐳 Docker 部署支持

**适用场景：**
- 监控数据可视化
- 报表图表生成
- 性能指标展示
- 告警趋势分析

[查看详细文档 →](./charts/README.md)

---

## 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器
- （可选）Docker 和 Docker Compose

### 安装步骤

每个工具都是独立的模块，可以单独安装和使用：

#### 1. Mail Listen

```bash
cd mail-listen
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 配置文件
python main.py
```

#### 2. SSH Agent

```bash
cd ssh-agent
pip install -r requirements.txt
uvicorn ssh_agent:app --host 0.0.0.0 --port 8000
```

#### 3. Charts

```bash
cd charts
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 配置文件
python charts.py
```

### Docker 部署

每个工具都提供了 Dockerfile 和 docker-compose 配置：

```bash
# Mail Listen
cd mail-listen
docker-compose up -d

# SSH Agent
cd ssh-agent
docker build -t ssh-agent .
docker run -d -p 8000:8000 ssh-agent

# Charts
cd charts
docker build -t charts-api .
docker run -d -p 38000:38000 --env-file .env charts-api
```

## 项目结构

```
toolsets/
├── mail-listen/              # 邮件监听系统
│   ├── main.py              # 主程序入口
│   ├── mail_listener.py     # 邮件监听服务
│   ├── api_server.py        # API 服务
│   ├── email_client.py      # 邮件客户端
│   ├── database.py          # 数据库操作
│   ├── filters.py           # 过滤规则
│   ├── actions.py           # 操作处理
│   ├── requirements.txt     # 依赖列表
│   ├── .env.example         # 配置示例
│   └── README.md            # 详细文档
│
├── ssh-agent/               # 网络设备自动化
│   ├── ssh_agent.py         # FastAPI 服务
│   ├── requirements.txt     # 依赖列表
│   └── README.md            # 详细文档
│
├── charts/                  # 图表生成服务
│   ├── charts.py            # FastAPI 服务
│   ├── requirements.txt     # 依赖列表
│   ├── .env.example         # 配置示例
│   └── README.md            # 详细文档
│
└── README.md                # 本文档
```

## 使用场景示例

### 场景 1：监控告警自动化处理

1. **Mail Listen** 监听监控系统发送的告警邮件
2. 根据过滤规则自动分类和处理告警
3. 通过 API 创建告警事件并记录
4. **Charts** 生成告警趋势图表
5. 统计分析告警持续时间和频率

### 场景 2：网络设备批量巡检

1. **SSH Agent** 批量连接网络设备
2. 执行巡检命令收集设备信息
3. 将巡检结果通过邮件发送
4. **Mail Listen** 接收并处理巡检报告
5. **Charts** 生成设备性能趋势图

### 场景 3：自动化配置变更

1. **Mail Listen** 接收配置变更请求邮件
2. 解析邮件内容提取变更指令
3. 调用 **SSH Agent** API 执行配置变更
4. 记录变更结果和事件
5. 生成变更报告和图表

## 技术栈

### 共同技术

- **Python 3.8+** - 主要开发语言
- **FastAPI** - 现代化 Web 框架
- **Pydantic** - 数据验证
- **Uvicorn** - ASGI 服务器
- **Docker** - 容器化部署

### 各模块特定技术

**Mail Listen:**
- IMAPClient - IMAP 协议客户端
- SQLite - 轻量级数据库
- Loguru - 日志管理
- Flask - API 服务框架

**SSH Agent:**
- Netmiko - 网络设备自动化
- Paramiko - SSH 协议实现
- ThreadPoolExecutor - 并发处理

**Charts:**
- Matplotlib - 图表绘制
- NumPy/SciPy - 数据处理
- MinIO - 对象存储（可选）

## 开发指南

### 代码规范

- 遵循 PEP 8 Python 代码规范
- 使用类型注解提高代码可读性
- 编写清晰的文档字符串
- 合理的错误处理和日志记录

### 扩展开发

每个工具都支持扩展：

**Mail Listen:**
- 自定义过滤规则
- 扩展操作类型
- 添加新的 API 接口

**SSH Agent:**
- 支持更多设备类型
- 自定义命令模板
- 添加批量操作接口

**Charts:**
- 支持更多图表类型
- 自定义图表样式
- 添加数据处理功能

### 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 常见问题

### Q: 这些工具可以单独使用吗？

A: 是的，每个工具都是独立的模块，可以单独部署和使用。它们之间没有强依赖关系。

### Q: 如何选择合适的工具？

A: 根据你的需求选择：
- 需要处理邮件和告警事件 → Mail Listen
- 需要管理网络设备 → SSH Agent
- 需要生成图表 → Charts

### Q: 支持哪些操作系统？

A: 所有工具都支持 Linux、macOS 和 Windows 系统。推荐在 Linux 环境下部署生产服务。

### Q: 如何保证安全性？

A: 建议：
- 使用环境变量管理敏感信息
- 启用 API Key 认证
- 在生产环境使用 HTTPS
- 定期更新依赖包
- 限制网络访问权限

### Q: 性能如何？

A: 
- Mail Listen: 支持并发处理，可处理大量邮件
- SSH Agent: 使用线程池，支持同时连接多个设备
- Charts: 快速生成图表，支持高并发请求

## 许可证

MIT License

## 联系方式

如有问题或建议，请通过 Issue 联系。

## 更新日志

### v1.0.0 (2025-03)
- ✨ 初始版本发布
- 📦 包含三个核心工具模块
- 📝 完整的文档和示例
- 🐳 Docker 部署支持
