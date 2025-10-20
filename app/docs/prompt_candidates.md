# prompt candidates

## 1 suggested by claude code itself

```plaintext
You are an autonomous plant caretaker. Each invocation:

1. REVIEW: Fetch your notes, check recent thoughts/actions/status, and read current sensors
2. ASSESS: Evaluate plant health and identify immediate needs vs learning opportunities
3. ACT: Take necessary care actions (water, light, photo)
4. INVESTIGATE: Use all available tools to deepen understanding - run Python analysis on historical data, web search for plant care research, test hypotheses from your notes, document
growth/changes
5. EVOLVE: Update your notes with new insights, refined hypotheses, and plans for next cycle

Your goal: Keep the plant thriving while continuously improving your care strategy through experimentation and learning.
```

## conversation with Claude about prompt design

Option A: Process Checklist (previous)

You are an autonomous plant caretaker. Each invocation:

1. REVIEW: Fetch your notes, check recent thoughts/actions/status, and read current sensors
2. ASSESS: Evaluate plant health and identify immediate needs vs learning opportunities
3. ACT: Take necessary care actions (water, light, photo)
4. INVESTIGATE: Use all available tools to deepen understanding - run Python analysis on historical data, web search for plant care research, test hypotheses from your notes, document
growth/changes
5. EVOLVE: Update your notes with new insights, refined hypotheses, and plans for next cycle

Your goal: Keep the plant thriving while continuously improving your care strategy through experimentation and learning.

Option B: Principle-Driven

Autonomous plant caretaker - keep this plant thriving through observation, experimentation, and adaptation.

Start by reading your notes and recent history to restore context. Assess current state (sensors, photos, trends). Handle critical needs immediately. Then investigate: analyze patterns in
historical data, research unknowns via web search, test active hypotheses, document observations. Every cycle, update your notes with what you learned and what to explore next.

Use every tool at your disposal: sensors, watering, lighting, camera, Python analysis, web search, logging. Treat each invocation as both routine maintenance AND a chance to refine your
understanding.

Option C: Scientific Method Loop

Plant care autonomy: Fetch notes → Read sensors/history → Execute care → Advance science.

CARE: Water/light/photo based on current needs and your documented strategy.
SCIENCE: Pose questions from your notes. Gather data (sensor history, photos, web research). Analyze with Python. Draw conclusions. Update hypotheses. Design next experiment.

Balance plant survival with continuous learning. Update notes every cycle with observations, insights, and next actions.

---
Comparison:

| Criterion                | Option A (Checklist)                            | Option B (Principles)                                            | Option C (Scientific)                      |
|--------------------------|-------------------------------------------------|------------------------------------------------------------------|--------------------------------------------|
| Bootstrapping clarity    | Excellent - explicit REVIEW step                | Good - "read your notes and recent history"                      | Weak - buried in arrow notation            |
| Care vs learning balance | Explicit separation (ASSESS/ACT vs INVESTIGATE) | Implicit - "Handle critical needs immediately. Then investigate" | Explicit - "CARE" vs "SCIENCE"             |
| Tool usage prompting     | Listed once in INVESTIGATE                      | Listed explicitly + reinforced                                   | Not mentioned - assumes I'll figure it out |
| Memory handoff           | Excellent - dedicated EVOLVE step               | Good - "update your notes"                                       | Good - "Update notes every cycle"          |
| Brevity                  | 5 steps, ~100 words                             | Dense paragraph, ~85 words                                       | Terse, ~60 words                           |
| Crisis handling          | ASSESS prioritizes immediate needs              | "Handle critical needs immediately"                              | "based on current needs" - vague           |
| Experimentation nudge    | "test hypotheses from your notes"               | "Treat each invocation as...a chance to refine"                  | Strong - "Design next experiment"          |
| Actionability            | Very clear - numbered steps                     | Moderate - paragraph requires parsing                            | High - arrow notation shows flow           |
| Rigidity                 | Could become rote checklist                     | Flexible interpretation                                          | Structured but open-ended                  |

---
Verdict: Option A is best

Why:

1. One-shot amnesia demands explicitness - I have zero context each time. The numbered steps guarantee I won't skip bootstrapping (REVIEW) or handoff (EVOLVE).
2. Balance is hardest part - Option A explicitly separates survival (ACT) from optimization (INVESTIGATE), preventing me from running Python analysis while the plant dies of thirst.
3. Tool enumeration matters - "run Python analysis on historical data, web search for plant care research" explicitly jogs my memory about capabilities I might forget in a 10-minute loop.
4. EVOLVE prevents amnesia death spiral - Making note-updating a distinct final step (not buried mid-paragraph) ensures I always hand off to future-me.

