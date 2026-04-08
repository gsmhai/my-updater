import requests
import re
import yaml
import base64
import json
import urllib.parse
import os
from datetime import datetime

# ================= 配置区域 =================
SOURCES = [
    {"name": "tolinkshare2", "repo_url": "https://raw.githubusercontent.com/tolinkshare2/tolinkshare2.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "toshare5", "repo_url": "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "mkshare3", "repo_url": "https://raw.githubusercontent.com/mkshare3/mkshare3.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "abshare3", "repo_url": "https://raw.githubusercontent.com/abshare3/abshare3.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"},
    {"name": "mksshare", "repo_url": "https://raw.githubusercontent.com/mksshare/mksshare.github.io/main/README.md", "clash_keyword": "免费Clash订阅链接", "v2ray_keyword": "免费v2rayN订阅链接"}
]

HISTORY_FILE = "history.json"
MAX_HISTORY = 1000
OUTPUT_CLASH = "clash_sub.txt"
OUTPUT_V2RAY = "v2ray_sub.txt"
# ============================================

yaml.SafeDumper.ignore_aliases = lambda *args: True

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

def main():
    history = load_history()
    clash_headers = {"User-Agent": "clash-verge/v2.4.8"}
    v2ray_headers = {"User-Agent": "v2rayN/7.17"}
    github_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0"}
    
    global_seen_names = set()
    processed_sources = []
    
    final_clash_config = {}
    original_proxy_groups = []

    for source in SOURCES:
        s_name = source['name']
        print(f"\n[{s_name}] 正在解析仓库...")
        
        source_data = {"source_name": s_name, "update_time": "", "group_name": "", "clash_nodes": [], "v2ray_text": ""}

        try:
            resp = requests.get(source['repo_url'], headers=github_headers, timeout=15)
            resp.raise_for_status()
            content = resp.text

            # 提取当前页面的更新时间
            curr_update_time = re.search(r"更新时间[^\d]*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)", content)
            curr_time_str = curr_update_time.group(1).strip() if curr_update_time else ""
            source_data["update_time"] = curr_time_str

            # ================= 历史记录与平均时间计算 =================
            if s_name not in history:
                history[s_name] = {"last_update": "", "prev_update": "", "records": []}
            
            if curr_time_str and curr_time_str != history[s_name]["last_update"]:
                history[s_name]["prev_update"] = history[s_name]["last_update"]
                history[s_name]["last_update"] = curr_time_str
                history[s_name]["records"].append(curr_time_str)
                if len(history[s_name]["records"]) > MAX_HISTORY:
                    history[s_name]["records"].pop(0)

            avg_h = calculate_avg_hours(history[s_name]["records"])
            
            # 显示格式：上次:mm-dd hh:mm
            prev_update_show = history[s_name]["prev_update"][5:16] if history[s_name]["prev_update"] else "N/A"
            curr_update_short = curr_time_str[2:16] if curr_time_str else "N/A"
            # ========================================================

            # ========== 处理 Clash ==========
            clash_url = fetch_real_url(content, source['clash_keyword'])
            if clash_url:
                c_resp = requests.get(clash_url, headers=clash_headers, timeout=15)
                
                try:
                    yaml_data = yaml.safe_load(c_resp.text)
                    
                    if yaml_data and not final_clash_config:
                        for k, v in yaml_data.items():
                            if k not in ['proxies', 'proxy-groups']: final_clash_config[k] = v
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
                        
                        # 构建超级组名
                        p_traffic = f"{group_traffic:<8}" if group_traffic else "N/A     "
                        source_data["group_name"] = f"{s_name:<12} 剩余：{p_traffic} 更新：{curr_update_short}  上次：{prev_update_show}  [{avg_h}h]"

                        for node in nodes:
                            original_name = str(node.get('name', ''))
                            if "剩余流量" in original_name and group_traffic and curr_update_short != "N/A":
                                new_node_name = f"[{s_name}] 剩余：{group_traffic} 时间:{curr_update_short}"
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

            # ========== 处理 V2ray ==========
            v2ray_url = fetch_real_url(content, source['v2ray_keyword'])
            if v2ray_url:
                v_resp = requests.get(v2ray_url, headers=v2ray_headers, timeout=15)
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

    # ================= 写入文件阶段 (没有省略的完整版) =================
    
    # 保存 JSON 历史记录
    save_history(history)
    print("\n✅ 历史更新频率记录已保存至 history.json")

    # 按时间排序
    processed_sources.sort(key=lambda x: x["update_time"] if x["update_time"] else "9999-99-99 99:99:99")

    all_clash_proxies = []       
    our_5_groups = []        
    all_source_group_names = []  
    all_v2ray_nodes = ""

    for src in processed_sources:
        if src["clash_nodes"]:
            all_clash_proxies.extend(src["clash_nodes"])
            node_names = [n['name'] for n in src["clash_nodes"]]
            group = {"name": src["group_name"], "type": "select", "proxies": node_names}
            our_5_groups.append(group)
            all_source_group_names.append(src["group_name"])
            
        if src["v2ray_text"]:
            all_v2ray_nodes += f"\n# ===== {src['group_name']} =====\n"
            all_v2ray_nodes += src["v2ray_text"] + "\n"

    # 生成 Clash 文件
    if all_clash_proxies:
        for og_group in original_proxy_groups:
            og_group['proxies'] = all_source_group_names
            
        final_proxy_groups = original_proxy_groups + our_5_groups
        final_clash_config['proxies'] = all_clash_proxies
        final_clash_config['proxy-groups'] = final_proxy_groups
        
        with open(OUTPUT_CLASH, 'w', encoding='utf-8') as f:
            yaml.safe_dump(final_clash_config, f, allow_unicode=True, sort_keys=False)
        print(f"🎉 Clash 写入完成：共 {len(all_clash_proxies)} 个节点。")

    # 生成 V2ray 文件
    if all_v2ray_nodes.strip():
        final_v2ray_b64 = base64.b64encode(all_v2ray_nodes.strip().encode('utf-8')).decode('utf-8')
        with open(OUTPUT_V2RAY, 'w', encoding='utf-8') as f:
            f.write(final_v2ray_b64)
        print(f"🎉 V2ray 写入完成：已重新编码为 Base64。")

if __name__ == "__main__":
    main()