FROM python:3.12-slim

WORKDIR /app

# 安装中文字体 (Noto Sans CJK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p imgs && chmod 777 imgs

EXPOSE 8000

CMD ["uvicorn", "charts:app", "--host", "0.0.0.0", "--port", "8000"]