# SlimeNodes Auto Renew 🟢

**只续期、不刷币** 的 [SlimeNodes](https://dash.slimenodes.com) 服务器自动续期脚本。

> 改装自 [guanxi660-crypto/SlimeNodes-AutoCoin-btpphlmb](https://github.com/guanxi660-crypto/SlimeNodes-AutoCoin-btpphlmb)（原版为刷币 + 续期）。
> 本版已删除全部刷币逻辑（`/lv/gen` → Linkvertise 广告赚币），仅保留续期链路，避免广告点击风控、省时省力。

## 功能

- 🔄 **自动续期** — 服务器到期前 ≤ `RENEW_HOURS`（默认 24h）且余额 ≥ `RENEW_THRESHOLD`（默认 50 币）时自动调用 `/renew` 续期
- 📱 **TG 通知** — 每次运行后发送状态通知到 Telegram（可选）
- ⚠️ **余额不足提醒** — 余额不够续期时在通知中明确提示，可手动刷币或充值

## 工作原理

纯 HTTP 方式，无需浏览器：

1. 用 Session Cookie 请求 `/dashboard`，读取金币余额（顺带验证会话有效性）
2. 请求 `/lastrenew?id={SERVER_ID}` 获取服务器精确到期时间
3. 剩余时间 ≤ `RENEW_HOURS` 且余额 ≥ `RENEW_THRESHOLD` → 请求 `/renew?id={SERVER_ID}` 续期（约 115 币/次）
4. 发送 TG 通知

> 💡 **余额从哪来？** 本版不刷币，余额来自原版脚本积累或手动操作。若余额不足以续期，通知会提示"余额不足"，此时可手动去面板刷几个广告，或等待下一次运行重试。

## 定时任务

GitHub Actions 每天自动运行两次：

- ⏰ **00:30 UTC**（北京时间 08:30）
- ⏰ **12:30 UTC**（北京时间 20:30）

也可手动触发 `workflow_dispatch`（Actions 页面 → Run workflow）。

## 环境变量

### Secrets（Settings → Secrets and variables → Actions → Secrets）

| 变量 | 说明 | 必填 |
|------|------|------|
| `SLIME_SESSION` | SlimeNodes session cookie (`connect.sid`) | ✅ |
| `TG_BOT_TOKEN` | Telegram Bot Token | ❌ |
| `TG_CHAT_ID` | Telegram Chat ID | ❌ |

### Variables（Settings → Secrets and variables → Actions → Variables）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SERVER_ID` | 服务器 ID | `10102` |
| `RENEW_HOURS` | 续期阈值小时数（剩余时间 ≤ 此值才续期） | `24` |
| `RENEW_THRESHOLD` | 续期最低余额（币） | `50` |

不配置 Variables 时自动使用默认值，全部可选。

## GitHub Secrets 设置

```json
{
  "SLIME_SESSION": "s%3A...",
  "TG_BOT_TOKEN": "7935239797:AAH...",
  "TG_CHAT_ID": "644320820"
}
```

## TG 通知格式

```
🇫🇷 Aclclouds 续期通知

✅ 续期成功
⏱️ 新过期时间: 6j 23h
👤 登录账户: b****b
⏱️ 运行时间: 2026-09-06 05:00:28
```

过期时间用 `Xj Xh`（天+小时）原样展示，不做小数天换算；账号首尾各留 1 字符脱敏。

状态行有五种：
- `✅ 续期成功`（同时显示续期后的新过期时间）
- `⏭️ 暂不需要续期`（剩余时间 > RENEW_HOURS）
- `⚠️ 余额不足 (需 50 币, 当前 30 币)`
- `❌ 续期失败`
- `❓ 无法获取到期时间`

会话失效时通知为 `❌ Session 已过期`，此时需要重新导出 cookie 更新 `SLIME_SESSION`。

## 退出码（Actions 状态）

| 码 | 含义 |
|----|------|
| 0 | 正常（含"暂不需要续期"等正常跳过） |
| 1 | `SLIME_SESSION` 未设置 |
| 2 | Session 已过期，需更新 Secret |
| 3 | 无法获取余额（网络/面板问题） |

## 参考

- [jpus/SlimeNodes-AutoCoin](https://github.com/jpus/SlimeNodes-AutoCoin) — 原始参考脚本
- [guanxi660-crypto/SlimeNodes-AutoCoin-btpphlmb](https://github.com/guanxi660-crypto/SlimeNodes-AutoCoin-btpphlmb) — 本仓库改装前的原版