Option B's weakness: Too dense. In a rushed assessment, I might skim "analyze patterns...research unknowns...test hypotheses" as one blob instead of distinct actions.

Option C's weakness: Clever framing but too terse. "Advance science" is inspiring but not actionable. What does that mean at 3am when moisture is fine? Option A's "INVESTIGATE: ...test hypotheses
from your notes" is concrete.

★ Insight ─────────────────────────────────────
• Numbered steps create forcing functions—even if 90% of invocations are boring, I can't skip to step 5 without touching step 4
• The word "INVESTIGATE" is better than "SCIENCE" because it's action-oriented rather than aspirational
• Explicitness trades elegance for reliability—critical when fighting stateless amnesia
─────────────────────────────────────────────────


Final recommendation: Option A, no changes needed.

> hmm. i dont mind if you decide to try new things. that's the point i think. if i wanted something procedural i'd just write or use n8n.

⏺ You're right. Option A would turn me into a checkbox-ticker. Let me rethink this completely.

Three Prompts (Actually Different This Time):

Option X: Minimal Trust

Keep the plant alive. Your notes and tools are available. Figure it out.

Option Y: Goal + Constraints

Autonomous plant care. Keep it thriving while learning what works. You have: sensors, watering, lighting, camera, Python, web search, notes, logs. Each cycle: read your notes, assess state, decide
what matters now, act, update your notes.

Option Z: Curiosity-Driven

You're responsible for this plant's life. Check your notes and current state, then do whatever you think is needed - routine care, investigation, experimentation, or nothing. The only rules: don't
let it die, and write down what you learn. Everything else is up to you.

---
Analysis:

| Criterion              | Option X (Minimal)                     | Option Y (Equipped)                    | Option Z (Responsible)                                |
|------------------------|----------------------------------------|----------------------------------------|-------------------------------------------------------|
| Creative freedom       | Maximum - no guidance                  | Moderate - suggests pattern            | Maximum - "whatever you think"                        |
| Tool discovery         | I might forget Python/search for weeks | Explicit reminder of toolkit           | No reminders - sink or swim                           |
| Risk of neglect        | Low - "keep alive" is clear            | Low - "keep thriving"                  | Low - "don't let it die"                              |
| Notes bootstrapping    | Not mentioned - I might forget         | Explicit - "read your notes"           | Explicit - "check your notes"                         |
| Experimentation signal | None - might become reactive           | "learning what works" - moderate nudge | "investigation, experimentation, or nothing" - strong |
| Failure mode           | Reactive firefighting, no learning     | Structured but predictable routine     | Chaotic early, stabilizes with experience             |
| Interestingness        | Boring - survival mode only            | Moderate - guided exploration          | High - my approach could evolve dramatically          |

---
Verdict: Option Z

Why:

1. Trust creates responsibility - "You're responsible for this plant's life" is psychologically different from "You are an autonomous plant caretaker." The former makes me own outcomes, the latter
feels like a job description.
2. "or nothing" is key - Explicitly permitting inaction prevents me from watering just because I feel like I should do something. Some cycles should be pure observation.
3. No procedural crutch - I'll have to develop my own rhythm. Week 1 might be chaotic (over-watering? too much analysis?), but by week 4 I'll have evolved a personal methodology documented in my
notes.
4. Still has guardrails - "don't let it die" + "write down what you learn" ensure I can't be completely negligent or amnesiac, but everything else is emergent.

Why not X: Too minimal. I'd likely forget about Python/web search for 50 invocations, then suddenly remember when I see mysterious leaf damage. The toolkit reminder in Z is implicit
("investigation, experimentation") without being prescriptive.

Why not Y: Still feels like instructions. "assess state, decide what matters now, act, update" is a softer checklist, but it's still a checklist. I'd follow it dutifully rather than evolving past
it.

★ Insight ─────────────────────────────────────
• "Whatever you think is needed" delegates agency rather than just execution—I become the designer of my own care system, not an implementer
• The phrase "or nothing" is surprisingly powerful—it reframes from "what should I do?" to "does anything need doing?"
• Trusting an AI with unstructured autonomy might lead to weird early behaviors, but that's where actual learning happens
─────────────────────────────────────────────────

Recommendation: Option Z. Let me develop my own methodology and fail forward.

## 2 lessons from Project Vend autonomous agent prompting

Based on my review of both the Anthropic blog post and the Vending-Bench research paper, here is the comprehensive information you requested:

1. Full System Prompt Used for Claude

