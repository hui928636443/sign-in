# 多平台签到工具

自动签到多个平台，支持 GitHub Actions 定时运行。

## 支持平台

- **LinuxDo** - 自动登录、浏览帖子、随机点赞
- **AnyRouter** - 自动签到、查询余额

## 功能特性

- 🔐 使用 Patchright（反检测 Playwright）自动化浏览器操作
- 📱 支持 11 种通知渠道
- ⏰ GitHub Actions 每 6 小时自动运行
- 🔧 支持多账号配置

## 环境变量配置

### LinuxDo 配置

#### JSON 多账号配置（推荐）

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
    "browse_enabled": true,
    "name": "小号"
  }
]
```

| 字段 | 说明 |
|------|------|
| `username` | 用户名或邮箱 |
| `password` | 密码 |
| `browse_enabled` | 是否浏览帖子 |
| `name` | 账号显示名称 |

#### 单账号配置（向后兼容）

| 环境变量 | 说明 |
|----------|------|
| `LINUXDO_USERNAME` | 用户名或邮箱 |
| `LINUXDO_PASSWORD` | 密码 |
| `BROWSE_ENABLED` | 是否浏览帖子（默认 true）|

### AnyRouter 配置

```json
[
  {
    "cookies": {"session": "MTc2ODc4NzQzNHxEWDhFQVFMX2dBQUJFQUVRQUFE..."},
    "api_user": "68121",
    "provider": "anyrouter",
    "name": "账号1"
  }
]
```

### 通知配置（可选）

| 渠道 | 环境变量 |
|------|----------|
| Email | `EMAIL_USER`, `EMAIL_PASS`, `EMAIL_TO` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| PushPlus | `PUSHPLUS_TOKEN` |
| Server酱 Turbo | `SC3_PUSH_KEY` |
| 钉钉 | `DINGDING_WEBHOOK` |
| 飞书 | `FEISHU_WEBHOOK` |
| 企业微信 | `WEIXIN_WEBHOOK` |
| Bark | `BARK_KEY`, `BARK_SERVER` |
| Gotify | `GOTIFY_URL`, `GOTIFY_TOKEN` |

## 使用方法

### 命令行

```bash
# 安装依赖
uv sync

# 运行所有平台
uv run python main.py

# 指定平台
uv run python main.py --platform linuxdo
uv run python main.py --platform anyrouter
```

### GitHub Actions

1. Fork 仓库
2. 添加 Secrets（Settings → Secrets and variables → Actions）：
   - `LINUXDO_ACCOUNTS` - LinuxDo 账号 JSON
   - `ANYROUTER_ACCOUNTS` - AnyRouter 账号 JSON
   - 通知渠道配置（可选）
3. 启用 Actions

工作流每 6 小时自动运行一次。

#### 防止 Actions 被禁用

GitHub 会在仓库 60 天无活动后禁用定时任务。配置 `ACTIONS_TRIGGER_PAT` 可防止：

1. 生成 Token：https://github.com/settings/tokens?type=beta
   - Repository access: 选择本仓库
   - Permissions: Actions `Read and write`, Workflows `Read and write`
2. 添加到 Secrets：`ACTIONS_TRIGGER_PAT`

## 项目结构

```
sign-in/
├── main.py                    # 主入口
├── platforms/                 # 平台适配器
│   ├── base.py               # 基础类
│   ├── linuxdo.py            # LinuxDo
│   ├── anyrouter.py          # AnyRouter
│   └── manager.py            # 平台管理
├── utils/                     # 工具模块
│   ├── config.py             # 配置管理
│   ├── notify.py             # 通知管理
│   ├── retry.py              # 重试装饰器
│   └── logging.py            # 日志配置
└── .github/workflows/         # GitHub Actions
    ├── daily-check-in.yml    # 签到任务（每6小时）
    └── immortality.yml       # 保活任务（每月）
```

## License

MIT
