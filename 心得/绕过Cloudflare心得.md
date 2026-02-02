# 绕过 Cloudflare 心得总结

> **最后验证时间：2026年2月3日**

## 🎯 一句话核心

**nodriver + Xvfb 虚拟显示 + 非 headless 模式 = 绕过 Cloudflare**

## 🔑 为什么能绕过？

| 技术 | 作用 |
|------|------|
| **nodriver** | 直接用 CDP 协议控制 Chrome，没有 `navigator.webdriver` 特征 |
| **Xvfb 虚拟显示** | 让浏览器以为自己在真实桌面环境运行 |
| **非 headless 模式** | Cloudflare 检测 headless 缺少渲染栈，非 headless 能骗过它 |

**对比其他方案：**
- ❌ Selenium/ChromeDriver - 有 `navigator.webdriver` 特征，秒被检测
- ❌ Playwright headless - 缺少渲染栈，容易被识别
- ❌ curl_cffi - 无法通过 JS 挑战
- ✅ **nodriver + Xvfb** - 目前最有效的方案

---

## 📋 完整配置步骤

### 第 1 步：GitHub Actions Workflow 配置

```yaml
jobs:
  browse:
    runs-on: ubuntu-22.04
    steps:
      # 安装 Xvfb 和 Chrome
      - name: Install Xvfb and Chrome
        run: |
          sudo apt-get update
          sudo apt-get install -y xvfb google-chrome-stable

      # 运行脚本（关键：设置 DISPLAY 环境变量）
      - name: Run script
        env:
          DISPLAY: ":99"  # 关键！指向 Xvfb 虚拟显示
        run: |
          # 启动 Xvfb 虚拟显示
          Xvfb :99 -screen 0 1920x1080x24 &
          sleep 2
          
          # 运行 Python 脚本
          python your_script.py
```

### 第 2 步：Python nodriver 配置

```python
import nodriver as uc
import os

# 检测 CI 环境
is_ci = bool(os.environ.get("CI")) or bool(os.environ.get("GITHUB_ACTIONS"))
display_set = bool(os.environ.get("DISPLAY"))

# 关键配置
config = uc.Config(
    headless=False,   # 🔑 关键：非 headless 模式（配合 Xvfb）
    sandbox=False,    # 🔑 关键：CI 环境必须关闭沙箱
    browser_args=[
        "--disable-blink-features=AutomationControlled",  # 隐藏自动化特征
        "--disable-dev-shm-usage",  # 避免 /dev/shm 空间不足
        "--no-first-run",
        "--window-size=1920,1080",
    ],
)

browser = await uc.start(config=config)
```

### 第 3 步：等待 Cloudflare 验证通过

```python
async def wait_for_cloudflare(tab, timeout=30):
    """等待 Cloudflare 挑战完成"""
    import asyncio
    import time
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        title = await tab.evaluate("document.title")
        
        # Cloudflare 挑战页面特征
        cf_indicators = ["just a moment", "checking your browser", "please wait"]
        
        if not any(ind in title.lower() for ind in cf_indicators):
            print("✅ Cloudflare 验证通过！")
            return True
        
        await asyncio.sleep(2)
    
    print("❌ Cloudflare 验证超时")
    return False

# 使用方式：先访问首页等验证通过，再访问目标页面
tab = await browser.get("https://example.com")
await wait_for_cloudflare(tab)
await tab.get("https://example.com/login")  # 再访问登录页
```

---

## ⚠️ 踩坑记录

### 坑 1：nodriver 启动失败

**现象：** `Failed to connect to browser`

**原因：** CI 环境中 nodriver 启动不稳定

**解决：** 增加重试机制，CI 环境建议 5 次重试

```python
async def start_browser_with_retry(config, max_retries=5):
    for attempt in range(max_retries):
        try:
            browser = await uc.start(config=config)
            print(f"✅ 第 {attempt + 1} 次尝试启动成功")
            return browser
        except Exception as e:
            print(f"❌ 第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)  # 递增等待：2s, 4s, 6s...
                await asyncio.sleep(wait_time)
            else:
                raise
```

### 坑 2：登录表单填不进去

**现象：** 日志显示"已输入用户名"，但登录报错 `Please enter your email or username`

**原因：** nodriver 的 `send_keys()` 在 CI 环境可能丢失字符

**解决：** 用 JavaScript 直接赋值，不用 `send_keys()`

```python
# ❌ 不可靠
await input_element.send_keys(username)

# ✅ 可靠：JS 直接赋值
await tab.evaluate(f"""
    (function() {{
        const input = document.querySelector('#login-account-name');
        if (input) {{
            input.focus();
            input.value = '{username}';
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }})()
""")
```

