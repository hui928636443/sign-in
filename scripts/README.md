# Cookie 提取工具

由于 LinuxDO OAuth 被 Cloudflare Turnstile 拦截，需要手动提取浏览器 Cookie 来实现签到。

## 🎯 推荐：GUI 图形界面（傻瓜式操作）

```bash
# 1. 安装依赖
pip install customtkinter browser_cookie3

# 2. 运行 GUI
python scripts/cookie_gui.py
```

![GUI 截图](../docs/cookie_gui.png)

操作步骤：
1. 先在浏览器中登录各公益站
2. 关闭浏览器
3. 运行 GUI，点击「提取 Cookie」
4. 点击「复制到剪贴板」
5. 粘贴到 GitHub Secrets → ANYROUTER_ACCOUNTS

---

## 命令行版本

### 1. 安装依赖

```bash
pip install browser_cookie3
```

### 2. 在浏览器中登录各公益站

确保你已经在 Chrome/Edge/Firefox 中登录了以下站点：
- api.wongapi.com (WONG公益站)
- api.anyrouter.top (AnyRouter)
- api.elysiver.com (Elysiver)
- 等等...

### 3. 提取 Cookie

```bash
# 关闭浏览器后运行
python scripts/extract_cookies.py
```

### 4. 更新 GitHub Secrets

**方式一：手动复制**
1. 复制脚本输出的 JSON
2. 打开 GitHub 仓库 → Settings → Secrets → Actions
3. 更新 `ANYROUTER_ACCOUNTS`

**方式二：自动同步（推荐）**

先安装 [GitHub CLI](https://cli.github.com/)：
```bash
# Windows (winget)
winget install GitHub.cli

# 登录
gh auth login
```

然后一键同步：
```bash
python scripts/sync_to_github.py
```

## 注意事项

1. **api_user 需要手动填写**
   - 脚本只能提取 Cookie，无法获取用户 ID
   - 登录各站点后，在个人中心查看你的用户 ID

2. **Cookie 有效期**
   - 通常 2-4 周
   - 过期后需要重新提取

3. **浏览器锁定**
   - Chrome/Edge 运行时可能锁定 Cookie 数据库
   - 建议关闭浏览器后再运行脚本

## 定时自动更新（可选）

Windows 任务计划程序：
```powershell
# 每天早上 8 点自动提取并同步
schtasks /create /tn "SyncCookies" /tr "python C:\path\to\scripts\sync_to_github.py" /sc daily /st 08:00
```
