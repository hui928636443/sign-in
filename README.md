# Sign-in 多平台签到工具

自动签到多个公益站，支持 LinuxDO OAuth 登录和 Cookie 登录两种方式。

## 功能特性

- ✅ **AnyRouter 签到** - 使用 Cookie 方式
- ✅ **NEWAPI 类网站签到** - 优先使用 LinuxDO OAuth 登录，Cookie 作为备用
- ✅ **LinuxDO 浏览帖子** - 自动浏览帖子增加在线时间
- ✅ **Cookie 一键获取** - GUI 工具从浏览器提取 Cookie

## 支持的站点

| 站点 | 类型 | 登录方式 |
|------|------|----------|
| AnyRouter | AnyRouter | Cookie |
| WONG公益站 | NewAPI | LinuxDO OAuth / Cookie |
| Elysiver | NewAPI | LinuxDO OAuth / Cookie |
| KFC API | NewAPI | LinuxDO OAuth / Cookie |
| Free DuckCoding | NewAPI | LinuxDO OAuth / Cookie |
| 随时跑路 | NewAPI | LinuxDO OAuth / Cookie |
| NEB公益站 | NewAPI | LinuxDO OAuth / Cookie |
| 小呆公益站 | NewAPI | LinuxDO OAuth / Cookie |
| Mitchll-api | NewAPI | LinuxDO OAuth / Cookie |
| LinuxDO | Discourse | 账号密码 |

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

推荐使用 LinuxDO 统一账号（一次配置签到所有站点）：

```bash
# 简单配置（签到所有站点 + 浏览帖子）
export LINUXDO_USERNAME="your_username"
export LINUXDO_PASSWORD="your_password"

# 可选配置
export LINUXDO_BROWSE="true"        # 是否浏览帖子（默认 true）
export LINUXDO_BROWSE_COUNT="10"    # 浏览帖子数量（默认 10）
```

或使用 JSON 格式配置多账号：

```bash
export LINUXDO_ACCOUNTS='[
  {
    "username": "user1",
    "password": "pass1",
    "sites": ["wong", "elysiver", "kfcapi"],
    "browse_linuxdo": true,
    "browse_count": 10
  }
]'
```

### 3. 运行签到

```bash
# 运行所有平台签到
python main.py

# 仅运行指定平台
python main.py --platform linuxdo

# 干运行模式（仅显示配置）
python main.py --dry-run
```

## Cookie 一键获取

如果 OAuth 登录失败，可以使用 Cookie 方式。运行 GUI 工具从浏览器提取 Cookie：

```bash
python scripts/cookie_gui.py
```

1. 先在浏览器中登录各站点
2. 关闭浏览器
3. 运行工具提取 Cookie
4. 复制生成的 JSON 到 GitHub Secrets

## GitHub Actions 配置

在仓库 Settings → Secrets 中添加：

| Secret 名称 | 说明 |
|-------------|------|
| `LINUXDO_USERNAME` | LinuxDO 用户名 |
| `LINUXDO_PASSWORD` | LinuxDO 密码 |
| `ANYROUTER_ACCOUNTS` | AnyRouter 账号配置（JSON） |

## 环境变量说明

### LinuxDO 统一账号

| 变量 | 必填 | 说明 |
|------|------|------|
| `LINUXDO_USERNAME` | 是 | LinuxDO 用户名 |
| `LINUXDO_PASSWORD` | 是 | LinuxDO 密码 |
| `LINUXDO_BROWSE` | 否 | 是否浏览帖子（默认 true） |
| `LINUXDO_BROWSE_COUNT` | 否 | 浏览帖子数量（默认 10） |

### AnyRouter 账号

```json
[
  {
    "cookies": {"session": "xxx"},
    "api_user": "123",
    "provider": "anyrouter"
  }
]
```

## 通知配置

支持多种通知渠道：

| 渠道 | 环境变量 |
|------|----------|
| Email | `EMAIL_USER`, `EMAIL_PASS`, `EMAIL_TO` |
| PushPlus | `PUSHPLUS_TOKEN` |
| Server酱 | `SC3_PUSH_KEY` |

## 技术栈

- **浏览器自动化**: nodriver / Patchright（反检测）
- **HTTP 请求**: httpx
- **日志**: loguru
- **运行环境**: GitHub Actions

## License

MIT
