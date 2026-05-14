# Charts API

图表生成服务，支持本地存储、MinIO 对象存储和自定义上传接口三种模式。

## 功能特性

- 生成美观的图表(目前仅支持折线图)
- 支持阈值高亮显示
- 灵活的存储方式：本地文件系统、MinIO 对象存储或自定义上传接口
- API Key 认证保护

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并根据需要修改配置：

```bash
cp .env.example .env
```

### 3. 配置说明

#### 本地存储模式（默认）

```env
STORAGE_TYPE=local
CHART_API_KEY=your-secret-key
```

图片将保存在 `imgs/` 目录下，API 返回相对路径如 `/imgs/2024-01-01/abc123.png`

#### MinIO 存储模式

```env
STORAGE_TYPE=minio
CHART_API_KEY=your-secret-key

# MinIO 配置
MINIO_ENDPOINT=minio.example.com:9000
MINIO_ACCESS_KEY=your-access-key
MINIO_SECRET_KEY=your-secret-key
MINIO_BUCKET=charts
MINIO_SECURE=true
MINIO_PUBLIC_URL=https://cdn.example.com  # 可选
```

图片将上传到 MinIO，API 返回完整的访问链接如 `https://minio.example.com/charts/2024-01-01/abc123.png`

#### 自定义上传接口模式

```env
STORAGE_TYPE=custom
CHART_API_KEY=your-secret-key

CUSTOM_UPLOAD_URL=https://api.fashion-tele.com/oss/upload
CUSTOM_UPLOAD_BUCKET=itsm/attachments
CUSTOM_UPLOAD_ACCESS_KEY=your-access-key
CUSTOM_UPLOAD_SECRET_KEY=your-secret-key
```

接口会按 multipart/form-data 上传:

- `bucket`: `CUSTOM_UPLOAD_BUCKET`
- `file`: 生成的 PNG 图表文件
- 请求头: `X-Access-Key` / `X-Secret-Key`，可通过环境变量改名

如果接口返回 JSON 中包含 `url` 字段，API 将直接返回该地址。

### 4. 启动服务

```bash
python charts.py
```

服务将在 `http://0.0.0.0:38000` 启动

## API 使用

### 生成图表

**请求:**

```bash
curl -X POST "http://localhost:38000/generate-chart" \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      {
        "name": "CPU 使用率",
        "x": ["2024-01-01 10:00", "2024-01-01 11:00", "2024-01-01 12:00"],
        "y": [45.2, 67.8, 89.3],
        "unit": "%",
        "color": "#1890ff",
        "threshold": 80
      }
    ]
  }'
```

**响应 (本地存储):**

```json
{
  "status": "success",
  "data": [
    {
      "metric": "CPU 使用率",
      "url": "/imgs/2024-01-01/abc123def456.png"
    }
  ]
}
```

**响应 (对象存储/自定义上传):**

```json
{
  "status": "success",
  "data": [
    {
      "metric": "CPU 使用率",
      "url": "https://minio.example.com/charts/2024-01-01/abc123def456.png"
    }
  ]
}
```

### 转存远程文件

**请求:**

```bash
curl -X POST "http://localhost:38000/store-file-from-url" \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "file_urls": [
      "https://example.com/path/to/report.pdf",
      "/path/to/image.jpg"
    ]
  }'
```

服务会先下载 `file_urls` 中的每个链接，再按当前 `STORAGE_TYPE` 转存到本地、MinIO 或自定义上传接口。也兼容旧的单个 `file_url` 字段。

如果传入的是相对路径，例如 `/path/to/image.jpg`，服务会从 `.env` 里的 `SOURCE_FILE_BASE_URL` 配置读取基础地址并自动拼接下载。

**响应:**

```json
{
  "status": "success",
  "data": [
    {
      "source_url": "https://example.com/path/to/report.pdf",
      "resolved_url": "https://example.com/path/to/report.pdf",
      "filename": "report.pdf",
      "content_type": "application/pdf",
      "size": 148328,
      "url": "https://api.fashion-tele.com/oss/itsm/attachments/report.pdf"
    },
    {
      "source_url": "/path/to/image.jpg",
      "resolved_url": "https://static.example.com/path/to/image.jpg",
      "error": "Failed to download file: 404 Client Error"
    }
  ]
}
```

## Docker 部署

```bash
docker build -t charts-api .
docker run -d -p 38000:38000 --env-file .env charts-api
```

## 环境变量参考

| 变量名 | 说明 | 默认值 | 必填 |
|--------|------|--------|------|
| CHART_API_KEY | API 认证密钥 | default-secret-key | 是 |
| STORAGE_TYPE | 存储类型 (local/minio/custom) | local | 是 |
| MINIO_ENDPOINT | MinIO 服务地址 | localhost:9000 | MinIO 模式必填 |
| MINIO_ACCESS_KEY | MinIO 访问密钥 | - | MinIO 模式必填 |
| MINIO_SECRET_KEY | MinIO 密钥 | - | MinIO 模式必填 |
| MINIO_BUCKET | MinIO Bucket 名称 | charts | MinIO 模式必填 |
| MINIO_SECURE | 是否使用 HTTPS | false | 否 |
| MINIO_PUBLIC_URL | 自定义公网访问地址 | - | 否 |
| CUSTOM_UPLOAD_URL | 自定义上传接口地址 | - | Custom 模式必填 |
| CUSTOM_UPLOAD_BUCKET | 自定义上传 bucket 字段值 | - | Custom 模式必填 |
| CUSTOM_UPLOAD_ACCESS_KEY | 自定义上传 Access Key | - | 否 |
| CUSTOM_UPLOAD_SECRET_KEY | 自定义上传 Secret Key | - | 否 |
| CUSTOM_UPLOAD_ACCESS_KEY_HEADER | Access Key 请求头名 | X-Access-Key | 否 |
| CUSTOM_UPLOAD_SECRET_KEY_HEADER | Secret Key 请求头名 | X-Secret-Key | 否 |
| CUSTOM_UPLOAD_TIMEOUT | 上传超时秒数 | 30 | 否 |
| FILE_FETCH_TIMEOUT | 下载远程文件超时秒数 | 30 | 否 |
| SOURCE_FILE_BASE_URL | 相对路径下载时使用的基础地址 | - | 仅相对路径时必填 |
