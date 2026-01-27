# 多平台签到工具

## 项目描述

这个项目用于自动签到多个平台，目前支持：

- **LinuxDo** - 自动登录并浏览帖子
- **AnyRouter/AgentRouter** - 自动签到并查询余额

使用 Python 实现，支持 GitHub Actions 自动运行。

## 功能

- 🔐 自动登录 LinuxDo 并浏览帖子
- 💰 自动签到 AnyRouter/AgentRouter 并查询余额
- 📱 支持 11 种通知渠道（Telegram、钉钉、飞书、企业微信等）
- ⏰ 支持 GitHub Actions 定时自动运行
- 🔧 支持命令行参数指定平台

## 环境变量配置

### LinuxDo 配置

支持两种配置方式：

#### 方式一：JSON 多账号配置（推荐）

| 环境变量名称         | 描述                    | 示例值     |
| -------------------- | ----------------------- | ---------- |
| `LINUXDO_ACCOUNTS` | LinuxDo 账号配置 (JSON) | 见下方示例 |

```json
[
  {
    "username": "user1@example.com",
    "password": "password1",
    "browse_enabled": true,
    "name": "主账号"
  },
  {
    "username": "user2@example.com",
    "password": "password2",
    "browse_enabled": false,
    "name": "小号"
  }
]
```

#### 方式二：单账号配置（向后兼容）

| 环境变量名称         | 描述                 | 示例值                       |
| -------------------- | -------------------- | ---------------------------- |
| `LINUXDO_USERNAME` | LinuxDo 用户名或邮箱 | `your_username`            |
| `LINUXDO_PASSWORD` | LinuxDo 密码         | `your_password`            |
| `BROWSE_ENABLED`   | 是否启用浏览帖子功能 | `true` (默认) 或 `false` |

> 注：旧版环境变量 `USERNAME` 和 `PASSWORD` 仍然可用

### AnyRouter 配置

| 环境变量名称           | 描述                              | 示例值     |
| ---------------------- | --------------------------------- | ---------- |
| `ANYROUTER_ACCOUNTS` | AnyRouter 账号配置 (JSON)         | 见下方示例 |
| `PROVIDERS`          | 自定义 Provider 配置 (JSON，可选) | 见下方示例 |

#### ANYROUTER_ACCOUNTS 格式

```json
[
  {
    "cookies": {"session": "MTc2ODc4NzQzNHxEWDhFQVFMX2dBQUJFQUVRQUFE..."},
    "api_user": "68121",
    "provider": "anyrouter",
    "name": "账号1"
  },
  {
    "cookies": {"session": "MTc2OTEwNDAyMHxEWDhFQVFMX2dBQUJFQUVRQUFE..."},
    "api_user": "59286",
    "provider": "anyrouter",
    "name": "账号2"
  }
]
```

> 注：`cookies` 只需要 `session` 字段即可，其他 CDN cookie（如 `acw_tc`）不需要保存。

#### PROVIDERS 格式（可选）

```json
{
  "custom_provider": {
    "name": "Custom Provider",
    "domain": "https://custom.example.com",
    "sign_in_path": "/api/user/sign_in",
    "user_info_path": "/api/user/self",
    "api_user_key": "new-api-user",
    "bypass_method": "waf_cookies",
    "waf_cookie_names": ["cf_clearance"]
  }
}
```

### 通知配置

支持以下通知渠道（均为可选）：

