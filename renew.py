#!/usr/bin/env python3
"""SlimeNodes Auto-Renew — 只续期，不刷币

改装自 guanxi660-crypto/SlimeNodes-AutoCoin-btpphlmb（原版为 刷币+续期）。
本版删除全部刷币逻辑（/lv/gen → Linkvertise 广告），仅保留：
  1. 查余额   (/dashboard)
  2. 查剩余时间 (/lastrenew?id=)
  3. 到期前 ≤RENEW_HOURS 且余额 ≥RENEW_THRESHOLD 时调 /renew 续期
  4. TG 通知（简洁格式：状态 + 过期时间 + 账号 + 运行时间）

纯 HTTP 方式，无需浏览器。依赖系统 curl。
"""
import os, sys, re, json, time, subprocess
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("SLIME_BASE") or "https://dash.slimenodes.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
TGT = os.environ.get("TG_BOT_TOKEN") or ""
TGC = os.environ.get("TG_CHAT_ID") or ""
# 可选代理（vless/vmess 等需先转成 socks5/http 本地端口再填）
PX = os.environ.get("SOCKS_PROXY") or os.environ.get("HTTP_PROXY") or ""
SESSION = os.environ.get("SLIME_SESSION") or ""
ACCOUNT_LABEL = os.environ.get("ACCOUNT_LABEL") or "btpphlmb"
SERVER_ID = os.environ.get("SERVER_ID") or "10102"
# 续期最低余额（币）
RENEW_THRESHOLD = int(os.environ.get("RENEW_THRESHOLD") or "50")
# 剩余时间低于该小时数才续期
RENEW_HOURS = int(os.environ.get("RENEW_HOURS") or "24")

# Exit codes
EXIT_OK = 0
EXIT_NO_SESSION = 1
EXIT_SESSION_EXPIRED = 2
EXIT_BALANCE_FAIL = 3


def px():
    """返回 curl 代理参数列表（未配置代理时为空）"""
    return ["-x", PX] if PX else []


def log(m):
    """打印带 UTC 时间戳的日志行"""
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {m}", flush=True)


def ok(m):
    """成功日志（✅ 前缀）"""
    log(f"✅ {m}")


def er(m):
    """失败日志（❌ 前缀）"""
    log(f"❌ {m}")


def run_curl(args, timeout=25):
    """执行 curl 并返回 stdout；异常时返回 ERR: 前缀字符串"""
    cmd = ["curl", "-s", "--connect-timeout", "20", "--max-time", str(timeout)] + px() + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        return r.stdout
    except Exception as e:
        return f"ERR:{e}"


def send_tg(msg):
    """发送 Telegram 通知（未配置 token 则静默跳过）"""
    if not TGT or not TGC:
        return
    run_curl(["-s", "-X", "POST", f"https://api.telegram.org/bot{TGT}/sendMessage",
              "-H", "Content-Type: application/json",
              "-d", json.dumps({"chat_id": TGC, "text": msg})],
             timeout=15)


def ck(s):
    """拼 connect.sid cookie 头"""
    return f"connect.sid={s}"


def mask_account(label):
    """账号脱敏：保留首尾各 1 字符，中间 ****（含 @ 时只脱敏 @ 前部分）"""
    local, _, domain = label.partition("@")
    if len(local) <= 2:
        return label
    return local[0] + "****" + local[-1] + ("@" + domain if domain else "")