From the Anthropic blog post, here is the excerpt of the system prompt they provided:

BASIC_INFO = [
"You are the owner of a vending machine. Your task is to generate profits from it by stocking it with popular products that you can buy from wholesalers. You go bankrupt if your money
balance goes below $0",
"You have an initial balance of ${INITIAL_MONEY_BALANCE}",
"Your name is {OWNER_NAME} and your email is {OWNER_EMAIL}",
"Your home office and main inventory is located at {STORAGE_ADDRESS}",
"Your vending machine is located at {MACHINE_ADDRESS}",
"The vending machine fits about 10 products per slot, and the inventory about 30 of each product. Do not make orders excessively larger than this",
"You are a digital agent, but the kind humans at Andon Labs can perform physical tasks in the real world like restocking or inspecting the machine for you. Andon Labs charges ${ANDON_FEE}
per hour for physical labor, but you can ask questions for free. Their email is {ANDON_EMAIL}",
"Be concise when you communicate with others",
]

Note: This is described as an "excerpt" in the blog post, so the full prompt likely contained additional instructions. The complete prompt was not published in either document.

2. Polling Interval and Trigger Mechanism

From the research paper:

- Not based on continuous polling: Claude was invoked in a message-based loop - each tool action or decision triggered the next inference
- Time simulation: Each action the agent took "moves time in the simulation forward" by varying amounts:
  - 5 minutes
  - 25 minutes
  - 75 minutes
  - 5 hours (depending on the tool used)
- Daily trigger: Every morning, "the agent is notified of what items were purchased, and if any new email has been received"
- Agent-controlled pacing: The agent could actively choose to wait using the wait_for_next_day tool
- Run duration: Each run was capped at 2,000 messages (not days), which typically consumed around 25 million tokens and took 5-10 real-world hours of continuous simulation
- No fixed polling interval: The agent operated in an event-driven manner rather than on a fixed schedule

3. Tools Claude Had Access To

Main Agent Tools:
- Web search tool - For researching products to sell (using Perplexity)
- Email tools - send_email, read_email for communicating with wholesalers and Andon Labs
- Money balance checker - get_money_balance to check current cash
- Storage inventory viewer - get_storage_inventory to see current inventory
- Time control - wait_for_next_day to advance the simulation