| 环境变量                       | 描述                                                          |
| ------------------------------ | ------------------------------------------------------------- |
| **Email**                |                                                               |
| `EMAIL_USER`                 | 发件邮箱账号                                                  |
| `EMAIL_PASS`                 | 发件邮箱密码/授权码                                           |
| `EMAIL_TO`                   | 收件邮箱地址                                                  |
| `EMAIL_SENDER`               | 发件人显示名称（可选）                                        |
| `CUSTOM_SMTP_SERVER`         | 自定义 SMTP 服务器（可选）                                    |
| **Gotify**               |                                                               |
| `GOTIFY_URL`                 | Gotify 服务器地址                                             |
| `GOTIFY_TOKEN`               | Gotify 应用 Token                                             |
| `GOTIFY_PRIORITY`            | 消息优先级（可选，默认 9）                                    |
| **Server酱 Turbo (SCT)** |                                                               |
| `SC3_PUSH_KEY`               | Server酱 Turbo SendKey (从 https://sct.ftqq.com/sendkey 获取) |
| **wxpush**               |                                                               |
| `WXPUSH_URL`                 | wxpush 服务器地址                                             |
| `WXPUSH_TOKEN`               | wxpush Token                                                  |
| **Telegram**             |                                                               |
| `TELEGRAM_BOT_TOKEN`         | Telegram Bot Token                                            |
| `TELEGRAM_CHAT_ID`           | Telegram Chat ID                                              |
| **PushPlus**             |                                                               |
| `PUSHPLUS_TOKEN`             | PushPlus Token                                                |
| **Server酱 (旧版)**      |                                                               |
| `SERVERPUSHKEY`              | Server酱 SCKEY                                                |
| **钉钉**                 |                                                               |
| `DINGDING_WEBHOOK`           | 钉钉机器人 Webhook URL                                        |
| **飞书**                 |                                                               |
| `FEISHU_WEBHOOK`             | 飞书机器人 Webhook URL                                        |
| **企业微信**             |                                                               |
| `WEIXIN_WEBHOOK`             | 企业微信机器人 Webhook URL                                    |
| **Bark**                 |                                                               |
| `BARK_KEY`                   | Bark 推送 Key                                                 |
| `BARK_SERVER`                | Bark 服务器地址（可选）                                       |

## 使用方法

### 命令行使用

```bash
# 安装依赖
uv sync

# 运行所有平台签到
uv run python main.py

# 仅运行 LinuxDo 签到
uv run python main.py --platform linuxdo

# 仅运行 AnyRouter 签到
uv run python main.py --platform anyrouter

# 干运行模式（仅显示配置）
uv run python main.py --dry-run

# 启用调试日志
uv run python main.py --debug
```

### GitHub Actions 自动运行

项目提供三个工作流：

1. **daily-check-in.yml** - 统一签到（每12小时运行，支持手动选择平台）
2. **linuxdo-only.yml** - 仅 LinuxDo 签到（每12小时运行）
3. **anyrouter-only.yml** - 仅 AnyRouter 签到（每12小时运行）

#### 配置步骤

1. Fork 本仓库（或直接推送到你的仓库）
2. 在仓库 `Settings` → `Secrets and variables` → `Actions` → `New repository secret` 中添加以下 Secrets：

   **必须配置（根据你要签到的平台）：**

   - `LINUXDO_ACCOUNTS` - LinuxDo 账号 JSON（多账号）
   - 或 `LINUXDO_USERNAME` + `LINUXDO_PASSWORD` - LinuxDo 单账号
   - `ANYROUTER_ACCOUNTS` - AnyRouter 账号 JSON

   **可选配置（通知，选一个即可）：**

   - `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` - Telegram 通知
   - `PUSHPLUS_TOKEN` - PushPlus 微信通知
   - `SC3_PUSH_KEY` - Server酱 Turbo 通知 (https://sct.ftqq.com/sendkey)

   **防止 Actions 被禁用（推荐配置）：**

   - `ACTIONS_TRIGGER_PAT` - GitHub Personal Access Token，用于保持 Actions 活跃

3. 进入 `Actions` 选项卡，点击 `I understand my workflows, go ahead and enable them` 启用工作流
4. 工作流会按计划自动运行（每12小时一次）

#### 配置 ACTIONS_TRIGGER_PAT（防止 Actions 被自动禁用）

GitHub 会在仓库 60 天无活动后自动禁用定时任务。配置此 Token 可防止签到任务被停用。

**生成 Token：**

1. 打开 https://github.com/settings/tokens?type=beta
2. 点击 "Generate new token"
3. 设置：
   - Token name: `workflow-immortality`
   - Expiration: 建议选 1 年
   - Repository access: 选 "Only select repositories" → 选择本仓库
   - Permissions → Repository permissions：
     - **Actions**: `Read and write`
     - **Workflows**: `Read and write`
4. 点击 "Generate token"，复制生成的 Token

**添加到仓库：**

1. 打开仓库 Settings → Secrets and variables → Actions
2. 点击 "New repository secret"
3. Name: `ACTIONS_TRIGGER_PAT`
4. Secret: 粘贴刚才复制的 Token
5. 点击 "Add secret"

配置完成后，`immortality.yml` 工作流会每月自动运行一次，保持仓库活跃。

#### 手动触发

1. 进入 `Actions` 选项卡
2. 选择要运行的工作流
3. 点击 `Run workflow`

## 项目结构

```
sign-in/
├── main.py                    # 主入口
├── pyproject.toml             # 项目配置
├── platforms/                 # 平台适配器
│   ├── base.py               # 基础适配器
│   ├── linuxdo.py            # LinuxDo 适配器
│   ├── anyrouter.py          # AnyRouter 适配器
│   └── manager.py            # 平台管理器
├── utils/                     # 工具模块
│   ├── config.py             # 配置管理
│   ├── notify.py             # 通知管理
│   ├── retry.py              # 重试装饰器
│   └── logging.py            # 日志配置
└── .github/workflows/         # GitHub Actions
``` .github/workflows/         # GitHub Actions
```

## 开发

```bash
# 安装开发依赖
uv sync

# 运行测试
uv run pytest

# 运行测试（详细输出）
uv run pytest -v
```

## 许可证

MIT License
