#!/usr/bin/env python3
"""
Cookie 提取 GUI 工具
一键提取浏览器 Cookie，生成可直接复制到 GitHub Secrets 的 JSON

支持的浏览器：Edge, Chrome, Firefox
支持的提取方式：
1. rookiepy (推荐，支持新版浏览器加密)
2. browser_cookie3 (备用)

运行方式: uv run python scripts/cookie_gui.py
"""

import json
import subprocess
import sys
from datetime import datetime

# 日志文件
LOG_FILE = "cookie_extract.log"


def log(message: str):
    """写入日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception:
        pass


def check_and_install_deps():
    """检查并安装依赖"""
    import importlib.util

    missing = []

    if importlib.util.find_spec("customtkinter") is None:
        missing.append("customtkinter")

    # 优先使用 rookiepy
    if importlib.util.find_spec("rookiepy") is None:
        missing.append("rookiepy")

    # browser_cookie3 作为备用
    if importlib.util.find_spec("browser_cookie3") is None:
        missing.append("browser-cookie3")

    if missing:
        print(f"正在安装缺失的依赖: {', '.join(missing)}")
        try:
            subprocess.check_call(["uv", "add"] + missing)
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            except subprocess.CalledProcessError:
                print("\n❌ 自动安装失败，请手动运行:")
                print(f"   uv add {' '.join(missing)}")
                sys.exit(1)
        print("依赖安装完成，请重新运行脚本")
        sys.exit(0)


check_and_install_deps()

import customtkinter as ctk  # noqa: E402

# 尝试导入 cookie 提取库
try:
    import rookiepy
    HAS_ROOKIEPY = True
except ImportError:
    HAS_ROOKIEPY = False

try:
    import browser_cookie3
    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False


# 公益站配置 - 与 utils/config.py 中的 NEWAPI_SITES 保持一致
SITES_CONFIG = {
    "wong": {"domain": "wzw.pp.ua", "name": "WONG公益站"},
    "elysiver": {"domain": "h-e.top", "name": "Elysiver"},
    "kfcapi": {"domain": "kfc-api.sxxe.net", "name": "KFC API"},
    "duckcoding": {"domain": "free.duckcoding.com", "name": "Free DuckCoding"},
    "runanytime": {"domain": "runanytime.hxi.me", "name": "随时跑路"},
    "neb": {"domain": "ai.zzhdsgsss.xyz", "name": "NEB公益站"},
    "zeroliya": {"domain": "new.184772.xyz", "name": "小呆公益站"},
    "mitchll": {"domain": "api.mitchll.com", "name": "Mitchll-api"},
    "anyrouter": {"domain": "anyrouter.top", "name": "AnyRouter"},
    "linuxdo": {"domain": "linux.do", "name": "LinuxDO"},
}


class CookieExtractorApp(ctk.CTk):
    """Cookie 提取器主窗口"""

    def __init__(self):
        super().__init__()

        self.title("🍪 Cookie 提取工具")
        self.geometry("850x750")
        self.minsize(750, 650)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.accounts: list[dict] = []
        self.site_vars: dict[str, ctk.BooleanVar] = {}
        self.browser_var: ctk.StringVar = ctk.StringVar(value="Edge")

        self._create_ui()

    def _create_ui(self):
        """创建界面"""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 标题
        title_label = ctk.CTkLabel(
            main_frame,
            text="🍪 公益站 Cookie 一键提取",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.pack(pady=(0, 10))

        # 说明
        desc_text = "从浏览器提取 Cookie，生成 LINUXDO_ACCOUNTS 或 ANYROUTER_ACCOUNTS 配置"
        if HAS_ROOKIEPY:
            desc_text += "\n✅ 使用 rookiepy 提取（支持新版浏览器加密）"
        elif HAS_BROWSER_COOKIE3:
            desc_text += "\n⚠️ 使用 browser_cookie3 提取（可能不支持最新浏览器）"

        desc_label = ctk.CTkLabel(
            main_frame,
            text=desc_text,
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        desc_label.pack(pady=(0, 15))

        # 站点选择
        self._create_sites_section(main_frame)

        # 浏览器选择
        self._create_browser_section(main_frame)

        # 操作按钮
        self._create_buttons(main_frame)

        # 结果显示
        self._create_result_section(main_frame)

        # 状态栏
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="💡 请先在浏览器中登录各站点，然后点击「提取 Cookie」",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.status_label.pack(pady=(10, 0))

    def _create_sites_section(self, parent):
        """创建站点选择区域"""
        sites_frame = ctk.CTkFrame(parent)
        sites_frame.pack(fill="x", pady=(0, 15))

        header_frame = ctk.CTkFrame(sites_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            header_frame,
            text="选择要提取的站点",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        ctk.CTkButton(
            btn_frame, text="全选", width=60, height=28, command=self._select_all
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="取消",
            width=60,
            height=28,
            fg_color="gray",
            command=self._deselect_all,
        ).pack(side="left")

        # 站点网格
        grid_frame = ctk.CTkFrame(sites_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=15, pady=(0, 15))

        for i, (site_id, config) in enumerate(SITES_CONFIG.items()):
            row = i // 3
            col = i % 3

            site_frame = ctk.CTkFrame(grid_frame)
            site_frame.grid(row=row, column=col, padx=5, pady=5, sticky="ew")
            grid_frame.columnconfigure(col, weight=1)

            var = ctk.BooleanVar(value=True)
            self.site_vars[site_id] = var

            cb = ctk.CTkCheckBox(
                site_frame,
                text=f"{config['name']}",
                variable=var,
                font=ctk.CTkFont(size=12),
            )
            cb.pack(side="left", padx=10, pady=8)

    def _create_browser_section(self, parent):
        """创建浏览器选择区域"""
        browser_frame = ctk.CTkFrame(parent)
        browser_frame.pack(fill="x", pady=(0, 15))

        inner_frame = ctk.CTkFrame(browser_frame, fg_color="transparent")
        inner_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(
            inner_frame,
            text="选择浏览器:",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left", padx=(0, 15))

        for browser in ["Edge", "Chrome", "Firefox"]:
            rb = ctk.CTkRadioButton(
                inner_frame,
                text=browser,
                variable=self.browser_var,
                value=browser,
                font=ctk.CTkFont(size=13),
            )
            rb.pack(side="left", padx=10)

        ctk.CTkLabel(
            inner_frame,
            text="⚠️ 提取前请关闭浏览器",
            font=ctk.CTkFont(size=12),
            text_color="orange",
        ).pack(side="right")

    def _create_buttons(self, parent):
        """创建操作按钮"""
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 15))

        self.extract_btn = ctk.CTkButton(
            btn_frame,
            text="🔍 提取 Cookie",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=45,
            command=self._start_extract,
        )
        self.extract_btn.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.copy_btn = ctk.CTkButton(
            btn_frame,
            text="📋 复制到剪贴板",
            font=ctk.CTkFont(size=16),
            height=45,
            fg_color="#28a745",
            hover_color="#218838",
            command=self._copy_to_clipboard,
            state="disabled",
        )
        self.copy_btn.pack(side="left", expand=True, fill="x")

    def _create_result_section(self, parent):
        """创建结果显示区域"""
        result_frame = ctk.CTkFrame(parent)
        result_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            result_frame,
            text="📄 生成的 JSON (复制到 GitHub Secrets)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.result_text = ctk.CTkTextbox(
            result_frame, font=ctk.CTkFont(family="Consolas", size=12), wrap="none"
        )
        self.result_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _select_all(self):
        for var in self.site_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self.site_vars.values():
            var.set(False)

    def _start_extract(self):
        """开始提取"""
        self.extract_btn.configure(state="disabled", text="⏳ 提取中...")
        self.status_label.configure(text="正在从浏览器提取 Cookie...", text_color="yellow")
        self.update()
        self._do_extract()

    def _do_extract(self):
        """执行提取"""
        log("=" * 50)
        log("开始提取 Cookie")

        selected_browser = self.browser_var.get()
        log(f"选择的浏览器: {selected_browser}")

        selected_sites = [
            site_id for site_id, var in self.site_vars.items() if var.get()
        ]
        log(f"选中的站点: {selected_sites}")

        if not selected_sites:
            self._show_error("请至少选择一个站点")
            return

        results = []
        success_count = 0
        fail_sites = []

        # 优先使用 rookiepy
        if HAS_ROOKIEPY:
            log("使用 rookiepy 提取...")
            results, success_count, fail_sites = self._extract_with_rookiepy(
                selected_browser, selected_sites
            )
        elif HAS_BROWSER_COOKIE3:
            log("使用 browser_cookie3 提取...")
            results, success_count, fail_sites = self._extract_with_browser_cookie3(
                selected_browser, selected_sites
            )
        else:
            self._show_error("未安装 Cookie 提取库")
            return

        log(f"提取完成: 成功 {success_count}, 失败 {len(fail_sites)}")
        self._show_results(results, success_count, fail_sites)

    def _extract_with_rookiepy(
        self, browser: str, sites: list
    ) -> tuple[list, int, list]:
        """使用 rookiepy 提取 Cookie"""
        results = []
        success_count = 0
        fail_sites = []

        # 获取所有域名
        domains = [SITES_CONFIG[site_id]["domain"] for site_id in sites]

        try:
            # 根据浏览器选择提取函数
            if browser == "Edge":
                all_cookies = rookiepy.edge(domains)
            elif browser == "Chrome":
                all_cookies = rookiepy.chrome(domains)
            elif browser == "Firefox":
                all_cookies = rookiepy.firefox(domains)
            else:
                all_cookies = []

            log(f"rookiepy 获取到 {len(all_cookies)} 个 cookie")

            # 按域名分组
            cookies_by_domain = {}
            for cookie in all_cookies:
                domain = cookie.get("domain", "").lstrip(".")
                if domain not in cookies_by_domain:
                    cookies_by_domain[domain] = {}
                cookies_by_domain[domain][cookie["name"]] = cookie["value"]

            # 匹配站点
            for site_id in sites:
                config = SITES_CONFIG[site_id]
                domain = config["domain"]

                session = None
                for cookie_domain, cookies in cookies_by_domain.items():
                    if domain in cookie_domain or cookie_domain in domain:
                        session = cookies.get("session")
                        if session:
                            break

                if session:
                    success_count += 1
                    results.append({
                        "name": config["name"],
                        "provider": site_id,
                        "cookies": {"session": session},
                    })
                    log(f"  ✅ {config['name']}: 成功")
                else:
                    fail_sites.append(config["name"])
                    log(f"  ❌ {config['name']}: 未找到 session")

        except Exception as e:
            log(f"rookiepy 提取失败: {e}")
            for site_id in sites:
                fail_sites.append(SITES_CONFIG[site_id]["name"])

        return results, success_count, fail_sites

    def _extract_with_browser_cookie3(
        self, browser: str, sites: list
    ) -> tuple[list, int, list]:
        """使用 browser_cookie3 提取 Cookie"""
        results = []
        success_count = 0
        fail_sites = []

        browser_funcs = {
            "Edge": browser_cookie3.edge,
            "Chrome": browser_cookie3.chrome,
            "Firefox": browser_cookie3.firefox,
        }
        browser_func = browser_funcs.get(browser)

        if not browser_func:
            return results, success_count, sites

        for site_id in sites:
            config = SITES_CONFIG[site_id]
            domain = config["domain"]

            try:
                cj = browser_func(domain_name=domain)
                cookie_dict = {c.name: c.value for c in cj}
                session = cookie_dict.get("session")

                if session:
                    success_count += 1
                    results.append({
                        "name": config["name"],
                        "provider": site_id,
                        "cookies": {"session": session},
                    })
                    log(f"  ✅ {config['name']}: 成功")
                else:
                    fail_sites.append(config["name"])
                    log(f"  ❌ {config['name']}: 未找到 session")
            except Exception as e:
                fail_sites.append(config["name"])
                log(f"  ❌ {config['name']}: {e}")

        return results, success_count, fail_sites

    def _show_results(self, results: list, success: int, failed: list):
        """显示结果"""
        self.extract_btn.configure(state="normal", text="🔍 提取 Cookie")

        if not results:
            self.status_label.configure(
                text="❌ 未提取到任何 Cookie，请确保已登录并关闭浏览器",
                text_color="red",
            )
            return

        self.accounts = results
        json_str = json.dumps(results, indent=2, ensure_ascii=False)

        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", json_str)
        self.copy_btn.configure(state="normal")

        status = f"✅ 成功提取 {success} 个站点"
        if failed:
            status += f"  |  ❌ 失败: {', '.join(failed[:3])}"
            if len(failed) > 3:
                status += f" 等 {len(failed)} 个"

        self.status_label.configure(text=status, text_color="green")

    def _show_error(self, message: str):
        """显示错误"""
        self.extract_btn.configure(state="normal", text="🔍 提取 Cookie")
        self.status_label.configure(text=f"❌ {message}", text_color="red")

    def _copy_to_clipboard(self):
        """复制到剪贴板"""
        if not self.accounts:
            return

        json_str = json.dumps(self.accounts, ensure_ascii=False)
        self.clipboard_clear()
        self.clipboard_append(json_str)

        self.status_label.configure(
            text="✅ 已复制到剪贴板！去 GitHub Secrets 粘贴吧",
            text_color="green",
        )

        original_text = self.copy_btn.cget("text")
        self.copy_btn.configure(text="✅ 已复制!")
        self.after(2000, lambda: self.copy_btn.configure(text=original_text))


def main():
    app = CookieExtractorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
