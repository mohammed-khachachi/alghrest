#!/usr/bin/env python3
"""
ALGHREST — Kill Switch Demo
===========================

عرض سريع لكيفية عمل نظام Kill Switch في ALGHREST.
هذا العرض يُظهر:

1. حساب المخاطر في الوقت الفعلي
2. تفعيل Kill Switch عند تجاوز الحدود
3. إلغاء الأوامر تلقائياً
4. إيقاف جميع الاستراتيجيات

Usage:
    python scripts/demo_kill_switch.py
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data.models import RiskMetrics, RISK_LIMITS
from core.risk.kill_switch import KillSwitch

console = Console()


class KillSwitchDemo:
    """عرض تفاعلي لنظام Kill Switch."""

    def __init__(self):
        self.kill_switch = KillSwitch()
        self.portfolio_value = Decimal("1000000")  # $1M
        self.initial_value = self.portfolio_value
        self.orders_cancelled = 0
        self.strategies_paused = 0
        self.demo_active = True

    def create_display_table(self, risk_metrics: RiskMetrics, current_step: str) -> Table:
        """إنشاء جدول عرض الحالة الحالية."""

        table = Table(title=f"🚨 ALGHREST Kill Switch Demo - {current_step}",
                     show_header=True, header_style="bold red")

        table.add_column("المؤشر", style="cyan", width=25)
        table.add_column("القيمة الحالية", style="white", width=20)
        table.add_column("الحد المسموح", style="yellow", width=20)
        table.add_column("الحالة", width=15)

        # قيمة المحفظة
        portfolio_change = float(risk_metrics.total_capital - self.initial_value)
        portfolio_pct = portfolio_change / float(self.initial_value) * 100

        table.add_row(
            "قيمة المحفظة",
            f"${risk_metrics.total_capital:,.0f}",
            f"${self.initial_value:,.0f}",
            f"{portfolio_pct:+.2f}%" if portfolio_pct >= 0 else f"[red]{portfolio_pct:.2f}%[/red]"
        )

        # الانخفاض اليومي
        daily_status = "🟢 آمن" if risk_metrics.daily_drawdown_pct < RISK_LIMITS.daily_drawdown_alert else "🔴 خطر"
        table.add_row(
            "الانخفاض اليومي",
            f"{risk_metrics.daily_drawdown_pct:.2%}",
            f"{RISK_LIMITS.daily_drawdown_alert:.1%}",
            daily_status
        )

        # الانخفاض الأسبوعي
        weekly_status = "🟢 آمن" if risk_metrics.weekly_drawdown_pct < RISK_LIMITS.weekly_drawdown_halt else "🔴 خطر"
        table.add_row(
            "الانخفاض الأسبوعي",
            f"{risk_metrics.weekly_drawdown_pct:.2%}",
            f"{RISK_LIMITS.weekly_drawdown_halt:.1%}",
            weekly_status
        )

        # الانخفاض الشهري
        monthly_status = "🟢 آمن" if risk_metrics.monthly_drawdown_pct < RISK_LIMITS.monthly_kill_switch else "🔴 خطر"
        table.add_row(
            "الانخفاض الشهري",
            f"{risk_metrics.monthly_drawdown_pct:.2%}",
            f"{RISK_LIMITS.monthly_kill_switch:.1%}",
            monthly_status
        )

        # حالة Kill Switch
        kill_switch_status = "🔴 مُفعّل" if self.kill_switch.is_active else "🟢 غير مُفعّل"
        table.add_row(
            "Kill Switch",
            kill_switch_status,
            "غير مُفعّل",
            kill_switch_status
        )

        # الأوامر المُلغاة
        table.add_row(
            "الأوامر المُلغاة",
            str(self.orders_cancelled),
            "-",
            "📊"
        )

        # الاستراتيجيات المُوقفة
        table.add_row(
            "الاستراتيجيات المُوقفة",
            str(self.strategies_paused),
            "8",
            "📈"
        )

        return table

    async def simulate_market_crash(self) -> None:
        """محاكاة انهيار السوق مع عرض تفاعلي."""

        console.print(Panel.fit(
            """
[bold blue]🚨 ALGHREST Kill Switch Demo 🚨[/bold blue]

سيقوم هذا العرض بمحاكاة انهيار السوق لإظهار كيفية عمل نظام الحماية.