**注意：** 密码中的特殊字符（`'` `\`）需要转义！

### 坑 3：Cloudflare 验证超时

**现象：** 一直卡在 "Just a moment..."

**可能原因：**
1. 没有使用 Xvfb 虚拟显示
2. 使用了 headless 模式
3. GitHub Actions IP 被限流

**解决：**
1. 确保 `DISPLAY=:99` 环境变量设置正确
2. 确保 `headless=False`
3. 增加超时时间，或等待一段时间后重试

### 坑 4：Cloudflare Turnstile 交互式验证（2025 新增）

**现象：** 页面显示"确认您是真人"复选框，需要手动点击

**原因：** Cloudflare Turnstile 是一种交互式验证。**重要发现：2025 年的 Turnstile 通常被包裹在封闭的 Shadow DOM 中**，导致：
- `document.querySelectorAll('iframe')` 返回 0 个结果
- 传统的 querySelector 无法访问内部元素
- 必须通过定位外层容器 + 坐标点击来解决

**解决方案：** 定位 `.cf-turnstile` 容器，然后坐标点击

```python
async def click_turnstile(tab):
    """点击 Cloudflare Turnstile 复选框（支持 Shadow DOM）"""
    # 1. 获取 Turnstile 容器的位置（不是 iframe！）
    container_rect = await tab.evaluate(r"""
        (function() {
            // 优先查找容器（即使 iframe 在 Shadow DOM 中不可见）
            const containerSelectors = [
                '.cf-turnstile',
                'div[data-sitekey]',
                '#turnstile-wrapper',
                'div[id*="turnstile"]',
                'div[class*="turnstile"]'
            ];
            for (const sel of containerSelectors) {
                const container = document.querySelector(sel);
                if (container) {
                    const rect = container.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                    }
                }
            }
            return null;
        })()
    """)
    
    if container_rect:
        # 2. 复选框位置：容器左上角偏移约 (40, 40) 像素
        # 这是 Turnstile 复选框的标准位置
        click_x = container_rect["x"] + 40
        click_y = container_rect["y"] + 40
        
        # 3. 使用 nodriver 的 mouse_click 点击坐标
        await tab.mouse_click(click_x, click_y)
        print(f"✅ 已点击 Turnstile 复选框 ({click_x}, {click_y})")
```

**检测 Turnstile 页面的方法：**
```python
# 检查页面是否有 Turnstile 验证（支持 Shadow DOM 场景）
turnstile_info = await tab.evaluate(r"""
    (function() {
        const result = { hasContainer: false, hasText: false };
        
        // 检查容器（关键：即使 iframe 不可见，容器通常可见）
        const containerSelectors = ['.cf-turnstile', 'div[data-sitekey]', '#turnstile-wrapper'];
        for (const sel of containerSelectors) {
            if (document.querySelector(sel)) {
                result.hasContainer = true;
                break;
            }
        }
        
        // 检查页面文字
        const bodyText = document.body?.innerText || '';
        const cfTexts = ['确认您是真人', '验证您是真人', 'verify you are human'];
        result.hasText = cfTexts.some(t => bodyText.toLowerCase().includes(t.toLowerCase()));
        
        return result;
    })()
""")
has_turnstile = turnstile_info["hasContainer"] or turnstile_info["hasText"]
```

**注意事项：**
- **不要依赖 iframe 检测！** 2025 年的 Turnstile 可能在封闭 Shadow DOM 中，iframe 数量为 0
- 复选框位置是固定的，通常在容器左上角偏移 (40, 40) 像素
- 点击后需要等待 4-5 秒让验证处理
- 可以多次尝试点击（最多 3 次），因为第一次可能没点中
- 如果点击后一直转圈，可能是浏览器指纹被标记，需要更换 IP 或优化指纹
- 避免直接点击 input 元素，点击 span 或容器区域更隐蔽

---

## 📊 浏览行为优化（防止被论坛检测）

模拟真实用户阅读行为，避免被 Discourse 论坛检测为机器人：

```python
config = {
    "scroll_delay": (5, 8),      # 每次滚动间隔 5-8 秒
    "scroll_distance": (200, 500),  # 随机滚动距离
    "scroll_back_chance": 0.2,   # 20% 概率回滚（模拟回看）
    "like_chance": 0.3,          # 30% 概率点赞
}
```

**关键点：**
- 滚动间隔要够长（5-8 秒），模拟真实阅读
- 滚动距离要随机，避免机械化
- 偶尔回滚，模拟回看之前内容
- 按时间控制浏览，而不是按帖子数量

---

## 📚 参考资源

- [nodriver GitHub](https://github.com/ultrafunkamsterdam/nodriver) - 官方仓库
- [Bypassing Cloudflare with Nodriver](https://substack.thewebscraping.club/p/bypassing-cloudflare-with-nodriver) - 详细教程
- [Bypass Cloudflare for GitHub Action](https://github.com/marketplace/actions/bypass-cloudflare-for-github-action) - GitHub Action 方案
