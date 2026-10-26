import requests
import re
import yaml
import base64
import json
import urllib.parse
import os
import sys
import html
from datetime import datetime

# Windows GBK 控制台下打印 emoji 会报 UnicodeEncodeError，强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ================= 配置区域 =================

# 1. 原原有 GitHub 聚合源配置
GITHUB_SOURCES = [
    {"name": "tolinkshare2", "repo_url": "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "toshare5", "repo_url": "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "mkshare3", "repo_url": "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "abshare3", "repo_url": "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "abshare", "repo_url": "https://raw.githubusercontent.com/abshare/abshare.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
]

HISTORY_FILE = "history.json"
MAX_HISTORY = 1000

GITHUB_OUTPUT_CLASH = "clash_sub.txt"
GITHUB_OUTPUT_V2RAY = "v2ray_sub.txt"
GITHUB_OUTPUT_SINGBOX = "singbox_sub.json"

# 2. 新增 YoyaPai 独立源配置
YOYA_CATEGORY_URL = "https://yoyapai.com/category/mianfeijiedian"
YOYA_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0"

YOYA_OUTPUT_CLASH = "clash.txt"
YOYA_OUTPUT_V2RAY = "v2ray.txt"
YOYA_OUTPUT_SINGBOX = "singbox.json"

# 3. 新增 MiBei (米贝分享) 独立源配置
MIBEI_CATEGORY_URL = "https://www.mibei77.com/category/jiedian"
MIBEI_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0"

MIBEI_OUTPUT_CLASH = "clash1.txt"
MIBEI_OUTPUT_V2RAY = "v2ray1.txt"
MIBEI_OUTPUT_SINGBOX = "singbox1.json"

REQUEST_TIMEOUT = 15
# ============================================

yaml.SafeDumper.ignore_aliases = lambda *args: True


# ================= 通用工具函数 =================

def fetch_url(url, headers=None, timeout=REQUEST_TIMEOUT):
    """
    通用网络请求封装：优先使用系统默认环境；
    若遇到本地代理异常/SSL握手错误（例如国内站点被本地代理阻断），自动切换为直连模式重试。
    """
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except (requests.exceptions.SSLError, requests.exceptions.ProxyError):
        session = requests.Session()
        session.trust_env = False
        return session.get(url, headers=headers, timeout=timeout)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def calculate_avg_hours(timestamps):
    if len(timestamps) < 2: return 0.0
    fmt = "%Y-%m-%d %H:%M:%S"
    intervals = []
    for i in range(1, len(timestamps)):
        try:
            t1 = datetime.strptime(timestamps[i-1], fmt)
            t2 = datetime.strptime(timestamps[i], fmt)
            diff = (t2 - t1).total_seconds() / 3600.0
            if diff > 0:  # 排除异常数据
                intervals.append(diff)
        except Exception:
            pass
    if not intervals: return 0.0
    return round(sum(intervals) / len(intervals), 1)

def fetch_real_url(content, keyword):
    pattern = f"{keyword}.*?(https://[^\\s'\"`<>]+)"
    match = re.search(pattern, content, re.S)
    return match.group(1).strip() if match else None

def decode_base64(text):
    text = text.strip()
    try:
        missing_padding = len(text) % 4
        if missing_padding:
            text += '=' * (4 - missing_padding)
        return base64.b64decode(text).decode('utf-8')
    except Exception:
        return text

def build_singbox_transport(node):
    """从 Clash 节点提取 sing-box 的 transport 配置 (ws/grpc/h2)"""
    net = node.get('network')
    if net == 'ws':
        ws_opts = node.get('ws-opts') or {}
        transport = {"type": "ws", "path": ws_opts.get('path', '/')}
        headers = ws_opts.get('headers') or {}
        if headers:
            transport['headers'] = headers
        return transport
    elif net == 'grpc':
        grpc_opts = node.get('grpc-opts') or {}
        return {"type": "grpc", "service_name": grpc_opts.get('grpc-service-name', '')}
    elif net == 'h2':
        h2_opts = node.get('h2-opts') or {}
        return {"type": "http", "host": h2_opts.get('host', []), "path": h2_opts.get('path', '/')}
    return None

def convert_clash_to_singbox(node):
    """将单个 Clash 节点转换为 sing-box outbound，不支持的类型返回 None"""
    try:
        n_type = node.get('type')
        base = {
            "tag": str(node.get('name', '')),
            "server": str(node.get('server', '')),
            "server_port": int(node.get('port', 0)),
        }

        # 通用 TLS 配置
        tls = None
        if node.get('tls') or n_type in ('trojan', 'hysteria2', 'hy2', 'tuic'):
            tls = {"enabled": True}
            sni = node.get('servername') or node.get('sni')
            if sni:
                tls['server_name'] = str(sni)
            if node.get('skip-cert-verify'):
                tls['insecure'] = True
            reality_opts = node.get('reality-opts')
            if reality_opts:
                tls['reality'] = {
                    "enabled": True,
                    "public_key": reality_opts.get('public-key', ''),
                    "short_id": reality_opts.get('short-id', ''),
                }
                tls['utls'] = {"enabled": True, "fingerprint": node.get('client-fingerprint', 'chrome')}

        if n_type == 'ss':
            out = {"type": "shadowsocks", **base,
                   "method": node.get('cipher', ''), "password": str(node.get('password', ''))}
            if node.get('plugin') == 'obfs':
                plugin_opts = node.get('plugin-opts') or {}
                out['plugin'] = 'obfs-local'
                out['plugin_opts'] = f"obfs={plugin_opts.get('mode', 'http')};obfs-host={plugin_opts.get('host', '')}"
            return out

        elif n_type == 'vmess':
            out = {"type": "vmess", **base,
                   "uuid": str(node.get('uuid', '')),
                   "alter_id": int(node.get('alterId', 0)),
                   "security": node.get('cipher', 'auto')}
            if tls: out['tls'] = tls
            transport = build_singbox_transport(node)
            if transport: out['transport'] = transport
            return out

        elif n_type == 'vless':
            out = {"type": "vless", **base, "uuid": str(node.get('uuid', ''))}
            if node.get('flow'):
                out['flow'] = node['flow']
            if tls: out['tls'] = tls
            transport = build_singbox_transport(node)
            if transport: out['transport'] = transport
            return out

        elif n_type == 'trojan':
            out = {"type": "trojan", **base, "password": str(node.get('password', ''))}
            out['tls'] = tls or {"enabled": True}
            transport = build_singbox_transport(node)
            if transport: out['transport'] = transport
            return out

        elif n_type in ('hysteria2', 'hy2'):
            out = {"type": "hysteria2", **base, "password": str(node.get('password', ''))}
            out['tls'] = tls or {"enabled": True}
            if node.get('obfs'):
                out['obfs'] = {"type": node.get('obfs'), "password": str(node.get('obfs-password', ''))}
            return out

        elif n_type == 'tuic':
            out = {"type": "tuic", **base,
                   "uuid": str(node.get('uuid', '')),
                   "password": str(node.get('password', ''))}
            if node.get('congestion-controller'):
                out['congestion_control'] = node['congestion-controller']
            if node.get('udp-relay-mode'):
                out['udp_relay_mode'] = node['udp-relay-mode']
            out['tls'] = tls or {"enabled": True}
            if node.get('alpn'):
                out['tls']['alpn'] = node['alpn']
            return out

    except Exception:
        return None
    return None

def build_full_singbox_config(outbound_nodes, source_groups=None):
    """
    组装包含通用 DNS、Inbounds(Mixed+Tun)、Outbounds 和 Route 规则的完整 Sing-box 配置
    """
    if not outbound_nodes:
        return None

    all_node_tags = [o['tag'] for o in outbound_nodes]
    
    if source_groups:
        all_group_tags = [g['tag'] for g in source_groups]
        selector_outbounds = ["♻️ 自动选择"] + all_group_tags
        middle_groups = source_groups
    else:
        selector_outbounds = ["♻️ 自动选择"] + all_node_tags
        middle_groups = []

    config = {
        "log": {"level": "warn", "timestamp": True},
        "dns": {
            "servers": [
                {"tag": "remote-dns", "address": "https://1.1.1.1/dns-query",
                 "detour": "🚀 节点选择", "strategy": "ipv4_only"},
                {"tag": "local-dns", "address": "https://223.5.5.5/dns-query",
                 "detour": "direct", "strategy": "ipv4_only"}
            ],
            "rules": [
                # 防回环：代理服务器自身域名必须用本地 DNS 直连解析
                {"outbound": "any", "server": "local-dns"},
                # 非中国大陆域名一律用远端 DNS，避免被污染
                {"rule_set": "geosite-geolocation-!cn", "server": "remote-dns"},
                {"rule_set": "geosite-cn", "server": "local-dns"}
            ],
            "final": "remote-dns",
            "strategy": "ipv4_only",
            "independent_cache": True
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 2080
            },
            {
                "type": "tun",
                "tag": "tun-in",
                "address": ["172.19.0.1/30"],
                "auto_route": True,
                "strict_route": True,
                "stack": "mixed"
            }
        ],
        "outbounds": [
            {
                "type": "selector",
                "tag": "🚀 节点选择",
                "outbounds": selector_outbounds
            },
            {
                "type": "urltest",
                "tag": "♻️ 自动选择",
                "outbounds": all_node_tags,
                "url": "https://www.gstatic.com/generate_204",
                "interval": "5m"
            }
        ] + middle_groups + outbound_nodes + [
            {"type": "direct", "tag": "direct"}
        ],
        "route": {
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"ip_is_private": True, "outbound": "direct"},
                # 域名类规则优先，命中国外域名直接走代理
                {"rule_set": "geosite-geolocation-!cn", "outbound": "🚀 节点选择"},
                {"rule_set": "geosite-cn", "outbound": "direct"},
                # IP 类规则必须先 resolve，否则目标是域名时不会匹配
                {"action": "resolve", "strategy": "ipv4_only"},
                {"rule_set": "geoip-cn", "outbound": "direct"}
            ],
            "rule_set": [
                {
                    "tag": "geosite-cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs",
                    "download_detour": "🚀 节点选择"
                },
                {
                    "tag": "geosite-geolocation-!cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-geolocation-!cn.srs",
                    "download_detour": "🚀 节点选择"
                },
                {
                    "tag": "geoip-cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs",
                    "download_detour": "🚀 节点选择"
                }
            ],
            "final": "🚀 节点选择",
            "auto_detect_interface": True
        }
    }
    return config


