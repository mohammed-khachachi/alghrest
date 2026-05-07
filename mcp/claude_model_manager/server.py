#!/usr/bin/env python3
"""
ALGHREST MCP Server — Claude Model Manager
Manage, test, and configure Claude AI models for all 32 ALGHREST agents.

Usage (stdio transport, registered in .claude/settings.json):
    python mcp/claude_model_manager/server.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import anthropic
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).parent.parent.parent / ".env")

mcp = FastMCP(
    "alghrest-model-manager",
    description="Manage Claude AI models for ALGHREST's 32-agent trading system",
)

CONFIG_PATH = Path(__file__).parent / "agent_models.json"

# Model catalogue: IDs, pricing (USD per 1M tokens), and metadata
MODELS: dict[str, dict] = {
    "claude-opus-4-7": {
        "name": "Claude Opus 4.7",
        "context_window": 200_000,
        "input_mtok_usd": 15.0,
        "output_mtok_usd": 75.0,
        "strengths": ["complex reasoning", "strategic planning", "long-form analysis"],
        "best_for": "CIO — high-stakes, infrequent decisions that justify premium cost",
    },
    "claude-sonnet-4-6": {
        "name": "Claude Sonnet 4.6",
        "context_window": 200_000,
        "input_mtok_usd": 3.0,
        "output_mtok_usd": 15.0,
        "strengths": ["analysis", "coding", "research", "tool use"],
        "best_for": "Intelligence / Quant / Strategy agents — best cost-to-quality ratio",
    },
    "claude-haiku-4-5-20251001": {
        "name": "Claude Haiku 4.5",
        "context_window": 200_000,
        "input_mtok_usd": 0.8,
        "output_mtok_usd": 4.0,
        "strengths": ["speed", "cost efficiency", "high-frequency tasks"],
        "best_for": "Execution / Monitoring agents — low-latency, high call-volume decisions",
    },
}

# Tier metadata for grouping in list output
TIERS: dict[str, list[str]] = {
    "Tier 1 — Executive": ["cio_agent", "risk_governor"],
    "Tier 2 — Intelligence": [
        "market_data_hub", "news_analyst", "sentiment_analyst",
        "macro_economist", "geopolitical_watcher", "onchain_sleuth",
    ],
    "Tier 3 — Quant": ["technical_analyst", "volatility_forecaster", "correlation_engine"],
    "Tier 4 — Strategies": [
        "trend_follower", "mean_reversion", "momentum", "stat_arb",
        "ml_predictor", "options_strategist", "arb_cross_exchange", "breakout_hunter",
    ],
    "Tier 5 — Execution": [
        "order_router", "position_sizer", "slippage_minimizer",
        "hedge_manager", "fee_optimizer", "liquidation_guard",
    ],
    "Tier 6 — DeFi": ["yield_farmer", "dex_arb", "mev_hunter", "bridge_strategist"],
    "Tier 7 — Monitoring": ["portfolio_tracker", "alert_manager", "compliance_agent"],
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"version": "1.0", "updated_at": "", "assignments": {}}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_config(config: dict) -> None:
    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set — check your .env file or environment.")
    return anthropic.Anthropic(api_key=api_key)


def _cost(model_id: str, input_tok: int, output_tok: int) -> float:
    info = MODELS[model_id]
    return (
        input_tok / 1_000_000 * info["input_mtok_usd"]
        + output_tok / 1_000_000 * info["output_mtok_usd"]
    )


# ── tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_models() -> str:
    """List all available Claude models with pricing, context window, and capabilities."""
    lines = ["# Available Claude Models\n"]
    for model_id, info in MODELS.items():
        lines += [
            f"## {info['name']}",
            f"`{model_id}`",
            f"- **Context window:** {info['context_window']:,} tokens",
            f"- **Price:** ${info['input_mtok_usd']}/M input · ${info['output_mtok_usd']}/M output",
            f"- **Strengths:** {', '.join(info['strengths'])}",
            f"- **Best for:** {info['best_for']}",
            "",
        ]
    return "\n".join(lines)


@mcp.tool()
def list_agent_assignments() -> str:
    """List all 32 ALGHREST agents grouped by tier with their current Claude model assignment."""
    config = _load_config()
    assignments = config.get("assignments", {})

    lines = ["# ALGHREST — Agent Model Assignments\n"]
    if config.get("updated_at"):
        lines.append(f"_Last updated: {config['updated_at']}_\n")

    for tier_label, agents in TIERS.items():
        lines.append(f"## {tier_label}")
        for agent in agents:
            mid = assignments.get(agent)
            if mid:
                label = f"{MODELS[mid]['name']} (`{mid}`)" if mid in MODELS else mid
            else:
                label = "_not assigned_"
            lines.append(f"- `{agent}`: {label}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def set_agent_model(agent_name: str, model_id: str) -> str:
    """
    Assign a Claude model to a specific ALGHREST agent.

    Args:
        agent_name: Agent name (e.g. 'cio_agent', 'news_analyst', 'order_router')
        model_id: Claude model ID — one of 'claude-opus-4-7', 'claude-sonnet-4-6',
                  or 'claude-haiku-4-5-20251001'
    """
    if model_id not in MODELS:
        return (
            f"Unknown model '{model_id}'.\n"
            f"Valid options: {', '.join(f'`{m}`' for m in MODELS)}"
        )

    config = _load_config()
    assignments = config.setdefault("assignments", {})
    old = assignments.get(agent_name, "none")
    assignments[agent_name] = model_id
    _save_config(config)

    old_label = MODELS.get(old, {}).get("name", old)
    new_label = MODELS[model_id]["name"]
    return (
        f"Updated `{agent_name}`\n"
        f"  {old_label} → **{new_label}** (`{model_id}`)\n\n"
        f"Saved to `{CONFIG_PATH}`"
    )


@mcp.tool()
def set_tier_model(tier: str, model_id: str) -> str:
    """
    Assign the same Claude model to every agent in a tier at once.

    Args:
        tier: Tier key — '1', '2', '3', '4', '5', '6', or '7'
        model_id: Claude model ID to assign to all agents in that tier
    """
    tier_map = {str(i + 1): label for i, label in enumerate(TIERS)}
    tier_label = tier_map.get(tier)
    if not tier_label:
        return f"Unknown tier '{tier}'. Valid values: 1 – 7."
    if model_id not in MODELS:
        return (
            f"Unknown model '{model_id}'.\n"
            f"Valid options: {', '.join(f'`{m}`' for m in MODELS)}"
        )

    agents = TIERS[tier_label]
    config = _load_config()
    assignments = config.setdefault("assignments", {})
    for agent in agents:
        assignments[agent] = model_id
    _save_config(config)

    model_name = MODELS[model_id]["name"]
    bullet_list = "\n".join(f"  - `{a}`" for a in agents)
    return (
        f"Assigned **{model_name}** to all {len(agents)} agents in {tier_label}:\n"
        f"{bullet_list}\n\n"
        f"Saved to `{CONFIG_PATH}`"
    )


@mcp.tool()
def test_model(model_id: str, prompt: str, max_tokens: int = 512) -> str:
    """
    Send a test prompt to a Claude model and return the response with token usage and cost.

    Args:
        model_id: Claude model to call
        prompt: The message to send
        max_tokens: Maximum response tokens (default 512)
    """
    if model_id not in MODELS:
        return f"Unknown model '{model_id}'. Valid: {', '.join(MODELS)}"

    try:
        client = _get_client()
    except ValueError as e:
        return str(e)

    try:
        resp = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        return "Authentication failed — check your ANTHROPIC_API_KEY."
    except anthropic.APIError as e:
        return f"API error: {e}"

    text = resp.content[0].text
    c = _cost(model_id, resp.usage.input_tokens, resp.usage.output_tokens)
    info = MODELS[model_id]

    return (
        f"## Response from {info['name']}\n\n"
        f"{text}\n\n"
        f"---\n"
        f"_Tokens: {resp.usage.input_tokens:,} in / {resp.usage.output_tokens:,} out · "
        f"Cost: ${c:.6f}_"
    )


@mcp.tool()
def estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    calls_per_day: int = 1,
) -> str:
    """
    Estimate the daily and monthly USD cost for a given call pattern.

    Args:
        model_id: Claude model ID
        input_tokens: Input tokens per API call
        output_tokens: Output tokens per API call
        calls_per_day: Number of calls per day (default 1)
    """
    if model_id not in MODELS:
        return f"Unknown model '{model_id}'. Valid: {', '.join(MODELS)}"

    info = MODELS[model_id]
    per_call = _cost(model_id, input_tokens, output_tokens)
    daily = per_call * calls_per_day
    monthly = daily * 30

    return (
        f"## Cost Estimate — {info['name']}\n\n"
        f"| Parameter | Value |\n"
        f"|-----------|-------|\n"
        f"| Input tokens/call | {input_tokens:,} @ ${info['input_mtok_usd']}/M |\n"
        f"| Output tokens/call | {output_tokens:,} @ ${info['output_mtok_usd']}/M |\n"
        f"| Cost per call | ${per_call:.6f} |\n"
        f"| Calls per day | {calls_per_day:,} |\n"
        f"| **Daily cost** | **${daily:.4f}** |\n"
        f"| **Monthly cost (30 d)** | **${monthly:.2f}** |\n"
    )


@mcp.tool()
def compare_models(prompt: str, max_tokens: int = 256) -> str:
    """
    Run the same prompt on all three Claude models and compare responses side by side.
    Keep max_tokens low to minimise cost during comparison.

    Args:
        prompt: Prompt to send to every model
        max_tokens: Max response tokens per model (default 256)
    """
    try:
        client = _get_client()
    except ValueError as e:
        return str(e)

    sections: list[str] = []
    total_cost = 0.0

    for model_id, info in MODELS.items():
        try:
            resp = client.messages.create(
                model=model_id,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            c = _cost(model_id, resp.usage.input_tokens, resp.usage.output_tokens)
            total_cost += c
            sections.append(
                f"## {info['name']}\n"
                f"_{resp.usage.input_tokens:,} in / {resp.usage.output_tokens:,} out · "
                f"${c:.6f}_\n\n"
                f"{text}"
            )
        except Exception as e:
            sections.append(f"## {info['name']}\n**Error:** {e}")

    return (
        f"# Model Comparison\n\n"
        f"**Prompt:** {prompt[:120]}{'…' if len(prompt) > 120 else ''}\n"
        f"**Total cost:** ${total_cost:.6f}\n\n"
        + "\n\n---\n\n".join(sections)
    )


if __name__ == "__main__":
    mcp.run()
