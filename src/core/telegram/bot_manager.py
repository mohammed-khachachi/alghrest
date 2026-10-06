"""
ALGHREST — Telegram Bot Manager
Central controller for all 32 agents via Telegram.

Features:
- Self-registration: saves your chat_id on first /start
- Real-time alerts: risk events, agent failures, kill switch
- Full command interface to inspect & control all agents
- Long-poll loop (no webhook required)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import datetime
from typing import Any, cast

import httpx
import orjson
import structlog
from redis.asyncio import Redis

from core.config import settings

logger = structlog.get_logger(__name__)

# ── REDIS KEY HELPERS ─────────────────────────────────────────────────────────

_KEY_REGISTERED_CHATS = "alghrest:telegram:registered_chats"  # Redis Set
_KEY_LAST_UPDATE_ID = "alghrest:telegram:last_update_id"  # Redis String


# ── TELEGRAM API HELPERS ──────────────────────────────────────────────────────


def _api(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _fmt_status(status: str) -> str:
    icons = {
        "RUNNING": "🟢",
        "DEGRADED": "🟡",
        "ERROR": "🔴",
        "STOPPED": "⚫",
        "SHUTDOWN": "⚫",
        "STARTING": "🔵",
        "PAUSED": "⏸",
    }
    return f"{icons.get(status.upper(), '❓')} {status}"


def _fmt_pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


# ── MAIN CLASS ────────────────────────────────────────────────────────────────


class TelegramBotManager:
    """
    Long-polling Telegram bot that acts as manager for all 32 ALGHREST agents.
    Integrated with Redis state via state_manager; started as a background task
    in api/main.py.
    """

    def __init__(self) -> None:
        self._token: str = settings.telegram_bot_token
        self._client: httpx.AsyncClient | None = None
        self._redis: Redis | None = None  # injected after state_manager.initialize()
        self._running = False
        self._log = logger.bind(component="telegram_bot")
        # track agent statuses to detect changes
        self._prev_agent_statuses: dict[int, str] = {}

    # ── LIFECYCLE ─────────────────────────────────────────────────────────────

    def attach_redis(self, redis: Redis) -> None:
        self._redis = redis

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            raise RuntimeError("Redis must be attached before starting the bot")
        return self._redis

    async def start(self) -> None:
        if not self._token:
            self._log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
            return
        self._client = httpx.AsyncClient(timeout=30)
        self._running = True
        self._log.info("Telegram bot started", username="Khachachi_bot")

        # send startup notification to all registered chats
        await self._broadcast(
            "🚀 *ALGHREST Online*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Bot manager connected.\n"
            "Type /help to see all commands."
        )

        await asyncio.gather(
            self._poll_loop(),
            self._alert_loop(),
            self._watchdog_loop(),
        )

    async def stop(self) -> None:
        self._running = False
        if self._client:
            await self._client.aclose()

    # ── POLLING LOOP ──────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        if self._client is None:
            raise RuntimeError("HTTP client must be initialized before polling")
        offset = await self._load_offset()
        while self._running:
            try:
                resp = await self._client.get(
                    _api(self._token, "getUpdates"),
                    params={
                        "timeout": 20,
                        "offset": offset,
                        "limit": 10,
                        "allowed_updates": '["message"]',
                    },
                )
                data = resp.json()
                if data.get("ok") and data["result"]:
                    for update in data["result"]:
                        offset = update["update_id"] + 1
                        await self._handle_update(update)
                    await self._save_offset(offset)
            except Exception as e:
                self._log.warning("poll error", error=str(e))
                await asyncio.sleep(5)

    # ── ALERT LOOP (Redis pub/sub) ─────────────────────────────────────────────

    async def _alert_loop(self) -> None:
        """Forward Redis risk alerts to Telegram in real-time."""
        while self._running:
            try:
                pubsub = self.redis.pubsub()
                await pubsub.subscribe("alghrest:risk:alerts")
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                    payload = orjson.loads(msg["data"])
                    severity = payload.get("severity", "INFO")
                    alert_msg = payload.get("message", "Unknown alert")
                    limit_name = payload.get("limit_name", "")
                    icon = "🚨" if severity == "CRITICAL" else "⚠️"
                    text = (
                        f"{icon} *{severity} ALERT*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📋 {limit_name}\n"
                        f"💬 {alert_msg}\n"
                        f"🕐 {datetime.utcnow().strftime('%H:%M:%S')} UTC"
                    )
                    await self._broadcast(text)
            except Exception as e:
                self._log.warning("alert loop error", error=str(e))
                await asyncio.sleep(10)

    # ── WATCHDOG LOOP (agent health monitoring) ────────────────────────────────

    async def _watchdog_loop(self) -> None:
        """Watch for agent status changes and notify on ERROR/DEGRADED."""
        while self._running:
            try:
                await asyncio.sleep(15)
                from core.orchestrator.state_manager import state_manager

                healths = await state_manager.get_all_agent_healths()
                for h in healths:
                    prev = self._prev_agent_statuses.get(h.agent_id)
                    curr = h.status.value if hasattr(h.status, "value") else str(h.status)
                    if prev and prev != curr:
                        if curr in ("ERROR", "DEGRADED", "STOPPED"):
                            icon = "🔴" if curr == "ERROR" else "🟡"
                            text = (
                                f"{icon} *Agent Status Change*\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"🤖 Agent #{h.agent_id} — {h.agent_name}\n"
                                f"📊 {prev} → *{curr}*\n"
                                f"⚠️ {h.last_error or 'No error message'}\n"
                                f"🕐 {datetime.utcnow().strftime('%H:%M:%S')} UTC"
                            )
                            await self._broadcast(text)
                        elif prev in ("ERROR", "DEGRADED") and curr == "RUNNING":
                            text = (
                                f"✅ *Agent Recovered*\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"🤖 Agent #{h.agent_id} — {h.agent_name}\n"
                                f"📊 {prev} → *{curr}*"
                            )
                            await self._broadcast(text)
                    self._prev_agent_statuses[h.agent_id] = curr
            except Exception as e:
                self._log.warning("watchdog error", error=str(e))

    # ── UPDATE HANDLER ────────────────────────────────────────────────────────

    async def _handle_update(self, update: dict[str, Any]) -> None:
        msg = update.get("message", {})
        if not msg:
            return
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "").strip()
        if not text:
            return

        parts = text.split()
        cmd = parts[0].lower().lstrip("/").split("@")[0]
        args = parts[1:]

        admin_id = settings.telegram_admin_id.strip()
        sender = msg.get("from", {}).get("id")
        # All portfolio/agent data and subscription commands are private too.
        # A stored chat registration, forwarded message or group is not identity.
        if (
            not admin_id
            or type(sender) is not int
            or sender <= 0
            or str(sender) != admin_id
            or chat_id != admin_id
            or msg["chat"].get("type") != "private"
        ):
            await self._send(chat_id, "Not authorized to use this bot.")
            return

        # auto-register the chat after privileged-command authorization
        await self._register_chat(chat_id)

        handlers = {
            "start": self._cmd_start,
            "help": self._cmd_help,
            "status": self._cmd_status,
            "agents": self._cmd_agents,
            "agent": self._cmd_agent,
            "pnl": self._cmd_pnl,
            "risk": self._cmd_risk,
            "alerts": self._cmd_alerts,
            "ks": self._cmd_killswitch,
            "killswitch": self._cmd_killswitch,
            "pause": self._cmd_pause,
            "restart": self._cmd_restart,
            "tier": self._cmd_tier,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(chat_id, args)
        else:
            await self._send(chat_id, "❓ Unknown command. Type /help for the full list.")

    # ── COMMANDS ──────────────────────────────────────────────────────────────

    async def _cmd_start(self, chat_id: str, args: list[str]) -> None:
        await self._send(
            chat_id,
            "👋 *Welcome to ALGHREST Bot Manager*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "You are now registered for real-time alerts.\n\n"
            "I manage *32 autonomous trading agents* across 7 tiers.\n\n"
            "Type /help to see all commands.",
        )

    async def _cmd_help(self, chat_id: str, args: list[str]) -> None:
        await self._send(
            chat_id,
            "📖 *ALGHREST Command Reference*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*📊 Monitoring*\n"
            "/status — System overview\n"
            "/pnl — Portfolio PnL\n"
            "/risk — Risk metrics\n"
            "/alerts — Last 5 risk alerts\n\n"
            "*🤖 Agents*\n"
            "/agents — All 32 agents status\n"
            "/agent <id> — Single agent detail\n"
            "/tier <1-7> — Agents by tier\n\n"
            "*⚙️ Control*\n"
            "/pause <id> — Pause an agent\n"
            "/restart <id> — Restart an agent\n"
            "/ks on — Activate kill switch 🚨\n"
            "/ks off — Deactivate kill switch\n\n"
            "*Auto-alerts sent for:*\n"
            "• Agent ERROR / DEGRADED\n"
            "• CRITICAL risk limit breach\n"
            "• Kill switch activation",
        )

    async def _cmd_status(self, chat_id: str, args: list[str]) -> None:
        from core.orchestrator.state_manager import state_manager

        portfolio = await state_manager.get_portfolio()
        risk = await state_manager.get_risk_metrics()
        healths = await state_manager.get_all_agent_healths()
        ks = await state_manager.is_kill_switch_active()

        running = sum(
            1 for h in healths if str(getattr(h.status, "value", h.status)).upper() == "RUNNING"
        )
        errors = sum(
            1 for h in healths if str(getattr(h.status, "value", h.status)).upper() == "ERROR"
        )
        degraded = sum(
            1 for h in healths if str(getattr(h.status, "value", h.status)).upper() == "DEGRADED"
        )

        pnl_line = ""
        if portfolio:
            pnl = float(portfolio.daily_pnl)
            pnl_pct = (
                (pnl / float(portfolio.total_capital) * 100)
                if float(portfolio.total_capital)
                else 0
            )
            icon = "📈" if pnl >= 0 else "📉"
            pnl_line = f"{icon} Daily PnL: *${pnl:+,.2f}* ({_fmt_pct(pnl_pct)})\n"
            pnl_line += f"💰 Portfolio: *${float(portfolio.total_capital):,.0f}*\n"
            pnl_line += f"📐 Leverage: *{float(portfolio.leverage):.2f} x *\n"

        risk_line = ""
        if risk:
            dd = round(float(getattr(risk, "daily_drawdown_pct", 0)) * 100, 2)
            risk_line = f"📉 Drawdown: *{dd:.2f}%*\n"

        ks_line = "🚨 *KILL SWITCH: ACTIVE*\n" if ks else "✅ Kill switch: OFF\n"

        await self._send(
            chat_id,
            f"🖥 *ALGHREST System Status*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{ks_line}"
            f"\n*Agents ({len(healths)} total)*\n"
            f"🟢 Running: {running}  🔴 Error: {errors}  🟡 Degraded: {degraded}\n\n"
            f"*Portfolio*\n"
            f"{pnl_line}"
            f"{risk_line}"
            f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        )

    async def _cmd_agents(self, chat_id: str, args: list[str]) -> None:
        from core.orchestrator.state_manager import state_manager

        healths = await state_manager.get_all_agent_healths()
        healths_sorted = sorted(healths, key=lambda h: (h.tier, h.agent_id))

        lines = ["🤖 *All 32 Agents*\n━━━━━━━━━━━━━━━━━━━━"]
        current_tier = None
        for h in healths_sorted:
            if h.tier != current_tier:
                current_tier = h.tier
                tier_names = {
                    1: "Command",
                    2: "Intelligence",
                    3: "Analytics",
                    4: "Strategy",
                    5: "Execution",
                    6: "DeFi",
                    7: "Oversight",
                }
                lines.append(f"\n*Tier {h.tier} — {tier_names.get(h.tier,'')}*")
            status = str(getattr(h.status, "value", h.status)).upper()
            icon = {
                "RUNNING": "🟢",
                "DEGRADED": "🟡",
                "ERROR": "🔴",
                "SHUTDOWN": "⚫",
                "STOPPED": "⚫",
            }.get(status, "❓")
            lines.append(f"{icon} #{h.agent_id} {h.agent_name}")

        await self._send(chat_id, "\n".join(lines))

    async def _cmd_agent(self, chat_id: str, args: list[str]) -> None:
        if not args or not args[0].isdigit():
            await self._send(chat_id, "Usage: /agent <id>  (e.g. /agent 1)")
            return
        from core.orchestrator.state_manager import state_manager

        agent_id = int(args[0])
        h = await state_manager.get_agent_health(agent_id)
        if not h:
            await self._send(chat_id, f"❌ Agent #{agent_id} not found.")
            return
        status = str(getattr(h.status, "value", h.status)).upper()
        uptime_h = int(getattr(h, "uptime_seconds", 0) // 3600)
        uptime_m = int((getattr(h, "uptime_seconds", 0) % 3600) // 60)
        await self._send(
            chat_id,
            f"🤖 *Agent #{h.agent_id} — {h.agent_name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Status: {_fmt_status(status)}\n"
            f"Tier: {h.tier}\n"
            f"Uptime: {uptime_h}h {uptime_m}m\n"
            f"Messages: {getattr(h, 'messages_processed', 0):,}\n"
            f"Errors: {getattr(h, 'error_count', 0)}\n"
            f"CPU: {(getattr(h, 'cpu_pct', None) or 0):.1f}%\n"
            f"Memory: {(getattr(h, 'memory_mb', None) or 0):.0f} MB\n"
            f"Latency p50: {(getattr(h, 'latency_p50_ms', None) or 0):.1f} ms\n"
            f"Latency p99: {(h.latency_p99_ms or 0):.1f} ms\n"
            + (f"⚠️ Last error: `{h.last_error}`\n" if h.last_error else "")
            + f"🕐 Heartbeat: {h.last_heartbeat}",
        )

    async def _cmd_pnl(self, chat_id: str, args: list[str]) -> None:
        from core.orchestrator.state_manager import state_manager

        portfolio = await state_manager.get_portfolio()
        if not portfolio:
            await self._send(chat_id, "❌ Portfolio data not available.")
            return
        daily = float(portfolio.daily_pnl)
        unrealized = float(portfolio.unrealized_pnl)
        capital = float(portfolio.total_capital)
        daily_pct = (daily / capital * 100) if capital else 0
        positions = portfolio.positions

        pos_lines = ""
        for p in positions[:8]:
            pnl = float(p.unrealized_pnl)
            icon = "📈" if pnl >= 0 else "📉"
            pos_lines += f"{icon} {p.symbol} {p.side}: ${pnl:+,.2f}\n"

        await self._send(
            chat_id,
            f"💰 *Portfolio PnL*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total Capital: *${capital:,.0f}*\n"
            f"📈 Daily PnL: *${daily:+,.2f}* ({_fmt_pct(daily_pct)})\n"
            f"💹 Unrealized: *${unrealized:+,.2f}*\n"
            f"📐 Leverage: *{float(portfolio.leverage):.2f} x *\n"
            f"🔢 Open Positions: *{len(positions)}*\n"
            f"\n*Positions*\n{pos_lines}"
            f"🕐 {datetime.utcnow().strftime('%H:%M:%S')} UTC",
        )

    async def _cmd_risk(self, chat_id: str, args: list[str]) -> None:
        from core.orchestrator.state_manager import state_manager

        risk = await state_manager.get_risk_metrics()
        ks = await state_manager.is_kill_switch_active()
        if not risk:
            await self._send(chat_id, "❌ Risk data not available.")
            return
        dd = round(float(getattr(risk, "daily_drawdown_pct", 0)) * 100, 2)
        lev = round(float(getattr(risk, "current_leverage", 0)), 2)
        var = float(getattr(risk, "var_95_1d", 0) or 0)
        sharpe = getattr(risk, "sharpe_90d", None)
        ks_line = "🚨 *KILL SWITCH ACTIVE*\n" if ks else ""
        await self._send(
            chat_id,
            f"⚠️ *Risk Metrics*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{ks_line}"
            f"📉 Daily Drawdown: *{dd:.2f}%* (limit 25%)\n"
            f"📐 Leverage: *{lev:.2f} x *\n"
            f"🎲 VaR 95% (1d): *${var:,.0f}*\n"
            f"📊 Sharpe (90d): *{sharpe or 'N/A'}*\n"
            f"🕐 {datetime.utcnow().strftime('%H:%M:%S')} UTC",
        )

    async def _cmd_alerts(self, chat_id: str, args: list[str]) -> None:
        alerts = await cast(
            Awaitable[list[bytes]], self.redis.lrange("alghrest:risk:alert_history", 0, 4)
        )
        if not alerts:
            await self._send(chat_id, "✅ No recent risk alerts.")
            return
        lines = ["🚨 *Last Risk Alerts*\n━━━━━━━━━━━━━━━━━━━━"]
        for raw in alerts:
            a = orjson.loads(raw)
            sev = a.get("severity", "INFO")
            icon = "🔴" if sev == "CRITICAL" else "🟡"
            lines.append(f"{icon} [{sev}] {a.get('message','')}")
        await self._send(chat_id, "\n".join(lines))

    async def _cmd_tier(self, chat_id: str, args: list[str]) -> None:
        if not args or not args[0].isdigit():
            await self._send(chat_id, "Usage: /tier <1-7>  (e.g. /tier 4)")
            return
        tier_num = int(args[0])
        if tier_num < 1 or tier_num > 7:
            await self._send(chat_id, "❌ Tier must be between 1 and 7.")
            return
        from core.orchestrator.state_manager import state_manager

        healths = await state_manager.get_all_agent_healths()
        tier_agents = [h for h in healths if h.tier == tier_num]
        tier_names = {
            1: "Command",
            2: "Intelligence",
            3: "Analytics",
            4: "Strategy",
            5: "Execution",
            6: "DeFi",
            7: "Oversight",
        }
        lines = [f"*Tier {tier_num} — {tier_names.get(tier_num,'')}*\n━━━━━━━━━━━━━━━━━━━━"]
        for h in sorted(tier_agents, key=lambda x: x.agent_id):
            status = str(getattr(h.status, "value", h.status)).upper()
            icon = {"RUNNING": "🟢", "DEGRADED": "🟡", "ERROR": "🔴", "SHUTDOWN": "⚫"}.get(
                status, "❓"
            )
            cpu = getattr(h, "cpu_pct", None) or 0
            mem = getattr(h, "memory_mb", None) or 0
            lines.append(
                f"{icon} #{h.agent_id} *{h.agent_name}*\n   CPU {cpu:.1f}%  RAM {mem:.0f}MB"
            )
        await self._send(chat_id, "\n".join(lines))

    async def _cmd_killswitch(self, chat_id: str, args: list[str]) -> None:
        if not args:
            await self._send(chat_id, "Usage: /ks on  or  /ks off")
            return
        action = args[0].lower()
        if action == "on":
            await self.redis.set("alghrest:kill_switch:active", "1")
            await self.redis.set(
                "alghrest:kill_switch:reason",
                f"Activated via Telegram by admin at {datetime.utcnow().isoformat()}",
            )
            await self._broadcast(
                "🚨 *KILL SWITCH ACTIVATED*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "All trading halted by Telegram command.\n"
                f"🕐 {datetime.utcnow().strftime('%H:%M:%S')} UTC"
            )
        elif action == "off":
            await self.redis.delete("alghrest:kill_switch:active")
            await self.redis.delete("alghrest:kill_switch:reason")
            await self._broadcast(
                "✅ *Kill Switch Deactivated*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Trading resumed.\n"
                f"🕐 {datetime.utcnow().strftime('%H:%M:%S')} UTC"
            )
        else:
            await self._send(chat_id, "Usage: /ks on  or  /ks off")

    async def _cmd_pause(self, chat_id: str, args: list[str]) -> None:
        if not args or not args[0].isdigit():
            await self._send(chat_id, "Usage: /pause <agent_id>  (e.g. /pause 14)")
            return
        agent_id = int(args[0])
        await self.redis.set(
            f"alghrest:agent:command:{agent_id}",
            orjson.dumps({"command": "PAUSE", "issued_at": datetime.utcnow().isoformat()}),
            ex=300,
        )
        await self._send(
            chat_id,
            f"⏸ *Pause command sent to Agent #{agent_id}*\n"
            "The agent will pause on its next heartbeat cycle.",
        )

    async def _cmd_restart(self, chat_id: str, args: list[str]) -> None:
        if not args or not args[0].isdigit():
            await self._send(chat_id, "Usage: /restart <agent_id>  (e.g. /restart 14)")
            return
        agent_id = int(args[0])
        await self.redis.set(
            f"alghrest:agent:command:{agent_id}",
            orjson.dumps({"command": "RESTART", "issued_at": datetime.utcnow().isoformat()}),
            ex=300,
        )
        await self._send(
            chat_id,
            f"🔄 *Restart command sent to Agent #{agent_id}*\n"
            "The agent will restart on its next heartbeat cycle.",
        )

    # ── CHAT REGISTRATION ─────────────────────────────────────────────────────

    async def _register_chat(self, chat_id: str) -> None:
        await cast(Awaitable[int], self.redis.sadd(_KEY_REGISTERED_CHATS, chat_id))

    async def _get_registered_chats(self) -> list[str]:
        chats = await cast(Awaitable[set[bytes | str]], self.redis.smembers(_KEY_REGISTERED_CHATS))
        return [c.decode() if isinstance(c, bytes) else c for c in chats]

    async def _load_offset(self) -> int:
        raw = await self.redis.get(_KEY_LAST_UPDATE_ID)
        return int(raw) if raw else 0

    async def _save_offset(self, offset: int) -> None:
        await self.redis.set(_KEY_LAST_UPDATE_ID, offset)

    # ── SEND HELPERS ──────────────────────────────────────────────────────────

    async def _send(self, chat_id: str, text: str) -> None:
        if not self._client:
            return
        try:
            await self._client.post(
                _api(self._token, "sendMessage"),
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
        except Exception as e:
            self._log.warning("send error", chat_id=chat_id, error=str(e))

    async def _broadcast(self, text: str) -> None:
        # Legacy Redis registrations are untrusted, including across restarts.
        # Only operator-configured destinations receive private broadcasts.
        all_chats = {settings.telegram_chat_id.strip(), settings.telegram_admin_id.strip()} - {""}
        for chat_id in all_chats:
            await self._send(str(chat_id), text)


# ── SINGLETON ─────────────────────────────────────────────────────────────────

telegram_bot = TelegramBotManager()