# ================= 任务1：原有 GitHub 源聚合处理 =================

def process_github_sources():
    """
    处理原有 5 个 GitHub 仓库源：
    抓取、去重并合并，输出到 clash_sub.txt、v2ray_sub.txt 和 singbox.json
    """
    print("\n" + "=" * 50)
    print(">>> 开始处理原有 GitHub 聚合源")
    print("=" * 50)

    history = load_history()
    clash_headers = {"User-Agent": "clash-verge/v2.4.8"}
    v2ray_headers = {"User-Agent": "v2rayN/7.17"}
    github_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0"}

    global_seen_names = set()
    processed_sources = []

    final_clash_config = {}
    original_proxy_groups = []

    for source in GITHUB_SOURCES:
        s_name = source['name']
        print(f"\n[{s_name}] 正在解析仓库...")

        source_data = {"source_name": s_name, "update_time": "", "group_name": "", "clash_nodes": [], "v2ray_text": ""}

        try:
            resp = requests.get(source['repo_url'], headers=github_headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            content = resp.text

            # 提取当前页面的更新时间
            curr_update_time = re.search(r"更新时间[^\d]*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", content)
            curr_time_str = curr_update_time.group(1).strip() if curr_update_time else ""
            source_data["update_time"] = curr_time_str

            # 历史记录与平均时间计算
            if s_name not in history:
                history[s_name] = {"last_update": "", "prev_update": "", "records": []}

            if curr_time_str and curr_time_str != history[s_name]["last_update"]:
                history[s_name]["prev_update"] = history[s_name]["last_update"]
                history[s_name]["last_update"] = curr_time_str
                history[s_name]["records"].append(curr_time_str)
                if len(history[s_name]["records"]) > MAX_HISTORY:
                    history[s_name]["records"].pop(0)

            avg_h = calculate_avg_hours(history[s_name]["records"])
            prev_update_show = history[s_name]["prev_update"][5:16] if history[s_name]["prev_update"] else "N/A"
            curr_update_short = curr_time_str[2:16] if curr_time_str else "N/A"

            # 处理 Clash
            clash_url = fetch_real_url(content, source['clash_keyword'])
            if clash_url:
                c_resp = requests.get(clash_url, headers=clash_headers, timeout=REQUEST_TIMEOUT)
                try:
                    yaml_data = yaml.safe_load(c_resp.text)
                    if not isinstance(yaml_data, dict):
                        print(f"  [{s_name}] Clash 配置解析失败：{c_resp.text[:80]}")
                    else:
                        if yaml_data and not final_clash_config:
                            for k, v in yaml_data.items():
                                if k not in ['proxies', 'proxy-groups']:
                                    final_clash_config[k] = v
                            original_proxy_groups = yaml_data.get('proxy-groups', [])

                        if yaml_data and 'proxies' in yaml_data:
                            nodes = yaml_data['proxies']
                            group_traffic = ""

                            for node in nodes:
                                orig_name = str(node.get('name', ''))
                                traffic_match = re.search(r"剩余流量[：:\s]*([\d\.]+\s*[a-zA-Z]+)", orig_name)
                                if traffic_match:
                                    group_traffic = traffic_match.group(1).strip()
                                    break

                            p_traffic = f"{group_traffic:<8}" if group_traffic else "N/A     "
                            source_data["group_name"] = f"{s_name:<12} {p_traffic} 更新：{curr_update_short}  上次：{prev_update_show}  [{avg_h}h]"

                            for node in nodes:
                                original_name = str(node.get('name', ''))
                                if "剩余流量" in original_name and group_traffic and curr_update_short != "N/A":
                                    new_node_name = f"[{s_name}] {group_traffic} 时间:{curr_update_short}"
                                else:
                                    new_node_name = f"[{s_name}] {original_name}"

                                final_node_name = new_node_name
                                counter = 1
                                while final_node_name in global_seen_names:
                                    final_node_name = f"{new_node_name} {counter}"
                                    counter += 1

                                global_seen_names.add(final_node_name)
                                node['name'] = final_node_name
                                source_data["clash_nodes"].append(node)
                except Exception as e:
                    print(f"  -> 解析 Clash 失败: {e}")

            # 处理 V2ray
            v2ray_url = fetch_real_url(content, source['v2ray_keyword'])
            if v2ray_url:
                v_resp = requests.get(v2ray_url, headers=v2ray_headers, timeout=REQUEST_TIMEOUT)
                raw_v2ray = decode_base64(v_resp.text)
                processed_v2ray_links = []

                for line in raw_v2ray.splitlines():
                    line = line.strip()
                    if not line: continue

                    if line.startswith("vmess://"):
                        try:
                            b64_str = line[8:]
                            b64_str += '=' * ((4 - len(b64_str) % 4) % 4)
                            node_data = json.loads(base64.b64decode(b64_str).decode('utf-8'))
                            old_name = str(node_data.get('ps', ''))

                            if "剩余流量" in old_name and curr_update_short != "N/A":
                                node_data['ps'] = f"{old_name} {curr_update_short}"
                                new_b64 = base64.b64encode(json.dumps(node_data, separators=(',', ':')).encode('utf-8')).decode('utf-8')
                                processed_v2ray_links.append(f"vmess://{new_b64}")
                            else:
                                processed_v2ray_links.append(line)
                        except Exception:
                            processed_v2ray_links.append(line)
                    elif "://" in line:
                        try:
                            parts = line.split('#', 1)
                            if len(parts) > 1:
                                base_url = parts[0]
                                old_name = urllib.parse.unquote(parts[1])
                                if "剩余流量" in old_name and curr_update_short != "N/A":
                                    new_name = f"{old_name} {curr_update_short}"
                                    encoded_name = urllib.parse.quote(new_name)
                                    processed_v2ray_links.append(f"{base_url}#{encoded_name}")
                                else:
                                    processed_v2ray_links.append(line)
                            else:
                                processed_v2ray_links.append(line)
                        except Exception:
                            processed_v2ray_links.append(line)
                    else:
                        processed_v2ray_links.append(line)

                source_data["v2ray_text"] = "\n".join(processed_v2ray_links)

            processed_sources.append(source_data)
        except Exception as e:
            print(f"  -> 访问出错: {e}")

    # 保存历史更新记录
    save_history(history)
    print("\n✅ 历史更新频率记录已保存至 history.json")

    # 排序与写入
    processed_sources.sort(key=lambda x: x["update_time"] if x["update_time"] else "9999-99-99 99:99:99")

    all_clash_proxies = []
    our_groups = []
    all_source_group_names = []
    all_v2ray_nodes = ""

    for src in processed_sources:
        if src["clash_nodes"]:
            all_clash_proxies.extend(src["clash_nodes"])
            node_names = [n['name'] for n in src["clash_nodes"]]
            group = {"name": src["group_name"], "type": "select", "proxies": node_names}
            our_groups.append(group)
            all_source_group_names.append(src["group_name"])

        if src["v2ray_text"]:
            all_v2ray_nodes += f"\n# ===== {src['group_name']} =====\n"
            all_v2ray_nodes += src["v2ray_text"] + "\n"

    # 1. 输出 Clash 文件 (clash_sub.txt)
    if all_clash_proxies:
        for og_group in original_proxy_groups:
            og_group['proxies'] = all_source_group_names

        final_proxy_groups = original_proxy_groups + our_groups
        final_clash_config['proxies'] = all_clash_proxies
        final_clash_config['proxy-groups'] = final_proxy_groups

        with open(GITHUB_OUTPUT_CLASH, 'w', encoding='utf-8') as f:
            yaml.safe_dump(final_clash_config, f, allow_unicode=True, sort_keys=False)
        print(f"🎉 [GitHub源] Clash 写入完成 -> {GITHUB_OUTPUT_CLASH} (共 {len(all_clash_proxies)} 个节点)")

    # 2. 输出 V2Ray 文件 (v2ray_sub.txt)
    if all_v2ray_nodes.strip():
        final_v2ray_b64 = base64.b64encode(all_v2ray_nodes.strip().encode('utf-8')).decode('utf-8')
        with open(GITHUB_OUTPUT_V2RAY, 'w', encoding='utf-8') as f:
            f.write(final_v2ray_b64)
        print(f"🎉 [GitHub源] V2ray 写入完成 -> {GITHUB_OUTPUT_V2RAY} (已重新编码为 Base64)")

    # 3. 输出 Sing-box 文件 (singbox.json)
    if all_clash_proxies:
        singbox_outbounds = []
        singbox_source_groups = []
        skipped = 0

        for src in processed_sources:
            if not src["clash_nodes"]: continue
            src_tags = []
            for node in src["clash_nodes"]:
                sb_node = convert_clash_to_singbox(node)
                if sb_node:
                    singbox_outbounds.append(sb_node)
                    src_tags.append(sb_node['tag'])
                else:
                    skipped += 1
            if src_tags:
                singbox_source_groups.append({
                    "type": "selector",
                    "tag": src["group_name"],
                    "outbounds": src_tags,
                })

        if singbox_outbounds:
            singbox_config = build_full_singbox_config(singbox_outbounds, source_groups=singbox_source_groups)
            with open(GITHUB_OUTPUT_SINGBOX, 'w', encoding='utf-8') as f:
                json.dump(singbox_config, f, indent=2, ensure_ascii=False)
            skip_msg = f"（跳过 {skipped} 个不支持的节点）" if skipped else ""
            print(f"🎉 [GitHub源] Sing-box 写入完成 -> {GITHUB_OUTPUT_SINGBOX} (共 {len(singbox_outbounds)} 个节点{skip_msg})")


# ================= 任务2：新增 YoyaPai 独立源处理 =================

def process_yoyapai_source():
    """
    独立处理 YoyaPai 源：
    1. 抓取最新每日更新文章，提取订阅链接；
    2. 下载并保存 clash.txt、v2ray.txt（二进制无损存储，防乱码）；
    3. 解析 clash.txt 中的节点，重组成完整的 Sing-box 配置并输出到 singbox1.txt。
    """
    print("\n" + "=" * 50)
    print(">>> 开始处理 YoyaPai 独立源")
    print("=" * 50)

    headers = {
        "User-Agent": YOYA_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://yoyapai.com/"
    }

    # 1. 获取分类页面
    print(f"[*] 正在请求分类页面: {YOYA_CATEGORY_URL}")
    resp = fetch_url(YOYA_CATEGORY_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = 'utf-8'

    pattern = r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    matches = re.findall(pattern, resp.text, re.DOTALL)

    articles = []
    seen_urls = set()
    for href, text in matches:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        if "每日更新" in clean_text and ("Clash" in clean_text or "V2Ray" in clean_text or "机场订阅" in clean_text):
            if href not in seen_urls and href.rstrip('/') != YOYA_CATEGORY_URL.rstrip('/'):
                seen_urls.add(href)
                articles.append({"title": clean_text, "url": href})

    if not articles:
        print("[-] 未在 YoyaPai 找到匹配关键字的文章！")
        return

    latest_article = articles[0]
    print(f"[+] 最新文章: {latest_article['title']}")
    print(f"[+] 文章链接: {latest_article['url']}")

    # 2. 打开详情页提取订阅链接
    art_resp = fetch_url(latest_article["url"], headers=headers, timeout=REQUEST_TIMEOUT)
    art_resp.raise_for_status()
    art_resp.encoding = 'utf-8'
    content = html.unescape(art_resp.text)

    # 提取 Clash 链接
    clash_m = re.search(r'Clash[^\n<]*?免费节点订阅地址.*?<code[^>]*>\s*(https?://[^\s<"\'`]+)\s*</code>', content, re.DOTALL | re.IGNORECASE)
    if not clash_m:
        clash_m = re.search(r'Clash[^\n<]*?免费节点订阅地址.*?(https?://[^\s<"\'`]+)', content, re.DOTALL | re.IGNORECASE)
    clash_url = clash_m.group(1).strip() if clash_m else None

    # 提取 V2Ray 链接
    v2ray_m = re.search(r'V2Ray[^\n<]*?免费节点订阅地址.*?<code[^>]*>\s*(https?://[^\s<"\'`]+)\s*</code>', content, re.DOTALL | re.IGNORECASE)
    if not v2ray_m:
        v2ray_m = re.search(r'V2Ray[^\n<]*?免费节点订阅地址.*?(https?://[^\s<"\'`]+)', content, re.DOTALL | re.IGNORECASE)
    v2ray_url = v2ray_m.group(1).strip() if v2ray_m else None

    print(f"[+] 提取到的 Clash 订阅: {clash_url}")
    print(f"[+] 提取到的 V2Ray 订阅: {v2ray_url}")

    # 3. 下载并无损保存 clash.txt
    if clash_url:
        print(f"[*] 正在下载 Clash 订阅内容...")
        c_sub_resp = fetch_url(clash_url, headers=headers, timeout=REQUEST_TIMEOUT)
        c_sub_resp.raise_for_status()
        with open(YOYA_OUTPUT_CLASH, "wb") as f:
            f.write(c_sub_resp.content)
        size_kb = len(c_sub_resp.content) / 1024
        print(f"🎉 [Yoya源] Clash 写入完成 -> {YOYA_OUTPUT_CLASH} (大小: {size_kb:.2f} KB)")
    else:
        print(f"[-] [Yoya源] 未获取到 Clash 订阅链接，跳过保存。")

    # 4. 下载并无损保存 v2ray.txt
    if v2ray_url:
        print(f"[*] 正在下载 V2Ray 订阅内容...")
        v_sub_resp = fetch_url(v2ray_url, headers=headers, timeout=REQUEST_TIMEOUT)
        v_sub_resp.raise_for_status()
        with open(YOYA_OUTPUT_V2RAY, "wb") as f:
            f.write(v_sub_resp.content)
        size_kb = len(v_sub_resp.content) / 1024
        print(f"🎉 [Yoya源] V2ray 写入完成 -> {YOYA_OUTPUT_V2RAY} (大小: {size_kb:.2f} KB)")
    else:
        print(f"[-] [Yoya源] 未获取到 V2Ray 订阅链接，跳过保存。")

    # 5. 解析 clash.txt 中的节点，重组并生成 singbox1.txt
    if not os.path.exists(YOYA_OUTPUT_CLASH):
        print(f"[-] [Yoya源] {YOYA_OUTPUT_CLASH} 不存在，无法生成 Sing-box。")
        return

    try:
        with open(YOYA_OUTPUT_CLASH, 'r', encoding='utf-8') as f:
            yoya_clash_data = yaml.safe_load(f)

        if not isinstance(yoya_clash_data, dict) or 'proxies' not in yoya_clash_data:
            print("[-] [Yoya源] 解析 clash.txt 失败：未找到有效 proxies 列表。")
            return

        proxies = yoya_clash_data.get('proxies', [])
        print(f"[*] 正在将 YoyaPai {len(proxies)} 个节点转换为 Sing-box 格式...")

        singbox_outbounds = []
        seen_tags = set()
        skipped = 0

        for node in proxies:
            # 确保节点标签唯一
            orig_name = str(node.get('name', '')).strip()
            if not orig_name:
                orig_name = f"{node.get('type', 'node')}-{node.get('server', '')}"

            tag_name = orig_name
            counter = 1
            while tag_name in seen_tags:
                tag_name = f"{orig_name}_{counter}"
                counter += 1
            seen_tags.add(tag_name)
            node['name'] = tag_name

            sb_node = convert_clash_to_singbox(node)
            if sb_node:
                singbox_outbounds.append(sb_node)
            else:
                skipped += 1

        if singbox_outbounds:
            # 组装完整包含分流规则、自动测速选择与直连的配置
            singbox_config = build_full_singbox_config(singbox_outbounds)
            with open(YOYA_OUTPUT_SINGBOX, 'w', encoding='utf-8') as f:
                json.dump(singbox_config, f, indent=2, ensure_ascii=False)
            skip_msg = f"（跳过 {skipped} 个不支持的节点）" if skipped else ""
            print(f"🎉 [Yoya源] Sing-box 写入完成 -> {YOYA_OUTPUT_SINGBOX} (共 {len(singbox_outbounds)} 个节点{skip_msg})")
        else:
            print(f"[-] [Yoya源] 未能成功转换出任何 Sing-box 节点。")

    except Exception as e:
        print(f"[-] [Yoya源] 生成 {YOYA_OUTPUT_SINGBOX} 失败: {e}")


# ================= 任务3：新增 MiBei (米贝分享) 独立源处理 =================

def process_mibei_source():
    """
    独立处理 MiBei (米贝分享) 源，流程与 YoyaPai 一致：
    1. 抓取分类页最新的“免费精选节点”文章（按标题日期取最新，规避置顶干扰），提取订阅链接；
    2. 下载并保存 clash_mibei.txt、v2ray_mibei.txt（二进制无损存储，防乱码）；
    3. 解析 clash_mibei.txt 中的节点，重组成完整的 Sing-box 配置并输出到 singbox_mibei.json。
    """
    print("\n" + "=" * 50)
    print(">>> 开始处理 MiBei (米贝分享) 独立源")
    print("=" * 50)

    headers = {
        "User-Agent": MIBEI_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.mibei77.com/"
    }

    # 1. 获取分类页面
    print(f"[*] 正在请求分类页面: {MIBEI_CATEGORY_URL}")
    resp = fetch_url(MIBEI_CATEGORY_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = 'utf-8'

    pattern = r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    matches = re.findall(pattern, resp.text, re.DOTALL)

    articles = []
    seen_urls = set()
    for href, text in matches:
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        if "节点" in clean_text and any(k in clean_text.lower() for k in ("v2ray", "clash", "订阅")):
            if href not in seen_urls and href.rstrip('/') != MIBEI_CATEGORY_URL.rstrip('/'):
                seen_urls.add(href)
                articles.append({"title": clean_text, "url": href})

    if not articles:
        print("[-] 未在 MiBei 找到匹配关键字的文章！")
        return

    # 按标题中的日期（如 2026年10月26日）降序排序，确保取到最新一篇
    def parse_article_date(title):
        m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', title)
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""

    articles.sort(key=lambda x: parse_article_date(x["title"]), reverse=True)

    latest_article = articles[0]
    print(f"[+] 最新文章: {latest_article['title']}")
    print(f"[+] 文章链接: {latest_article['url']}")

    # 2. 打开详情页提取订阅链接
    art_resp = fetch_url(latest_article["url"], headers=headers, timeout=REQUEST_TIMEOUT)
    art_resp.raise_for_status()
    art_resp.encoding = 'utf-8'
    content = html.unescape(art_resp.text)

    # 提取 Clash 链接（页面格式：<strong>Clash Meta订阅链接</strong>... <p>https://xxx.yaml</p>）
    clash_m = re.search(r'Clash[^\n<]*?订阅链接.*?(https?://[^\s<"\'`]+\.ya?ml)', content, re.DOTALL | re.IGNORECASE)
    if not clash_m:
        clash_m = re.search(r'(https?://[^\s<"\'`]+\.ya?ml)', content, re.IGNORECASE)
    clash_url = clash_m.group(1).strip() if clash_m else None

    # 提取 V2Ray 链接（页面格式：<strong>v2ray/小火箭/winxray</strong>等订阅链接... <p>https://xxx.txt</p>）
    v2ray_m = re.search(r'v2ray[^\n]*?订阅链接.*?(https?://[^\s<"\'`]+\.txt)', content, re.DOTALL | re.IGNORECASE)
    if not v2ray_m:
        v2ray_m = re.search(r'(https?://[^\s<"\'`]+\.txt)', content, re.IGNORECASE)
    v2ray_url = v2ray_m.group(1).strip() if v2ray_m else None

    print(f"[+] 提取到的 Clash 订阅: {clash_url}")
    print(f"[+] 提取到的 V2Ray 订阅: {v2ray_url}")

    # 3. 下载并无损保存 clash_mibei.txt
    if clash_url:
        print(f"[*] 正在下载 Clash 订阅内容...")
        c_sub_resp = fetch_url(clash_url, headers=headers, timeout=REQUEST_TIMEOUT)
        c_sub_resp.raise_for_status()
        with open(MIBEI_OUTPUT_CLASH, "wb") as f:
            f.write(c_sub_resp.content)
        size_kb = len(c_sub_resp.content) / 1024
        print(f"🎉 [MiBei源] Clash 写入完成 -> {MIBEI_OUTPUT_CLASH} (大小: {size_kb:.2f} KB)")
    else:
        print(f"[-] [MiBei源] 未获取到 Clash 订阅链接，跳过保存。")

    # 4. 下载并无损保存 v2ray_mibei.txt
    if v2ray_url:
        print(f"[*] 正在下载 V2Ray 订阅内容...")
        v_sub_resp = fetch_url(v2ray_url, headers=headers, timeout=REQUEST_TIMEOUT)
        v_sub_resp.raise_for_status()
        with open(MIBEI_OUTPUT_V2RAY, "wb") as f:
            f.write(v_sub_resp.content)
        size_kb = len(v_sub_resp.content) / 1024
        print(f"🎉 [MiBei源] V2ray 写入完成 -> {MIBEI_OUTPUT_V2RAY} (大小: {size_kb:.2f} KB)")
    else:
        print(f"[-] [MiBei源] 未获取到 V2Ray 订阅链接，跳过保存。")

    # 5. 解析 clash_mibei.txt 中的节点，重组并生成 singbox_mibei.json
    if not os.path.exists(MIBEI_OUTPUT_CLASH):
        print(f"[-] [MiBei源] {MIBEI_OUTPUT_CLASH} 不存在，无法生成 Sing-box。")
        return

    try:
        with open(MIBEI_OUTPUT_CLASH, 'r', encoding='utf-8') as f:
            mibei_clash_data = yaml.safe_load(f)

        if not isinstance(mibei_clash_data, dict) or 'proxies' not in mibei_clash_data:
            print(f"[-] [MiBei源] 解析 {MIBEI_OUTPUT_CLASH} 失败：未找到有效 proxies 列表。")
            return

        proxies = mibei_clash_data.get('proxies', [])
        print(f"[*] 正在将 MiBei {len(proxies)} 个节点转换为 Sing-box 格式...")

        singbox_outbounds = []
        seen_tags = set()
        skipped = 0

        for node in proxies:
            # 确保节点标签唯一
            orig_name = str(node.get('name', '')).strip()
            if not orig_name:
                orig_name = f"{node.get('type', 'node')}-{node.get('server', '')}"

            tag_name = orig_name
            counter = 1
            while tag_name in seen_tags:
                tag_name = f"{orig_name}_{counter}"
                counter += 1
            seen_tags.add(tag_name)
            node['name'] = tag_name

            sb_node = convert_clash_to_singbox(node)
            if sb_node:
                singbox_outbounds.append(sb_node)
            else:
                skipped += 1

        if singbox_outbounds:
            singbox_config = build_full_singbox_config(singbox_outbounds)
            with open(MIBEI_OUTPUT_SINGBOX, 'w', encoding='utf-8') as f:
                json.dump(singbox_config, f, indent=2, ensure_ascii=False)
            skip_msg = f"（跳过 {skipped} 个不支持的节点）" if skipped else ""
            print(f"🎉 [MiBei源] Sing-box 写入完成 -> {MIBEI_OUTPUT_SINGBOX} (共 {len(singbox_outbounds)} 个节点{skip_msg})")
        else:
            print(f"[-] [MiBei源] 未能成功转换出任何 Sing-box 节点。")

    except Exception as e:
        print(f"[-] [MiBei源] 生成 {MIBEI_OUTPUT_SINGBOX} 失败: {e}")


# ================= 主入口 =================

def main():
    print("=" * 60)
    print("        全自动代理订阅聚合与更新系统 (GitHub + YoyaPai + MiBei)")
    print("=" * 60)

    # 1. 执行原有 GitHub 聚合源处理任务
    try:
        process_github_sources()
    except Exception as e:
        print(f"[-] 原有 GitHub 聚合源执行发生异常: {e}")

    # 2. 执行新增 YoyaPai 独立源处理任务
    try:
        process_yoyapai_source()
    except Exception as e:
        print(f"[-] 新增 YoyaPai 独立源执行发生异常: {e}")

    # 3. 执行新增 MiBei 独立源处理任务
    try:
        process_mibei_source()
    except Exception as e:
        print(f"[-] 新增 MiBei 独立源执行发生异常: {e}")

    print("\n" + "=" * 60)
    print("[+] 所有订阅更新任务已执行完毕！")
    print("=" * 60)


if __name__ == "__main__":
    main()
