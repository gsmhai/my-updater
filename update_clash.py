import requests
import re

# 目标仓库 README 的 Raw 地址
SOURCE_URL = "https://raw.githubusercontent.com/mksshare/mksshare.github.io/main/README.md"
SOURCE_URL = "https://raw.githubusercontent.com/mksshare/abshare3.github.io/main/README.md"
SOURCE_URL = "https://raw.githubusercontent.com/toshare5/toshare5.github.io/main/README.md"


OUTPUT_CLASH = "clash_sub.txt"
OUTPUT_V2RAY = "v2ray_sub.txt"

def fetch_and_save(content, header_keyword, output_file, user_agent):
    pattern = f"{header_keyword}.*?(https://[^\\s'\"`<>]+)"
    match = re.search(pattern, content, re.S)
    
    if match:
        sub_url = match.group(1).strip()
        print(f"[{header_keyword}] 成功提取到地址: {sub_url}")
        
        try:
            # 使用最新的活跃客户端 User-Agent 进行伪装
            headers = {"User-Agent": user_agent}
            sub_response = requests.get(sub_url, headers=headers, timeout=15)
            sub_response.raise_for_status()
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(sub_response.text)
            print(f"[{header_keyword}] 订阅内容已成功同步到 {output_file} \n")
        except Exception as e:
            print(f"[{header_keyword}] 下载节点内容时出错: {e} \n")
    else:
        print(f"[{header_keyword}] 未能匹配到订阅链接。\n")

def main():
    try:
        print("正在获取目标仓库的 README 内容...")
        github_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        response = requests.get(SOURCE_URL, headers=github_headers, timeout=15)
        response.raise_for_status()
        content = response.text
        
        # 【关键修改】伪装成最新的 clash-verge 或其内核 mihomo
        fetch_and_save(content, "免费Clash订阅链接", OUTPUT_CLASH, "clash-verge/v2.4.8")
        
        # 将 v2rayN 版本号也稍微调高一点，伪装成较新的版本
        fetch_and_save(content, "免费v2rayN订阅链接", OUTPUT_V2RAY, "v2rayN/7.17")
        
    except Exception as e:
        print(f"获取目标 README 失败: {e}")

if __name__ == "__main__":
    main()
