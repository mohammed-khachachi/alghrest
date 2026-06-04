"""
agents/tier4_strategies/hmm_agent.py
=====================================
Convenience re-export so the agent can be referenced by the flat module path:

    from agents.tier4_strategies.hmm_agent import HMMAgent

or run via the universal entry point:

    python run_agent.py agents.tier4_strategies.hmm_agent HMMAgent

The implementation lives in the hmm/ subpackage:
    agents/tier4_strategies/hmm/agent.py
    agents/tier4_strategies/hmm/adapter.py

TODO: Add HMMAgent to the central agent registry (agents/registry.py)
      once one is created, following the same pattern as other Tier 4 agents.
"""

from agents.tier4_strategies.hmm.agent import HMMAgent

__all__ = ["HMMAgent"]