[yellow]السيناريو:[/yellow] انهيار تدريجي من 0% إلى 15% خلال دقيقتين
[yellow]التوقع:[/yellow] تفعيل Kill Switch عند الوصول إلى 5% انخفاض يومي
            """,
            style="white on blue"
        ))

        console.print("\n[bold green]بدء المحاكاة...[/bold green]")
        await asyncio.sleep(2)

        # محاكاة انهيار تدريجي
        total_steps = 30  # 30 خطوة خلال دقيقتين
        max_drawdown = 0.15  # 15% انخفاض كحد أقصى

        with Live(console=console, refresh_per_second=2) as live:

            for step in range(total_steps):
                if not self.demo_active:
                    break

                # حساب الانخفاض الحالي
                progress = step / total_steps
                current_drawdown = max_drawdown * progress

                # تحديث قيمة المحفظة
                self.portfolio_value = self.initial_value * Decimal(str(1 - current_drawdown))

                # إنشاء مقاييس المخاطر
                risk_metrics = RiskMetrics(
                    timestamp=datetime.utcnow(),
                    total_capital=self.portfolio_value,
                    available_capital=self.portfolio_value * Decimal("0.15"),
                    daily_drawdown_pct=current_drawdown,
                    weekly_drawdown_pct=current_drawdown,
                    monthly_drawdown_pct=current_drawdown,
                )

                # فحص Kill Switch
                kill_event = await self.kill_switch.check(
                    metrics=risk_metrics,
                    on_close_all_positions=self._mock_close_positions,
                    on_pause_strategy=self._mock_pause_strategy
                )

                # تحديد مرحلة العرض
                if kill_event:
                    current_step = "🔴 KILL SWITCH ACTIVATED!"
                    self.demo_active = False
                elif current_drawdown >= RISK_LIMITS.daily_drawdown_pause:
                    current_step = "🟠 إيقاف الاستراتيجيات الخاسرة"
                elif current_drawdown >= RISK_LIMITS.daily_drawdown_alert:
                    current_step = "🟡 تنبيه المدير التنفيذي"
                else:
                    current_step = "🟢 عمليات عادية"

                # تحديث العرض
                table = self.create_display_table(risk_metrics, current_step)

                progress_bar = Progress(
                    TextColumn("[progress.description]انهيار السوق"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                )
                progress_task = progress_bar.add_task("", total=100, completed=progress * 100)

                live.update(Panel(
                    f"{table}\n\n{progress_bar}",
                    title=f"خطوة {step + 1}/{total_steps}"
                ))

                # إيقاف مؤقت
                await asyncio.sleep(0.2)

                # إذا تم تفعيل Kill Switch، انتظر قليلاً ثم اخرج
                if kill_event:
                    await asyncio.sleep(3)
                    break

        # عرض النتيجة النهائية
        await self._show_final_results()

    async def _mock_close_positions(self, reason: str) -> int:
        """محاكاة إغلاق المراكز."""
        self.orders_cancelled = 47  # محاكاة إلغاء 47 أمر
        console.print(f"\n[bold red]🔒 تم إغلاق جميع المراكز: {reason}[/bold red]")
        return self.orders_cancelled

    async def _mock_pause_strategy(self, reason: str) -> None:
        """محاكاة إيقاف الاستراتيجيات."""
        self.strategies_paused += 3  # محاكاة إيقاف 3 استراتيجيات خاسرة
        console.print(f"\n[bold orange3]⏸️ تم إيقاف الاستراتيجيات الخاسرة: {reason}[/bold orange3]")

    async def _show_final_results(self) -> None:
        """عرض النتائج النهائية."""

        final_loss = self.initial_value - self.portfolio_value
        final_loss_pct = float(final_loss / self.initial_value * 100)

        results_panel = Panel.fit(
            f"""
[bold blue]📊 نتائج العرض النهائية[/bold blue]

[green]رأس المال المحمي:[/green] ${self.portfolio_value:,.0f}
[red]الخسارة المتجنبة:[/red] ${final_loss:,.0f} ({final_loss_pct:.2f}%)
[yellow]الأوامر الملغاة:[/yellow] {self.orders_cancelled}
[yellow]الاستراتيجيات المُوقفة:[/yellow] {self.strategies_paused}

[bold green]✅ نظام الحماية يعمل بنجاح![/bold green]

[blue]الخطوات التالية في النظام الحقيقي:[/blue]
• إشعار فوري للفريق عبر Telegram
• إيقاف جميع عمليات التداول
• حفظ البيانات والسجلات
• انتظار التدخل اليدوي لإعادة التشغيل
            """,
            style="white"
        )

        console.print(results_panel)

    async def reset_demo(self) -> None:
        """إعادة تعيين العرض."""
        await self.kill_switch.reset(authorized_by="demo_reset")
        self.portfolio_value = self.initial_value
        self.orders_cancelled = 0
        self.strategies_paused = 0
        self.demo_active = True
        console.print("\n[bold green]✅ تم إعادة تعيين العرض[/bold green]")


async def main():
    """الدالة الرئيسية للعرض."""

    demo = KillSwitchDemo()

    try:
        # عرض Kill Switch
        await demo.simulate_market_crash()

        # خيار إعادة التشغيل
        console.print(f"\n[bold yellow]هل تريد إعادة تشغيل العرض؟ (y/n)[/bold yellow]", end=" ")

        # في بيئة الإنتاج، يمكن استخدام input()
        # response = input()
        # if response.lower() == 'y':
        #     await demo.reset_demo()
        #     await demo.simulate_market_crash()

        console.print("\n[bold green]شكراً لاستخدام ALGHREST Kill Switch Demo! 🚀[/bold green]")

    except KeyboardInterrupt:
        console.print("\n\n[bold red]تم إيقاف العرض بواسطة المستخدم[/bold red]")
        await demo.kill_switch.reset(authorized_by="user_interrupt")

    except Exception as e:
        console.print(f"\n[bold red]خطأ في العرض: {str(e)}[/bold red]")
        await demo.kill_switch.reset(authorized_by="error_cleanup")


if __name__ == "__main__":
    asyncio.run(main())