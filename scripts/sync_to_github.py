#!/usr/bin/env python3
"""
一键同步 Cookie 到 GitHub Secrets

使用方法:
1. 先安装 GitHub CLI: https://cli.github.com/
2. 登录: gh auth login
3. 运行: python scripts/sync_to_github.py

此脚本会:
1. 提取本地浏览器的公益站 Cookie
2. 自动更新到 GitHub 仓库的 ANYROUTER_ACCOUNTS secret
"""

import json
import subprocess
import sys
from pathlib import Path

# 导入提取脚本
sys.path.insert(0, str(Path(__file__).parent))
from extract_cookies import extract_all_cookies


def get_repo_name() -> str | None:
    """获取当前 Git 仓库名"""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        # 解析 git@github.com:user/repo.git 或 https://github.com/user/repo.git
        if "github.com" in url:
            if url.startswith("git@"):
                return url.split(":")[-1].replace(".git", "")
            else:
                return "/".join(url.split("/")[-2:]).replace(".git", "")
    except Exception:
        pass
    return None


def check_gh_cli() -> bool:
    """检查 GitHub CLI 是否可用"""
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def update_github_secret(repo: str, secret_name: str, value: str) -> bool:
    """更新 GitHub Secret"""
    try:
        result = subprocess.run(
            ["gh", "secret", "set", secret_name, "-R", repo],
            input=value,
            text=True,
            capture_output=True,
            check=False,  # 手动检查返回码
        )
        if result.returncode != 0:
            print(f"   stderr: {result.stderr}")
        return result.returncode == 0
    except FileNotFoundError:
        print("❌ 未找到 gh 命令，请安装 GitHub CLI")
        return False
    except Exception as e:
        print(f"❌ 更新失败: {e}")
        return False


def main():
    print("=" * 50)
    print("🚀 Cookie 一键同步到 GitHub Secrets")
    print("=" * 50)
    
    # 检查 gh cli
    if not check_gh_cli():
        print("\n❌ 未安装 GitHub CLI")
        print("   请访问 https://cli.github.com/ 安装")
        print("   安装后运行: gh auth login")
        return
    
    # 获取仓库名
    repo = get_repo_name()
    if not repo:
        print("\n❌ 无法获取 GitHub 仓库名")
        print("   请确保在 Git 仓库目录下运行")
        return
    
    print(f"\n📦 目标仓库: {repo}")
    
    # 提取 cookies
    print("\n" + "-" * 50)
    accounts = extract_all_cookies()
    
    if not accounts:
        print("\n❌ 未提取到任何有效 Cookie，无法同步")
        return
    
    # 确认同步
    print("\n" + "-" * 50)
    print(f"📤 准备同步 {len(accounts)} 个账号到 ANYROUTER_ACCOUNTS")
    
    confirm = input("\n确认同步? (y/N): ").strip().lower()
    if confirm != "y":
        print("❌ 已取消")
        return
    
    # 同步到 GitHub
    value = json.dumps(accounts, ensure_ascii=False)
    
    print("\n⏳ 正在同步...")
    if update_github_secret(repo, "ANYROUTER_ACCOUNTS", value):
        print("✅ 同步成功!")
        print(f"   已更新 {repo} 的 ANYROUTER_ACCOUNTS secret")
    else:
        print("❌ 同步失败，请检查 GitHub CLI 权限")


if __name__ == "__main__":
    main()
