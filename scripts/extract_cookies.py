#!/usr/bin/env python3
"""
本地 Cookie 提取脚本
从 Chrome/Edge 浏览器提取各公益站的 session cookie，生成 ANYROUTER_ACCOUNTS 格式

使用方法:
1. 先在浏览器中登录各公益站
2. 运行此脚本: python scripts/extract_cookies.py
3. 复制生成的 JSON 到 GitHub Secrets

依赖安装: pip install browser_cookie3
"""

import json
import sys

try:
    import browser_cookie3
except ImportError:
    print("❌ 请先安装 browser_cookie3: pip install browser_cookie3")
    sys.exit(1)

# 公益站域名配置
SITES = {
    "wong": {
        "domain": "api.wongapi.com",
        "provider": "wong",
    },
    "anyrouter": {
        "domain": "api.anyrouter.top", 
        "provider": "anyrouter",
    },
    "elysiver": {
        "domain": "api.elysiver.com",
        "provider": "elysiver",
    },
    "kfcapi": {
        "domain": "kfcapi.com",
        "provider": "kfcapi",
    },
    "duckcoding": {
        "domain": "api.duckcoding.top",
        "provider": "duckcoding",
    },
    "runanytime": {
        "domain": "api.runanytime.top",
        "provider": "runanytime",
    },
    "neb": {
        "domain": "api.neb.lol",
        "provider": "neb",
    },
}


def extract_site_cookies(domain: str, browser_func) -> dict | None:
    """从指定浏览器提取某站点的 cookies"""
    try:
        cj = browser_func(domain_name=domain)
        cookies = {c.name: c.value for c in cj}
        
        # 查找 session cookie (通常名为 session)
        session = cookies.get("session")
        if session:
            return {"session": session}
    except PermissionError:
        # 浏览器正在运行，数据库被锁定
        return None
    except Exception:
        return None
    return None


def extract_all_cookies():
    """提取所有站点的 cookies"""
    # 尝试的浏览器顺序
    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Edge", browser_cookie3.edge),
        ("Firefox", browser_cookie3.firefox),
    ]
    
    results = []
    
    for site_name, site_config in SITES.items():
        domain = site_config["domain"]
        provider = site_config["provider"]
        
        print(f"\n🔍 正在提取 {site_name} ({domain})...")
        
        cookies = None
        used_browser = None
        
        for browser_name, browser_func in browsers:
            cookies = extract_site_cookies(domain, browser_func)
            if cookies:
                used_browser = browser_name
                break
        
        if cookies:
            print(f"   ✅ 从 {used_browser} 提取成功")
            
            # 构建账号配置
            account = {
                "name": site_name,
                "provider": provider,
                "cookies": cookies,
                # api_user 需要手动填写，因为它在页面上而非 cookie 中
                "api_user": "TODO_填写你的用户ID",
            }
            results.append(account)
        else:
            print(f"   ❌ 未找到有效 session (可能未登录或 cookie 已过期)")
    
    return results


def main():
    print("=" * 50)
    print("🍪 公益站 Cookie 提取工具")
    print("=" * 50)
    print("\n⚠️  请确保:")
    print("   1. 已在浏览器中登录各公益站")
    print("   2. 浏览器已关闭 (某些浏览器锁定数据库)")
    
    accounts = extract_all_cookies()
    
    if not accounts:
        print("\n❌ 未提取到任何有效 Cookie")
        return
    
    print("\n" + "=" * 50)
    print(f"✅ 成功提取 {len(accounts)} 个站点的 Cookie")
    print("=" * 50)
    
    # 输出 JSON
    output = json.dumps(accounts, indent=2, ensure_ascii=False)
    
    print("\n📋 ANYROUTER_ACCOUNTS 配置 (复制到 GitHub Secrets):\n")
    print(output)
    
    # 保存到文件
    output_file = "cookies_output.json"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"\n💾 已保存到 {output_file}")
    
    print("\n⚠️  注意: api_user 需要手动填写!")
    print("   登录各站点后，在个人中心或 API 页面查看你的用户 ID")


if __name__ == "__main__":
    main()
