#!/usr/bin/env python3
# login_orion.py
import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
from loguru import logger

from config import settings



def login(base_url, username, password):

    """
    登录并返回 XSRF-TOKEN和Session
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; automated-script/1.0)"
    })
    # 1) GET 登录页
    login_page_url = urljoin(base_url, "Login.aspx?ReturnUrl=%2f")
    r = session.get(login_page_url, timeout=20)
    r.raise_for_status()

    # 2) 解析页面，提取所有隐藏 input 字段（包括 __VIEWSTATE、__VIEWSTATEGENERATOR 等）
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form", id="aspnetForm") or soup.find("form")
    if not form:
        raise Exception("找不到表单（aspnetForm）。请确认 URL 和页面结构是否正确。")

    # 自动收集 hidden 字段
    payload = {}
    for hidden in form.find_all("input", {"type": "hidden"}):
        name = hidden.get("name")
        value = hidden.get("value", "")
        if name:
            payload[name] = value

    # 3) 填入用户名/密码等字段（根据页面字段名）
    payload.update({
        "ctl00$BodyContent$Username": username,
        "ctl00$BodyContent$Password": password,
        # 如果页面有额外的字段（如 PasswordPolicySettingsInput），payload 已包含自动提取到的值
    })

    # 4) 为兼容 ASP.NET，把 __EVENTTARGET 设为登录按钮 id（可选 — 页面脚本会设置它）
    # 这里按照你提供的 HTML，把它设置为登录按钮的 event target
    payload.setdefault("__EVENTTARGET", "ctl00$BodyContent$LoginButton")
    payload.setdefault("__EVENTARGUMENT", "")

    # 5) 确定提交 URL（使用 form.action 或 page 的 action）
    action = form.get("action")
    post_url = urljoin(login_page_url, action) if action else login_page_url

    # 6) 发起 POST 请求（表单编码 application/x-www-form-urlencoded）
    logger.info(f"POST 到：{post_url}")
    resp = session.post(post_url, data=payload, timeout=20, allow_redirects=True)
    # resp.raise_for_status()   # 若需要抛异常可启用
    xsrf_token = session.cookies.get("XSRF-TOKEN")

    # 7) 判断是否登录成功（示例：检查重定向或页面中是否出现特定标记）
    if resp.url != login_page_url and resp.status_code in (200, 302):
        logger.info(f"POST 请求已返回（可能已重定向）。当前 URL：{resp.url}" )
    # 简单检查：页面中是否包含“登录”表单或“用户名是必需”等提示来判断失败
    if "ctl00$BodyContent$Username" in resp.text and "User name is required" in resp.text:
        logger.info("看起来登录失败（页面仍包含登录表单）。")
    else:
        # 你可以更改以下检测逻辑以适配目标站点
        if "Log out" in resp.text or "Logout" in resp.text or "Orion" in resp.text:
            logger.info("可能已登录成功（检测到退出或仪表盘关键字）。")
        else:
            logger.info("提交完成，建议手动检查 resp.url / resp.text 来确认登录状态。")


    r2 = session.get(urljoin(base_url, "/"), timeout=20)
    logger.info(f"首页状态码：{r2.status_code}")
    return xsrf_token, session


def fetch_tree_nodes(session, base_url, resource_id, root_id, xsrf_token, start_index=0, max_pages=50):
    """
    稳健版：递归获取 NodeTree 节点。
    - 会排除“Get next 100 nodes”类型的翻页 <a>，只返回真实节点。
    - 通过解析 onclick 中的 ORION.NodeTree.GetMore(...) 获取下一页的 rootId 和 startIndex。
    """
    api_path = "NetPerfMon/Resources/NodeTree.asmx/GetTreeSection"
    url = urljoin(base_url.rstrip('/') + '/', api_path)

    payload = {
        "resourceId": resource_id,
        "rootId": root_id,
        "keys": [],
        "startIndex": start_index
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json, text/javascript, */*",
        "x-xsrf-token": xsrf_token
    }

    logger.info(f"[fetch_tree_nodes] POST {url} payload={{resourceId:{resource_id}, rootId:{root_id}, startIndex:{start_index}}}")

    resp = session.post(url, json=payload, headers=headers, timeout=20)
    if resp.status_code != 200:
        logger.info(f"请求失败:{resp.status_code}, 响应片段:, {resp.text[:300]}", )
        return []

    try:
        html = resp.json().get("d", "")
    except ValueError:
        logger.info("解析 JSON 失败，原始响应：", resp.text[:500])
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # 1) 解析所有真正的节点 <a>（排除翻页链接）
    for a in soup.find_all("a"):
        # 跳过用于翻页的 <a>：class 包含 getMore，或 href 是 "#"，或 onclick 包含 ORION.NodeTree.GetMore
        a_class = " ".join(a.get("class") or [])
        onclick = a.get("onclick") or ""
        href = a.get("href") or ""

        if "getMore" in a_class or href.strip() == "#" or "ORION.NodeTree.GetMore" in onclick:
            # 这是翻页或加载更多的链接，跳过作为节点收集
            continue

        text = a.get_text(strip=True)
        ip_match = re.findall(r"\d+\.\d+\.\d+\.\d+", text)
        ip = ip_match[-1] if ip_match else ""

        netobject = ""
        if href and "NetObject=" in href:
            m = re.search(r"NetObject=([^&'\"]+)", href)
            if m:
                netobject = m.group(1)

        results.append({
            "name": text,
            "ip": ip,
            "link": href,
            "netobject": netobject
        })

    # 2) 查找翻页 <a>（可能是 <a class="getMore"> 或 <a onclick="ORION.NodeTree.GetMore('NT_r4-startFrom-100', 4, [], 100);">）
    next_found = None
    # 先尝试 class=getMore 的 a
    get_more = soup.find("a", class_="getMore")
    if get_more:
        next_found = get_more
    else:
        # 再宽松查找包含 "Get next" 文本的 a
        get_more = soup.find("a", string=re.compile(r"Get next \d+ nodes", re.I))
        if get_more:
            next_found = get_more
        else:
            # 最后查找任何含有 ORION.NodeTree.GetMore 的 onclick
            onclick_tag = soup.find(lambda tag: tag.name == "a" and tag.get("onclick") and "ORION.NodeTree.GetMore" in tag.get("onclick"))
            if onclick_tag:
                next_found = onclick_tag

    # 3) 如果找到翻页链接，从 onclick 中解析下一页参数并递归请求
    if next_found and max_pages > 0:
        onclick = next_found.get("onclick") or ""
        # 期待形式: ORION.NodeTree.GetMore('NT_r4-startFrom-100', 4, [], 100);
        m = re.search(r"ORION\.NodeTree\.GetMore\(\s*'([^']+)'\s*,\s*(\d+)\s*,\s*\[\s*\]\s*,\s*(\d+)\s*\)", onclick)
        if m:
            next_root = m.group(1)
            try:
                next_resource = int(m.group(2))
            except:
                next_resource = resource_id
            next_start = int(m.group(3))

            # debug 输出
            logger.info(f"检测到更多： next_root={next_root}, next_resource={next_resource}, next_start={next_start}")

            # 递归请求下一页（注意继续使用同一个 session）
            more = fetch_tree_nodes(session, base_url, next_resource, next_root, xsrf_token, next_start, max_pages - 1)
            results.extend(more)
        else:
            # 如果 onclick 没有解析到（某些页面把参数放在 data-* 或 id 中），也尝试从 div id 中抓取 startFrom
            divs = soup.find_all("div", id=re.compile(r".*-startFrom-\d+"))
            parsed = False
            for d in divs:
                idv = d.get("id")
                m2 = re.search(r"-startFrom-(\d+)$", idv)
                if m2:
                    next_start = int(m2.group(1))
                    next_root = idv
                    logger.info(f"从 div id 解析到更多： next_root={next_root}, next_start={next_start}")
                    more = fetch_tree_nodes(session, base_url, resource_id, next_root, xsrf_token, next_start, max_pages - 1)
                    results.extend(more)
                    parsed = True
                    break
            if not parsed:
                logger.info("找到了翻页链接但无法解析 next 参数，跳过继续请求。")

    return results

def parse_rendercontrol_interfaces(html, node_netobject=None, node_name=None):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    # 找到主要表格（ResourceContent 下的 table）
    table = soup.find("table")
    if not table:
        return rows

    # 表格的每个 <tr>（跳过 thead）
    for tr in table.find_all("tr"):
        # 跳过表头行
        if tr.find_parent("thead") or tr.find("th") or tr.find("td", class_="ReportHeader"):
            # 仍需跳过 thead header row
            # 若该 tr 包含 td 且不是数据行，则 continue
            pass

        # 检查有没有 <a href="/Orion/Interfaces/InterfaceDetails.aspx?NetObject=I:...">
        a_tag = tr.find("a", href=re.compile(r"Interfaces/InterfaceDetails.aspx.*NetObject=I:"))
        if not a_tag:
            # 非 interface 行（例如 header 或隐藏文本）跳过
            continue

        # 文本（可能包括中文名称）
        name_text = a_tag.get_text(" ", strip=True)

        # 状态文本：通常在第二列 <td class="Property"> 有 "Unmanaged"/"Up"/"Down" 等
        status_td = None
        tds = tr.find_all("td", recursive=False)
        # 在 example 中 status 在第二个 td
        if len(tds) >= 2:
            status_td = tds[1]
        status_text = status_td.get_text(strip=True) if status_td else ""



        row = {
            "node_netobject": node_netobject,
            "node_name": node_name,
            "name": name_text,
            "status": status_text,
        }
        rows.append(row)

    return rows


def get_all_node_interfaces(session, base_url, nodes, resource_id=105, is_noc_view=True, pause_between=0.1):
    """
    nodes: list of node dicts, 每个 dict 至少包含 'netobject' 和可选 'name'
           eg: {"netobject":"N:40", "name":"..."}
    resource_id: 此处示例用 105 (Current Percent Utilization of Each Interface)
    is_noc_view: 是否在 query string 中加入 isNOCView=1（示例中为空）
    pause_between: 每次请求间的 sleep 秒数，防止刷太快
    返回：接口列表（每个包含 node_netobject）
    """
    results = []
    base = base_url.rstrip('/') + '/'
    for node in nodes:
        netobj = node.get("netobject") or node.get("NetObject") or node.get("netObject")
        node_name = node.get("name") or node.get("node_name") or node.get("text") or None
        if not netobj:
            logger.debug("跳过无 netobject 的 node:", node)
            continue

        # 构造请求 URL（与示例一致）
        qs = {
            "ResourceID": str(resource_id),
            "NetObject": netobj,
            # isNOCView 参数示例中为空，这里如果 is_noc_view True 就传空值（等价于 isNOCView=）
        }
        # 生成 query string manually to keep NetObject as-is（例如 N:40 -> N%3A40）
        query = urlencode(qs, doseq=True)
        if is_noc_view:
            query = query + "&isNOCView="
        url = base + "RenderControl.aspx?" + query

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": base + "NetPerfMon/NodeDetails.aspx?NetObject=" + netobj
        }

        try:
            logger.debug(f"请求 Resource {resource_id} for node {netobj} -> {url}")

            resp = session.post(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                logger.debug("请求失败:", resp.status_code, resp.text[:200])
                continue

            html = resp.text
            interfaces = parse_rendercontrol_interfaces(html, node_netobject=netobj, node_name=node_name)
            logger.debug(f"解析到 {len(interfaces)} 个接口 for {netobj}")

            results.extend(interfaces)

        except Exception as e:
            logger.debug(f"异常：{e}")
        finally:
            # 速率限制
            if pause_between:
                time.sleep(pause_between)

    return results

def get_target_node_interfaces(target_node_name, status):
    interfaces = []

    # 定义要访问的服务器列表
    servers = [
        "http://10.6.0.68:8080/Orion/",
        "http://10.6.0.69:8080/Orion/"
    ]

    for server_url in servers:
        try:
            # 登录并获取 session 和 xsrf_token
            xsrf_token, session = login(server_url, settings.sw_username, settings.sw_password)
            
            # 获取所有节点信息
            all_node = fetch_tree_nodes(session, server_url, 4, "NT_r4", xsrf_token)
            logger.debug("返回内容：{}", all_node)
            logger.info("返回内容数量：{}", len(all_node))

            # 过滤出目标节点

            target_nodes = [
                result for result in all_node
                if target_node_name in result.get('name', '')
            ]
            logger.info("匹配的目标节点：{}", target_nodes)

            # 获取目标节点的接口信息
            server_interfaces = get_all_node_interfaces(session, server_url, target_nodes, resource_id=105, pause_between=0.05)
            if status:
                server_interfaces = [interface for interface in server_interfaces if interface.get('status', '').lower() == status.lower()]
            interfaces.extend(server_interfaces or [])

        except Exception as e:
            logger.error(f"处理服务器 {server_url} 时发生错误: {e}")
            continue

    return interfaces