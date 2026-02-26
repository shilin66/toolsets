import os
import uuid
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from typing import List, Optional
from scipy.interpolate import make_interp_spline
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette import status
from matplotlib.ticker import FuncFormatter
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
import io

import matplotlib
matplotlib.use('Agg')

# 加载环境变量
load_dotenv()

app = FastAPI(title="Monitor Chart API")

API_KEY = os.getenv("CHART_API_KEY", "default-secret-key")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# 存储配置
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")  # local 或 minio

# MinIO 配置
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "charts")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "")  # 可选：自定义公网访问地址

# 本地存储配置
BASE_IMAGE_DIR = "imgs"
os.makedirs(BASE_IMAGE_DIR, exist_ok=True)

# 只在本地存储模式下挂载静态文件
if STORAGE_TYPE == "local":
    app.mount("/imgs", StaticFiles(directory=BASE_IMAGE_DIR), name="imgs")

# 初始化 MinIO 客户端
minio_client = None
if STORAGE_TYPE == "minio":
    try:
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        # 确保 bucket 存在
        if not minio_client.bucket_exists(MINIO_BUCKET):
            minio_client.make_bucket(MINIO_BUCKET)
            # 设置 bucket 为公开读取（可选）
            policy = f'''{{
                "Version": "2012-10-17",
                "Statement": [{{
                    "Effect": "Allow",
                    "Principal": {{"AWS": ["*"]}},
                    "Action": ["s3:GetObject"],
                    "Resource": ["arn:aws:s3:::{MINIO_BUCKET}/*"]
                }}]
            }}'''
            minio_client.set_bucket_policy(MINIO_BUCKET, policy)
    except Exception as e:
        print(f"MinIO 初始化失败: {e}")
        minio_client = None

# --- 数据模型 ---
class MetricData(BaseModel):
    name: str
    x: List[str]
    y: List[float]
    unit: str = "%"
    color: str = "#1890ff"
    threshold: Optional[float] = None   # 👈 新增阈值字段

class ChartRequest(BaseModel):
    metrics: List[MetricData]

async def get_api_key(header: str = Security(api_key_header)):
    if header == API_KEY:
        return header
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")

def format_x_axis_labels(x_data: List[str]) -> List[str]:
    formatted_labels = []
    last_date = ""
    for item in x_data:
        parts = item.split(' ')
        if len(parts) == 2:
            d, t = parts
            if d != last_date:
                formatted_labels.append(f"{d}\n{t}")
                last_date = d
            else:
                formatted_labels.append(t)
        else:
            formatted_labels.append(item)
    return formatted_labels

# --- MinIO 上传函数 ---
def upload_to_minio(image_bytes: bytes, file_name: str) -> str:
    """上传图片到 MinIO 并返回访问链接"""
    if not minio_client:
        raise Exception("MinIO 客户端未初始化")
    
    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        object_name = f"{date_str}/{file_name}"
        
        # 上传文件
        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(image_bytes),
            length=len(image_bytes),
            content_type="image/png"
        )
        
        # 返回访问链接
        if MINIO_PUBLIC_URL:
            # 使用自定义公网地址
            return f"{MINIO_PUBLIC_URL}/{MINIO_BUCKET}/{object_name}"
        else:
            # 使用 MinIO endpoint
            protocol = "https" if MINIO_SECURE else "http"
            return f"{protocol}://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{object_name}"
    
    except S3Error as e:
        raise Exception(f"MinIO 上传失败: {e}")

# --- 绘图引擎 ---
def draw_antd_plot(metric: MetricData):
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    x_indices = np.arange(len(metric.x))
    y_values = np.array(metric.y)

    if len(y_values) > 3:
        x_new = np.linspace(x_indices.min(), x_indices.max(), 300)
        spl = make_interp_spline(x_indices, y_values, k=3)
        y_smooth = spl(x_new)
        y_smooth = np.clip(y_smooth, 0, None)
    else:
        x_new, y_smooth = x_indices, y_values

    plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'WenQuanYi Zen Hei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    fig, ax = plt.subplots(figsize=(10, 4), dpi=100)

    # 基础蓝色区域 + 折线
    ax.fill_between(x_new, y_smooth, color=metric.color, alpha=0.1)
    ax.plot(x_new, y_smooth, color=metric.color, linewidth=2)

    # 🔥 阈值高亮逻辑
    if metric.threshold is not None:
        threshold = metric.threshold
        over_mask = y_smooth > threshold

        # 阈值线
        ax.axhline(threshold, color="#ff4d4f", linestyle="--", linewidth=1)

        # 连续区间分段画红线
        idx = np.where(over_mask)[0]
        if len(idx) > 0:
            segments = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
            for seg in segments:
                ax.plot(x_new[seg], y_smooth[seg], color="#ff4d4f", linewidth=2.5, zorder=5)

        # 超阈值区域填充
        ax.fill_between(x_new, threshold, y_smooth, where=over_mask, color="#ff4d4f", alpha=0.15)

    # 标题
    ax.set_title(metric.name, loc='left', fontsize=14, color='#262626', pad=20, fontweight='bold')

    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color('#f0f0f0')

    display_labels = format_x_axis_labels(metric.x)
    ax.set_xticks(x_indices)
    ax.set_xticklabels(display_labels, color='#8c8c8c', fontsize=9)

    n = max(1, len(metric.x) // 8)
    for i, label in enumerate(ax.xaxis.get_ticklabels()):
        if i % n != 0:
            label.set_visible(False)

    ax.yaxis.set_tick_params(left=False)
    ax.grid(axis='y', linestyle='-', linewidth=1, color='#f8f8f8')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y:g}{metric.unit}'))
    plt.setp(ax.get_yticklabels(), color='#8c8c8c', fontsize=9)

    plt.tight_layout()
    file_name = f"{metric.name}-{uuid.uuid4().hex[:12]}.png"
    
    # 根据存储类型选择保存方式
    if STORAGE_TYPE == "minio":
        # 保存到内存缓冲区
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
        buf.seek(0)
        plt.close(fig)
        
        # 上传到 MinIO
        image_bytes = buf.getvalue()
        url = upload_to_minio(image_bytes, file_name)
        return url
    else:
        # 保存到本地
        target_dir = os.path.join(BASE_IMAGE_DIR, date_str)
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.join(target_dir, file_name)
        plt.savefig(file_path, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return f"/imgs/{date_str}/{file_name}"

@app.post("/generate-chart", dependencies=[Depends(get_api_key)])
async def generate_chart_api(request: ChartRequest):
    if not request.metrics:
        raise HTTPException(status_code=400, detail="Metrics list is empty")

    results = []
    for m in request.metrics:
        try:
            url = draw_antd_plot(m)
            results.append({"metric": m.name, "url": url})
        except Exception as e:
            results.append({"metric": m.name, "error": str(e)})

    return {"status": "success", "data": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=38000)