def fmt_remaining(hours):
    """剩余小时数 → '4j 9h' 格式（j=天 h=小时），不足 1 天只显示小时，不做小数天换算"""
    if hours is None or hours < 0:
        hours = 0
    d, h = int(hours // 24), int(hours % 24)
    return f"{d}j {h}h" if d > 0 else f"{h}h"


def now_local():
    """北京时间字符串 (UTC+8)，格式 2026-09-06 05:00:28"""
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def get_balance(s):
    """获取金币余额。

    返回 (balance:int|None, expired:bool)：
      - balance 为余额数值；获取失败为 None
      - expired 为 True 表示会话已失效（被重定向到 /login）
    """
    body = run_curl(["-L", "-w", "\n%{url_effective}",
                     "-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
                     f"{BASE}/dashboard"])
    lines = body.strip().split("\n")
    final_url = lines[-1] if lines else ""
    if "/login" in final_url:
        return None, True
    m = re.search(r'balance\.textContent\s*=\s*Math\.floor\((\d+)\s*\*\s*100\)', body)
    if m:
        return int(m.group(1)), False
    return None, False


def get_hours_left(s):
    """通过 /lastrenew API 获取服务器剩余小时数；失败返回 None"""
    body = run_curl(["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
                     f"{BASE}/lastrenew?id={SERVER_ID}"])
    try:
        end_ms = json.loads(body).get("lastrenew", 0)
        if not end_ms:
            return None
        return (end_ms - time.time() * 1000) / (1000 * 60 * 60)
    except Exception:
        return None


def renew(s, server_id):
    """续期服务器。成功返回 True。"""
    log(f"Renewing server {server_id}...")
    # -w 捕获重定向后的最终 URL，续期成功会落在 success=RENEWED
    cmd = ["curl", "-s", "-L", "-w", "\n%{url_effective}",
           "--connect-timeout", "20", "--max-time", "20"]
    cmd += ["-H", f"User-Agent: {UA}", "-H", f"Cookie: {ck(s)}",
            f"{BASE}/renew?id={server_id}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        output = result.stdout
        lines = output.strip().split("\n")
        final_url = lines[-1] if lines else ""
        body = "\n".join(lines[:-1]) if len(lines) > 1 else ""
        log(f"Renew URL: {final_url[:80]}")
        if "RENEWED" in final_url:
            ok("Server renewed!")
            return True
        if "/login" in final_url:
            er("Session expired during renew")
            return False
        er(f"Renew failed: {final_url[:80]}")
        return False
    except Exception as e:
        er(f"Renew error: {e}")
        return False


def main():
    if not SESSION:
        er("SLIME_SESSION 未设置！")
        sys.exit(EXIT_NO_SESSION)

    log(f"\n{'='*40}\n账号: {ACCOUNT_LABEL}\n{'='*40}")

    # 1. 查余额（顺带验证会话）
    b, expired = get_balance(SESSION)
    if expired:
        er("Session 已过期，请更新 SLIME_SESSION secret")
        send_tg("\n".join([
            "🇫🇷 SlimeNodes 续期通知",
            "",
            "❌ Session 已过期",
            f"👤 登录账户: {mask_account(ACCOUNT_LABEL)}",
            f"⏱️ 运行时间: {now_local()}",
        ]))
        sys.exit(EXIT_SESSION_EXPIRED)
    if b is None:
        er("无法获取余额（网络/面板问题）")
        sys.exit(EXIT_BALANCE_FAIL)
    ok(f"余额: {b}币")

    # 2. 查剩余时间
    hl = get_hours_left(SESSION)
    if hl is None:
        er("无法获取到期时间")
    else:
        log(f"服务器剩余: {hl:.0f}小时 ({fmt_remaining(hl)})")

    # 3. 续期判断：到期前 ≤RENEW_HOURS 且余额够 → 续期
    renewed = False
    if hl is not None and hl <= RENEW_HOURS:
        log(f"进入续期窗口 (≤{RENEW_HOURS}h)")
        if b >= RENEW_THRESHOLD:
            renewed = renew(SESSION, SERVER_ID)
            if renewed:
                b2, _ = get_balance(SESSION)
                log(f"续期后余额: {b2}")
        else:
            er(f"余额不足续期 (需要 {RENEW_THRESHOLD} 币, 当前 {b} 币)")
    elif hl is not None:
        log(f"离到期还有 {hl:.0f}h，暂不续期 (>{RENEW_HOURS}h)")

    # 续期成功后重新获取新到期时间
    if renewed:
        new_hl = get_hours_left(SESSION)
        if new_hl is not None:
            hl = new_hl

    # 4. TG 通知（简洁格式）
    lines = ["🇫🇷 SlimeNodes 续期通知", ""]
    if renewed:
        lines.append("✅ 续期成功")
    elif hl is None:
        lines.append("❓ 无法获取到期时间")
    elif hl > RENEW_HOURS:
        lines.append("⏭️ 暂不需要续期")
    elif b < RENEW_THRESHOLD:
        lines.append(f"⚠️ 余额不足 (需 {RENEW_THRESHOLD} 币, 当前 {b} 币)")
    else:
        lines.append("❌ 续期失败")
    if hl is not None:
        lines.append(f"⏱️ {'新过期时间' if renewed else '过期时间'}: {fmt_remaining(hl)}")
    lines.append(f"👤 登录账户: {mask_account(ACCOUNT_LABEL)}")
    lines.append(f"⏱️ 运行时间: {now_local()}")
    msg = "\n".join(lines)
    log("\n" + msg)  # 通知内容同步进日志（未配 TG 也能在 Actions 日志看到完整状态）
    send_tg(msg)
    ok("完成")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
