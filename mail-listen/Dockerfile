# =============================================================
# Mail Listen (NOC 工作台) Docker 镜像
# 基础镜像：Python 3.12 slim
# 运行时环境变量通过 .env 注入（docker-compose env_file / docker run --env-file
# / 挂载 .env 到 /app/.env，应用内 python-dotenv 会自动加载）
# =============================================================
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 全局环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    DATABASE_PATH=/app/data/mail_listener.db

# 安装系统依赖：
# - gcc/g++：编译部分 Python 扩展
# - curl：健康检查
# - tzdata：时区支持（日志与割接时间使用东八区）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# 先复制依赖清单，利用 Docker 层缓存（代码变更时不重装依赖）
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright Chromium（RPA 登录/验证码识别需要，--with-deps 自动补齐系统库）
RUN python -m playwright install --with-deps chromium

# 复制应用代码（.env 等敏感文件已在 .dockerignore 中排除，不会打入镜像）
COPY . .

# 创建运行时目录（数据库、附件、日志持久化挂载点）
RUN mkdir -p /app/logs /app/data/email_attachments /app/data/rpa/artifacts

# API 服务端口
EXPOSE 5001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5001/health || exit 1

# 启动一体化服务（邮件监听 + API）
CMD ["python", "main.py"]
