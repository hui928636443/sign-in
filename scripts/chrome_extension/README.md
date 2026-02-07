# NEWAPI 人工补录 Chrome 扩展

这个扩展专门用于 **GitHub Action 签到后人工补录**。

目标流程：
1. GitHub Action 跑完后，自动更新 `scripts/chrome_extension/failed_sites.json`
2. 本地 `git pull`
3. 打开扩展，点击“一键打开失败站点”
4. 你在浏览器里人工登录这些站点
5. 回到扩展，点击“提取失败站点 Cookie”
6. 复制生成结果，粘贴到 GitHub Secret `NEWAPI_ACCOUNTS`

## 安装

1. 打开 `chrome://extensions/` 或 `edge://extensions/`
2. 开启“开发者模式”
3. 选择“加载已解压的扩展程序”
4. 选择目录：`scripts/chrome_extension`

## 使用说明

### 1) 刷新失败清单
- 扩展会读取本地目录中的 `failed_sites.json`
- 如果提示读取失败，先确认仓库已 `pull` 到最新

### 2) 一键打开失败站点
- 按失败清单批量打开登录页
- 你手动登录（用于拿到最新 session cookie）

### 3) 生成 NEWAPI_ACCOUNTS
- 可选：先粘贴当前 `NEWAPI_ACCOUNTS`（用于合并）
- 点击“提取失败站点 Cookie”
- 扩展会按失败清单站点读取 `session` cookie，并尝试补齐 `api_user`
- 自动按 `provider + api_user` 去重，新的覆盖旧的

### 4) 复制到 GitHub
- 点击“复制结果 JSON”
- 贴到 GitHub Secret：`NEWAPI_ACCOUNTS`

## 说明

- 若某站点提取失败，通常是：
  - 还没登录成功
  - 没有 `session` cookie
  - 缺失 `api_user`
- 扩展会在提取结果里列出失败项，便于你继续补录。
