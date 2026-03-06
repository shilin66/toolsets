# SSH Agent - 高性能并发网络自动化接口

基于 FastAPI 和 Netmiko 的网络设备自动化 API 服务，支持通过 SSH/Telnet 协议批量执行网络设备命令。

## 功能特性

- 🚀 高性能并发处理：使用线程池处理多个设备连接
- 🔌 多协议支持：支持 SSH 和 Telnet 协议
- 🛡️ 智能错误处理：单条命令失败不影响后续命令执行
- ⚙️ 自动命令识别：自动区分配置命令和查询命令
- 📊 详细执行结果：返回每条命令的执行状态和输出
- 🔧 专家级参数优化：针对慢速设备和不稳定网络环境优化

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

```bash
uvicorn ssh_agent:app --host 0.0.0.0 --port 8000
```

服务启动后访问 API 文档：http://localhost:8000/docs

## API 使用

### 执行命令接口

**端点：** `POST /execute`

**请求示例：**

```json
{
  "host": "192.168.1.1",
  "username": "admin",
  "password": "password123",
  "secret": "enable_password",
  "device_type": "cisco_ios",
  "protocol": "ssh",
  "commands": [
    "show version",
    "show ip interface brief",
    "show running-config"
  ]
}
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| host | string | 是 | 设备 IP 地址或主机名 |
| username | string | 是 | 登录用户名 |
| password | string | 是 | 登录密码 |
| secret | string | 否 | Enable 密码（特权模式） |
| device_type | string | 否 | 设备类型，默认 `cisco_ios` |
| protocol | string | 否 | 连接协议，`ssh` 或 `telnet`，默认 `ssh` |
| commands | array | 是 | 要执行的命令列表 |

**支持的设备类型：**

- `cisco_ios` - Cisco IOS 设备
- `cisco_nxos` - Cisco Nexus 设备
- `cisco_xr` - Cisco IOS-XR 设备
- `huawei` - 华为设备
- `hp_comware` - HP Comware 设备
- 更多设备类型参考 [Netmiko 文档](https://github.com/ktbyers/netmiko)

**响应示例（成功）：**

```json
{
  "status": "completed",
  "results": [
    {
      "command": "show version",
      "output": "Cisco IOS Software...",
      "status": "success"
    },
    {
      "command": "show ip interface brief",
      "output": "Interface IP-Address...",
      "status": "success"
    }
  ]
}
```

**响应示例（连接失败）：**

```json
{
  "status": "error",
  "message": "Connection Failed: Authentication failed"
}
```

**响应示例（部分命令失败）：**

```json
{
  "status": "completed",
  "results": [
    {
      "command": "show version",
      "output": "Cisco IOS Software...",
      "status": "success"
    },
    {
      "command": "invalid command",
      "output": "Command Failed: Timeout error",
      "status": "failed"
    }
  ]
}
```

## 核心特性说明

### 智能命令识别

系统会自动识别命令类型：
- 查询命令（show/display/do/ping）：使用 `send_command` 方法
- 配置命令（包含 conf）：使用 `send_config_set` 方法

### 错误容错机制

- 单条命令执行失败不会中断整个任务
- 每条命令执行前清空缓冲区，避免数据混淆
- 连接断开时自动终止后续命令执行

### 性能优化参数

针对慢速设备和不稳定网络环境，系统配置了以下优化参数：

```python
conn_timeout: 30          # 连接超时 30 秒
auth_timeout: 30          # 认证超时 30 秒
banner_timeout: 30        # Banner 读取超时 30 秒
global_delay_factor: 4    # 全局延迟因子，适配慢速 CPU
read_timeout: 120         # 命令执行超时 120 秒
delay_factor: 2           # 命令延迟因子
```

## 使用场景

- 批量设备配置备份
- 网络设备巡检
- 批量配置变更
- 设备信息采集
- 网络自动化运维

## 技术栈

- **FastAPI** - 现代化的 Web 框架
- **Netmiko** - 网络设备自动化库
- **Paramiko** - SSH 协议实现
- **Pydantic** - 数据验证
- **Uvicorn** - ASGI 服务器

## 注意事项

1. 确保网络设备允许 SSH/Telnet 访问
2. 建议在生产环境中使用 HTTPS 和身份认证
3. 对于大量设备操作，建议实现请求队列和限流机制
4. 敏感信息（密码）建议使用环境变量或密钥管理系统

