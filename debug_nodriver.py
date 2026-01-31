#!/usr/bin/env python3
"""调试 nodriver 按钮查找"""
import asyncio
import nodriver as uc

async def main():
    browser = await uc.start(headless=False)
    tab = await browser.get("https://wzw.pp.ua/login")
    
    await asyncio.sleep(5)  # 等待页面加载
    
    print("=" * 60)
    print("尝试查找 LinuxDO 按钮...")
    print("=" * 60)
    
    # 方式1: find 文本
    try:
        btn = await tab.find("使用 LinuxDO 继续", timeout=3)
        print(f"方式1 (find 完整文本): 找到 - {btn}")
    except Exception as e:
        print(f"方式1 (find 完整文本): 失败 - {e}")
    
    # 方式2: find 部分文本
    try:
        btn = await tab.find("LinuxDO", timeout=3)
        print(f"方式2 (find LinuxDO): 找到 - {btn}")
    except Exception as e:
        print(f"方式2 (find LinuxDO): 失败 - {e}")
    
    # 方式3: select 按钮
    try:
        buttons = await tab.select_all('button')
        print(f"方式3 (select_all button): 找到 {len(buttons)} 个按钮")
        for i, btn in enumerate(buttons):
            try:
                text = await btn.get_property('innerText')
                print(f"  按钮 {i}: {text[:50] if text else 'N/A'}...")
            except:
                print(f"  按钮 {i}: 无法获取文本")
    except Exception as e:
        print(f"方式3 (select_all button): 失败 - {e}")
    
    # 方式4: 获取页面 HTML
    try:
        html = await tab.get_content()
        if "LinuxDO" in html:
            print("方式4: 页面 HTML 中包含 'LinuxDO'")
        else:
            print("方式4: 页面 HTML 中不包含 'LinuxDO'")
    except Exception as e:
        print(f"方式4: 失败 - {e}")
    
    # 方式5: 使用 JavaScript 查找
    try:
        result = await tab.evaluate("""
            const buttons = document.querySelectorAll('button');
            const texts = [];
            buttons.forEach(btn => texts.push(btn.innerText));
            return texts;
        """)
        print(f"方式5 (JS querySelectorAll): {result}")
    except Exception as e:
        print(f"方式5 (JS): 失败 - {e}")
    
    print("\n等待 30 秒后关闭...")
    await asyncio.sleep(30)
    browser.stop()

asynci