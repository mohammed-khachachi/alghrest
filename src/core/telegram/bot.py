import os

import httpx


class TelegramBroadcaster:
    """
    Handles broadcasting messages to a specific Telegram Channel for Copy Trading.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in environment variables.
    """

    def __init__(self) -> None:
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.http_client = httpx.AsyncClient()

    async def broadcast_signal(
        self,
        symbol: str,
        direction: str,
        price: float,
        strategy: str,
        confidence: float,
        tp: float | None = None,
        sl: float | None = None,
    ) -> None:
        """
        Formats and sends a copy-trading signal to the channel.
        """
        if not self.bot_token or not self.channel_id:
            return

        direction_emoji = "🟢 LONG" if direction.upper() == "LONG" else "🔴 SHORT"

        message = (
            f"🚨 **ALGHREST TRADE SIGNAL** 🚨\n\n"
            f"🪙 **Pair:** #{symbol.replace('/', '')}\n"
            f"📈 **Action:** {direction_emoji}\n"
            f"💵 **Entry Price:** {price:.4f}\n\n"
            f"🤖 **Strategy:** {strategy}\n"
            f"🧠 **AI Confidence:** {confidence*100:.1f}%\n"
        )

        if tp:
            message += f"🎯 **Take Profit:** {tp:.4f}\n"
        if sl:
            message += f"🛡️ **Stop Loss:** {sl:.4f}\n"

        message += "\n*Powered by ALGHREST Multi-Agent Engine*"

        await self._send_text(message)

    async def _send_text(self, text: str) -> None:
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.channel_id, "text": text, "parse_mode": "Markdown"}
        try:
            response = await self.http_client.post(url, json=payload, timeout=10.0)
            if response.status_code != 200:
                print(f"Telegram API Error: {response.text}")
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")

    async def close(self) -> None:
        await self.http_client.aclose()
