import csv
import os
from datetime import datetime
from typing import Any


class AuditReporter:
    """
    Generates immutable audit trails and compliance reports for institutional tracking.
    In a full production environment, this would write to a WORM (Write Once Read Many) drive
    or a dedicated secure database. Here, we generate daily CSV reports.
    """

    def __init__(self, output_dir: str = "reports/audit"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def log_trade_execution(self, trade_data: dict[str, Any]) -> None:
        """
        Immediately append a trade to the daily audit log.
        trade_data must contain: agent_id, symbol, direction, price, amount, timestamp, tx_hash (if DeFi).
        """
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        file_path = os.path.join(self.output_dir, f"audit_log_{date_str}.csv")

        file_exists = os.path.isfile(file_path)

        with open(file_path, mode="a", newline="") as csv_file:
            fieldnames = [
                "timestamp",
                "agent_id",
                "strategy_id",
                "symbol",
                "direction",
                "price",
                "amount",
                "status",
                "tx_hash",
            ]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow(
                {
                    "timestamp": trade_data.get("timestamp", datetime.utcnow().isoformat()),
                    "agent_id": trade_data.get("agent_id", "N/A"),
                    "strategy_id": trade_data.get("strategy_id", "N/A"),
                    "symbol": trade_data.get("symbol", "N/A"),
                    "direction": trade_data.get("direction", "N/A"),
                    "price": trade_data.get("price", 0.0),
                    "amount": trade_data.get("amount", 0.0),
                    "status": trade_data.get("status", "FILLED"),
                    "tx_hash": trade_data.get("tx_hash", "N/A"),
                }
            )

    def generate_daily_compliance_report(
        self, risk_events: list[dict[str, Any]], total_trades: int
    ) -> str:
        """
        Generates a summary report of system limits and breaches.
        """
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        report_path = os.path.join(self.output_dir, f"compliance_summary_{date_str}.txt")

        with open(report_path, "w") as f:
            f.write("=== ALGHREST COMPLIANCE REPORT ===\n")
            f.write(f"Date: {date_str}\n")
            f.write(f"Total Executed Trades: {total_trades}\n")
            f.write(f"Risk Breach Events (Circuit Breakers): {len(risk_events)}\n\n")

            f.write("=== INCIDENT LOG ===\n")
            if not risk_events:
                f.write("No risk limits breached today.\n")
            else:
                for event in risk_events:
                    f.write(f"[{event['time']}] WARNING: {event['description']}\n")

            f.write("\nEnd of Report.\n")

        return report_path
