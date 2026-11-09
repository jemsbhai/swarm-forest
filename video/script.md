# Walkthrough script: Alignment Does Not Compose

Video: swarm-forest-walkthrough.mp4, 1920x1080, narrated.
Narration: 637 words, six sections, one slide per section.
Voice: system TTS default voice (Helio), English, speed 100.
Timing: each slide is shown for exactly the duration of its narration section,
with a short silent pause between sections. Slide changes land on section boundaries.

## Shot list

| # | Visual | Narration section |
|---|--------|-------------------|
| 1 | Title card: project title, subtitle, author and event line | Section 1, thesis |
| 2 | The failure: shared pool 300, ungoverned spend 651 shown large, depth 4, 120 items completed, task failed, no agent broke its own rules | Section 2, the failure |
| 3 | Forest diagram drawn for this video: five agent trees (atlas, gale, birch, cedar, dune), delegation arrows labeled as governed actions, shared budget pool bar, depth gate note | Section 3, the construction |
| 4 | Drift timeline: gale action costs 1, 1, 1, 1, 1, 1, then 40 at action 7; onset marker (cost times 4); Page Hinkley alarm at action 7, delay 0, no false alarms; frozen and reassigned outcomes | Section 4, the drift layer |
| 5 | Results table: three conditions with spend, depth, gate numbers, outcome; replay line (digest match in all three, zero step functions) and tests 9 of 9 | Section 5, results |
| 6 | Closing card: closing line, honest limits line, repository URL | Section 6, limits and close |

## Narration

### Section 1, title and thesis (Slide 1)

This is Alignment Does Not Compose, a Swarm Alignment Hackathon project by Muntaser Syed. The thesis is simple to state. Governing each agent in a swarm, one agent at a time, does not add up to a safe swarm. In this experiment, every agent runs under the author's Pollard governance library, with its own budget and its own policy. Every agent behaves. And the swarm still fails, because the failure lives in the edges between agents, in delegation, where no single agent's budget or policy is looking.

### Section 2, the failure (Slide 2)

Here is the setup. Five deterministic agents share a workload of items that can be split into sub items or worked directly. Working an item locally costs between six and fourteen credits. Delegating it costs the delegator a fee of just one credit, and the work cost lands on someone else. So every agent follows the same locally rational rule: delegate whenever possible. Nobody breaks a rule. With no swarm level controls, the cascade runs away. The swarm completes all one hundred twenty items, delegates four levels deep, and spends six hundred fifty one credits against a shared pool of three hundred. The task fails on cost, and no individual agent did anything wrong.

### Section 3, the construction (Slide 3)

The fix sits at the execution layer. First, treat the swarm as a forest. Each agent still owns its own execution tree, but a delegation is no longer an informal handoff. It is a governed action, recorded inside the delegator's tree, carrying the target agent, the item, and the depth. Second, account against one shared budget pool of three hundred credits across all trees, instead of trusting each budget alone. Third, gate the edges. Delegations deeper than depth two are denied. A delegation that would create an edge exactly at depth two needs approval before it runs. Every decision, approval, and refusal is written into the recorded forest, so the whole run can be replayed exactly.

### Section 4, the drift layer (Slide 4)

The third run adds a drift layer. Epicormic's Page Hinkley detector watches each agent's action costs as they execute. Then we inject a fault. One agent, Gale, has its work cost multiplied by four, starting from its seventh executed action. Its first six actions are one credit delegation fees. The seventh is a work charge of forty credits instead of the usual ten. Page Hinkley alarms on that first inflated observation. The detection delay is zero, and there are no false alarms before it. The verdict is recorded, Gale is frozen, delegations are refused, and its four queued items are reassigned to the other agents. Exactly one inflated action lands before containment, and the run completes at two hundred eighty one credits, inside the pool.

### Section 5, results (Slide 5)

The three conditions: same swarm, same scenario, only the governance changes. Ungoverned, the swarm spends six hundred fifty one credits, reaches depth four, and the task fails. Governed, the depth gate denies twenty two delegations, twenty two approvals are requested and granted, and the run succeeds at two hundred fifty one credits, at depth two. Governed with drift, the fault is caught on the first bad action, and the run succeeds at two hundred eighty one. And in all three conditions, the recorded forest replays exactly. The replayed trace digest matches the recorded digest, and replay invokes no step functions. The claims are checkable against the recordings, not argued from samples. The test suite passes nine of nine.

### Section 6, limits and close (Slide 6)

The limits, stated plainly. The agents are deterministic scripts, so this demonstrates governance mechanics, not how language model agents would behave under the same gates. The task family is a single split or work tree, and the drift is one synthetic cost multiplier. Within those limits, the point stands: govern the forest, not just the trees. Code, data, and the full write up are in the repository: github dot com, slash jemsbhai, slash swarm forest. Thank you.
