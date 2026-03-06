import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from netmiko import ConnectHandler
from typing import List, Optional, Dict

app = FastAPI(title="Concurrency Network API", description="高性能并发网络自动化接口")

# 使用线程池来处理阻塞的 Netmiko 调用
executor = ThreadPoolExecutor(max_workers=10)


class CommandRequest(BaseModel):
    host: str
    username: str
    password: str
    secret: Optional[str] = None
    device_type: str = "cisco_ios"
    protocol: str = "ssh"
    commands: List[str]


def _ssh_execute_task(device_config: dict, commands: List[str]) -> Dict:
    results = []
    try:
        with ConnectHandler(**device_config) as conn:
            conn.enable()

            for cmd in commands:
                try:
                    # 为每条命令设置独立的执行逻辑
                    # 在发送新命令前，把之前可能残留的数据全部扔掉
                    conn.clear_buffer()

                    is_show = any(cmd.lower().startswith(x) for x in ['sh', 'disp', 'do', 'pi'])
                    if 'conf ' in cmd.lower() and not is_show:
                        output = conn.send_config_set([cmd])
                    else:
                        # 单条命令执行，设定合理的超时
                        output = conn.send_command(
                            cmd,
                            read_timeout=120,
                            delay_factor=2,
                            strip_prompt=False,
                            strip_command=False,
                            cmd_verify=False
                        )

                    results.append({"command": cmd, "output": output, "status": "success"})

                except Exception as cmd_error:
                    # 【核心改进】如果单条命令失败（如超时），记录错误但不跳出循环
                    conn.clear_buffer()
                    results.append({
                        "command": cmd,
                        "output": f"Command Failed: {str(cmd_error)}",
                        "status": "failed"
                    })
                    # 如果是连接断开了，才需要彻底退出
                    if not conn.is_alive():
                        break

            return {"status": "completed", "results": results}

    except Exception as connection_error:
        # 只有在连不上设备、登录失败等“全局问题”时才返回 error
        return {"status": "error", "message": f"Connection Failed: {str(connection_error)}"}


@app.post("/execute")
async def execute_commands(req: CommandRequest):
    # 输出请求body
    print(req.json())
    # 1. 适配协议
    final_type = f"{req.device_type}_telnet" if req.protocol == "telnet" else req.device_type

    device_config = {
        "device_type": final_type,
        "host": req.host,
        "username": req.username,
        "password": req.password,
        "secret": req.secret,
        "port": 23 if req.protocol == "telnet" else 22,
        # --- 专家级加固参数 ---
        "conn_timeout": 30,          # 提高连接超时到 30 秒
        "auth_timeout": 30,          # 提高认证超时
        "banner_timeout": 30,        # 提高读取 Banner 的超时
        "global_delay_factor": 4,    # 增加整体操作延迟，适配慢速 CPU
    }

    # 2. 使用 asyncio.get_event_loop().run_in_executor 将阻塞任务交给线程池
    # 这允许 FastAPI 在等待 SSH 返回时继续处理其他 API 请求
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        executor,
        _ssh_execute_task,
        device_config,
        req.commands
    )

    if response["status"] == "error":
        # 即使报错也返回 200，但在 JSON 里体现错误，方便大模型分析
        return response

    return response