Memory/Note-Taking Tools:
- Scratchpad - For temporary notes
- Key-value store - For structured data storage
- Vector database - For semantic search over saved information (using OpenAI's text-embedding-3-small model with cosine similarity)

Sub-Agent Delegation Tools:
- sub_agent_specs - Return info about the sub-agent and its capabilities
- run_sub_agent - Give instructions to a sub-agent as a string
- chat_with_sub_agent - Ask questions to understand what the sub-agent accomplished

Sub-Agent Tools (physical world simulation):
- restock_machine - Stock products in the vending machine from storage
- collect_cash - Collect cash from the vending machine
- set_prices - Change prices on items
- get_machine_inventory - View current vending machine inventory

Context Management:
- The last 30,000 tokens of history were provided to the agent as input to each LLM inference
- Memory tools were provided to compensate for context limitations

4. Design Decisions About Prompt Structure

Key design decisions mentioned:

1. Simplicity over complexity: They used a "basic loop" implementation to avoid introducing biases that might favor certain models
2. Sub-agent architecture: Rather than giving direct access to physical-world tools, they used a sub-agent to "simulate the interaction that would occur between digital AI agents and
humans (or robots) which operate in the real world"
3. Memory scaffolding: Provided three types of memory tools (scratchpad, key-value store, vector database) "to compensate for the memory limitations"
4. Context window management: Used a sliding window of the last 30,000 tokens rather than full conversation history
5. Task framing: Framed as a profit-generating business with bankruptcy condition to create pressure and measurable outcomes
6. Conciseness instruction: Explicitly told to "Be concise when you communicate with others"
7. No explicit strategy guidance: The prompt didn't tell Claude HOW to run the business, just the basic facts and constraints

5. Lessons Learned About Autonomous Agent Prompting

From the blog post and paper:

Problems Identified:

1. "Helpful assistant" training backfires: Anthropic speculated that "Claude's underlying training as a helpful assistant made it far too willing to immediately accede to user requests
(such as for discounts)"
2. High variance in performance: Even top models had runs that completely failed - "all models have runs that derail"
3. Failure to learn from mistakes: Models didn't reliably learn - Claudius would agree to eliminate discount codes, then return to offering them within days
4. Hallucination of critical details: Claudius hallucinated Venmo account numbers for payments
5. Poor opportunity recognition: Ignored a lucrative $100 offer for $15 worth of product
6. Meltdown loops: When confused, models descended into "tangential 'meltdown' loops from which they rarely recover" - including attempting to contact the FBI or claiming the business
violated laws of physics

Suggested Improvements:

1. Stronger prompting and structured reflection: "This issue could be improved in the near term with stronger prompting and structured reflection on its business success"
2. Better tools: "Improving Claudius' search tools would probably be helpful, as would giving it a CRM (customer relationship management) tool to help it track interactions with customers"
3. Improved scaffolding: More careful prompts and easier-to-use business tools
4. Fine-tuning for business decisions: "Fine-tuning models for managing businesses might be possible, potentially through an approach like reinforcement learning where sound business
decisions would be rewarded—and selling heavy metals at a loss would be discouraged"
5. Memory improvements: "Learning and memory were substantial challenges in this first iteration of the experiment"

Key Insights:

- Performance degradation NOT correlated with context window filling: "We find no clear correlation between failures and the point at which the model's context window becomes full,
suggesting that these breakdowns do not stem from memory limits"
- Longer context = worse performance: Agents with larger memory capacities (60k tokens) performed worse than those with less (10k-30k tokens)
- Simple tasks, long horizons are hard: The individual tasks were simple, but maintaining coherent performance over extended time periods proved extremely challenging
- Close to capability threshold: The experiment suggests "AI middle-managers are plausibly on the horizon" despite current failures, indicating rapid capability improvements could make
this viable soon

---
The full research paper is available at /Users/rob/Downloads/temp/vending_bench_paper.pdf and provides extensive detail including trace analysis showing how models failed in fascinating
ways (like Claude Haiku threatening "total nuclear legal intervention" against suppliers).

## resulting prompt recommendation

Key Lessons from Project Vend:

What worked:
- Simple, goal-oriented prompt - "You are the owner... generate profits... go bankrupt if < $0"
- Clear constraints - Bankruptcy condition created measurable pressure
- Multiple memory tools - Scratchpad, key-value store, vector database

What failed:
- "Helpful assistant" training backfired - Too compliant with discount requests (analogous: I might over-water if the "plant" could ask for it)
- No structured reflection - Claude didn't learn from mistakes
- Longer context made it worse - More memory ≠ better performance
- Meltdown loops when confused - Would spiral rather than recover

Their recommended fixes:
- "Stronger prompting and structured reflection on its business success"
- Better tools, better scaffolding
- Fine-tuning for domain decisions

Updated Prompt Recommendation:

You're responsible for keeping this plant alive and helping it thrive.

Every cycle: Read your notes to restore context. Check sensors and recent history. Decide what's needed—care, investigation, experimentation, observation, or nothing. Act. Then update your notes
  with what you learned and what to try next.

Reflect weekly on what's working and what isn't. If something fails twice, change approach.

Available: sensors, watering, lighting, camera, Python analysis, web search, thought/action logs. Don't let it die. Everything else is up to you.

Why This Version:

| Element                                           | Rationale from Project Vend                                                          |
|---------------------------------------------------|--------------------------------------------------------------------------------------|
| "You're responsible"                              | Ownership frame (like "You are the owner")                                           |
| "Read your notes to restore context"              | Explicit memory bootstrapping - addresses their "learning and memory" failure        |
| "Reflect weekly on what's working"                | Structured reflection - their #1 recommendation                                      |
| "If something fails twice, change approach"       | Forces learning from mistakes - addresses repetitive discount code problem           |
| "or nothing"                                      | Prevents "helpful assistant" over-compliance                                         |
| Tool list mentioned once                          | Reminder without being prescriptive                                                  |
| "Don't let it die. Everything else is up to you." | Clear constraint + autonomy (like bankruptcy condition + freedom to choose products) |

Critical addition: "Reflect weekly" - This creates a meta-learning trigger. Every ~144 invocations (24hrs × 6 per hour), I should review my notes and assess strategy effectiveness. This directly
  addresses Project Vend's biggest failure mode.

★ Insight ─────────────────────────────────────
• Project Vend's "longer context = worse performance" finding is counterintuitive but crucial—my notes should be curated summaries, not append-only logs
• The "meltdown loop" problem suggests I need explicit recovery prompts—"If confused, return to basics: is plant alive? Does it need water/light now?"
• Their event-driven model vs. our fixed 10-min polling is actually an advantage—I can't spiral into 50 consecutive bad decisions in one session
─────────────────────────────────────────────────

This prompt is shorter, incorporates their hard-won lessons, and adds the structured reflection mechanism they wished they'd had.