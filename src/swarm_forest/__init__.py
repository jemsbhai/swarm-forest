"""swarm_forest: governed execution forests for agent swarms.

Each agent runs as a pollard governed execution tree. Delegation between
agents is a registered, policy-gated pollard action, so the swarm is a
forest of trees joined by governed edges. One pollard SharedBudget acts
as the swarm budget pool. An epicormic sequential drift layer watches
per-agent action-cost streams and, on a drift verdict recorded in the
epicormic ledger, epicormic's DriftMeter refuses further delegations
while the swarm layer freezes the drifting agent.
"""

__version__ = "0.1.0"
