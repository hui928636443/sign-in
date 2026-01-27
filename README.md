# 多平台签到工具

自动签到多个平台，支持 GitHub Actions 定时运行。

## 支持平台

- **LinuxDo** - 自动登录、浏览帖子、随机点赞
- **AnyRouter** - 自动签到、查询余额
- **WONG 公益站** - 自动签到、查询余额（wzw.pp.ua）

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

### AnyRouter 类平台配置（ANYROUTER_ACCOUNTS）

`ANYROUTER_ACCOUNTS` 环境变量支持多个平台，通过 `provider` 字段区分：

| provider | 平台 | 说明 |
|----------|------|------|
| `anyrouter` | AnyRouter | anyrouter.top（默认值）|
| `wong` | WONG 公益站 | wzw.pp.ua |

#### 配置格式

```json
[
  {
    "name": "账号名称",
    "provider": "anyrouter",
    "cookies": {"session": "session_cookie_value"},
    "api_user": "用户ID"
  }
]
```

| 字段 | 说明 |
|------|------|
| `name` | 账号显示名称 |
| `provider` | 平台类型：`anyrouter` 或 `wong` |
| `cookies` | Cookie 对象，包含 `session` 字段 |
| `api_user` | 用户 ID（请求头 `new-api-user` 的值）|

#### 混合配置示例

```json
[
  {"name": "AnyRouter主号", "provider": "anyrouter", "cookies": {"session": "MTc2ODc4..."}, "api_user": "59286"},
  {"name": "AnyRouter小号", "provider": "anyrouter", "cookies": {"session": "MTc2Nzkz..."}, "api_user": "60723"},
  {"name": "WONG账号", "provider": "wong", "cookies": {"session": "MTc2OTQ4..."}, "api_user": "12231"}
]
```

#### 获取 Cookie 和 api_user

1. 登录对应平台（anyrouter.top 或 wzw.pp.ua）
2. 打开浏览器开发者工具 (F12)
3. **Cookie**: Application
```

> ⚠️ **注意**: Cookie 会过期，过期后需要重新登录获取新的 session 值。

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
│   ├── wong.py               # WONG 公益站
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
