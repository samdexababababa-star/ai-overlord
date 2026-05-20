"""Advanced reasoning engine.

Implements research-backed deliberative reasoning strategies:

- **Tree of Thoughts (ToT)** — Yao et al. 2023, "Tree of Thoughts: Deliberate
  Problem Solving with Large Language Models". Explores multiple reasoning
  branches via BFS/DFS with heuristic-guided pruning.

- **Reflexion** — Shinn et al. 2023, "Reflexion: Language Agents with Verbal
  Reinforcement Learning". Iterative self-critique loop where the agent reflects
  on failures and retries with accumulated verbal feedback.

- **Multi-Agent Debate** — Du et al. 2023, "Improving Factuality and Reasoning
  in Language Models through Multiagent Debate". Multiple independent agents
  argue opposing positions and converge toward consensus.

- **Constitutional AI (Self-Critique)** — Bai et al. 2022, "Constitutional AI:
  Harmlessness from AI Feedback". The model critiques its own output against
  a set of principles and revises until compliant.

- **Deliberate orchestrator** — Combines all strategies with automatic strategy
  selection based on task complexity analysis.
"""

from .constitutional import ConstitutionalCritic
from .debate import MultiAgentDebate
from .deliberate import DeliberateReasoner
from .reflexion import ReflexionLoop
from .tree_of_thoughts import TreeOfThoughts

__all__ = [
    "TreeOfThoughts",
    "ReflexionLoop",
    "MultiAgentDebate",
    "ConstitutionalCritic",
    "DeliberateReasoner",
]
