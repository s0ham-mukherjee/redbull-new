# Simulation Methodology — sakura-abm

**SakuraScore India — Simulation & Research Subsystem**

This document specifies exactly what the engine computes, every assumption it embeds, and why the paired-scenario design is statistically meaningful. Read `LIMITATIONS.md` before quoting any number.

---

## 1. Model class and purpose

`sakura-abm` is a **compact, deterministic, stochastic-threshold agent-based model** of an Indian audience reacting to a Japanese-media IP release under different availability strategies (notably: regional-language dubbing). Agents are NOT LLM personas (contrast: OASIS/MiroFish — see `REPOSITORY_EVALUATION.md`). Each agent is a parameterised actor whose per-round behaviour is decided by comparing fixed random draws against interpretable probabilities.

**Question it answers:** *under stated assumptions, how does a release-strategy variable (languages offered, marketing mix) shift reach and engagement across audience segments, and how stable is that shift across repeated runs?*

**Question it does NOT answer:** real-world revenue, viewership, or awareness forecasts.

## 2. World structure

- **Population:** `agent_count` agents (config; default 20, example 40).
- **Segments:** `audience_segments[]` partition the population by share (`size_share` sums to 1.0, tolerance 0.01). Each segment carries behavioural parameters (§5). Segment assignment is a per-agent draw from the share distribution.
- **Social graph:** Barabási–Albert preferential-attachment graph, degree `network_degree` (default 3) — a standard simplifying model of community/cluster structure in fan networks. Implemented in pure stdlib with insertion-order tie-breaking (`adapters/abm_engine.py :: build_barabasi_albert`).
- **Rounds:** `rounds` discrete steps (default 5). Round 0 carries a release-announcement attention spike (`announcement_boost`).

## 3. Agent state machine

```
UNAWARE ──discover──> AWARE ──view_info──> VIEWED ──express_interest──> ENGAGED
   ▲                    |                     |                            |
   └────────── ignore (no draw passed)        (engaged agents may share/discuss every round)
```

Per round, per agent, in fixed order, the engine draws **five uniforms in unconditional slots** (discover, view, interest, share, discuss) from a single `random.Random(seed)` stream, then compares each against its probability **only if the corresponding stage is active**. Unconditional drawing keeps the RNG stream *identical across scenarios with the same seed* — the basis of the paired design (§7).

## 4. Behavioural equations (v0.1.0)

Notation: agent *a* in segment *s*; scenario *X* offers languages `L(X)` and marketing multipliers `M(X)` (per channel); `fit(a, X) = max_{l ∈ L(X)} affinity_s(l)` — the agent's best affinity across offered languages; if that maximum is 0 and English is not offered, a hard subtitle-tolerance floor applies (`LANG_MOD_INTEREST_FLOOR = 0.25`).

| Stage | Probability | Notes |
|---|---|---|
| Discover (if unaware) | `min(cap, discovery_base_s · mix(a, X) · (0.7 + 0.3·fit) · (1 + wom_boost · engaged_neighbour_share) · susceptibility_a · announcement(r=0))` | `mix(a, X)` = channel multipliers of `M(X)` weighted by the segment's `channel_affinity`; `cap = discovery_cap` (default 0.95) |
| View info (if aware, not viewed, not engaged) | `min(1, view_info_prob_s · (0.7 + 0.3·fit) · susceptibility_a)` | |
| Express interest (if viewed, not engaged) | `min(1, base_interest_s · (0.25 + 0.75·fit) · dub_lift_a(X) · susceptibility_a)` | `dub_lift_a(X) = dub_lift` iff the agent's *primary language* is regional and offered; else 1. Primary language is drawn per agent from the segment's `language_affinity` weights |
| Share (if engaged) | `min(1, share_prob_s · vocalness_a · (0.85 + 0.15·fit) · dub_lift_a(X))` | recorded action; feeds WOM next round |
| Discuss (if engaged) | `min(1, discuss_prob_s · vocalness_a · (0.85 + 0.15·fit) · dub_lift_a(X))` | recorded action; feeds WOM next round |

Personal heterogeneity: `susceptibility ~ U(0.7, 1.3)`, `vocalness ~ U(0.75, 1.25)` — per-agent, drawn once from the seeded stream.

## 5. Segment parameters (input, treated as hypotheses)

`base_interest`, `discovery_base`, `view_info_prob`, `share_prob`, `discuss_prob`, `language_affinity{}`, `channel_affinity{}` — all validated to [0,1], all supplied by the config, all surfaced verbatim in results. The example config links each segment to cited evidence ids (`data/evidence/india_anime_evidence.json`) but the mapping "evidence → parameter value" is an interpretive judgement, not a measurement. **No survey responses were collected or fabricated.**

## 6. Randomness & reproducibility protocol

1. One RNG: `random.Random(seed)` (Mersenne Twister), created per scenario run.
2. Consumption order (fixed, engine-versioned): (a) graph construction; (b) population draw — segment, primary language, susceptibility, vocalness, per agent in id order; (c) per round, per agent (id order): the five unconditional draws.
3. Determinism: identical `(config, seed)` ⇒ identical JSON output (tested: `tests/test_runner.py :: test_reproducibility_identical_json`).
4. Variability: `simulation.seeds` (≤25) runs the *whole experiment* once per seed; the headline block reports `seed` (= `simulation.seed`, always seeds[0]); scenario `variability` blocks report mean/std/min/max per metric; comparisons aggregate paired deltas across seeds.
5. `run_metadata` records engine version, RNG description, python version, config hash — enough to re-run byte-identically.

## 7. Paired scenario design (why the A/B is defensible)

For repetition *i*, every scenario runs with the **same seed** ⇒ identical population, graph, and RNG stream. Only acceptance thresholds differ. Consequences:

1. **Variance reduction:** scenario deltas are computed *within* a seed, removing between-population variance — the reason `delta_std` is small relative to raw metric std.
2. **Monotonicity invariant:** if scenario B's languages ⊇ scenario A's languages and marketing is equal, every stage threshold in B is ≥ its counterpart in A (`dub_lift ≥ 1` by validation). By induction across rounds, B's aware/viewed/engaged sets are supersets of A's at every round. Tested across 100 seeds (`scripts/debug_monotonic.py`) and 30 seeds in the suite (`test_runner.py :: test_paired_monotonicity_across_seeds`).
3. **Attribution:** because the only manipulated inputs are the scenario fields, `comparisons[].drivers` lists exactly which inputs differ and which engine assumption each activates.

Caveat: monotonicity guarantees *directional* stability of the aggregate effect under this model, **not** real-world validity. The magnitude rests entirely on the assumption values (§8).

## 8. Assumption register (also emitted in results `assumptions[]`)

| Assumption | Value (default) | Basis / linked evidence | Sensitivity |
|---|---|---|---|
| `dub-lift` | `dub_lift = 1.6` | Judgement informed by distributor behaviour (Crunchyroll 2024–2026 HI/TA/TE slates; Infinity Castle India JP/HI/TA/TE release setting the all-time anime opening record; Muse Hindi dub channel investments) — evidence ids in results. NOT a measured elasticity. | Direction of effect is invariant to 1 < lift ≤ 3 (monotonicity); magnitude scales roughly linearly within the interest term |
| `language-fit-modulation` | discovery 0.7+0.3·fit; interest 0.25+0.75·fit; floor 0.25 | Hypothesis: language fit modulates discovery/interest; the 0.25 floor encodes subs-tolerance | Qualitative |
| `announcement-boost` | 2.0, round 0 only | Opening-day attention spikes (Infinity Castle $1.8M opening day) | Qualitative |
| `word-of-mouth` | `wom_boost = 0.8`, BA graph m=3 | Standard ABM practice; cluster structure assumption | Ablation-tested (`test_word_of_mouth_ablation_baseline`) |
| `population-heterogeneity` | U(0.7,1.3), U(0.75,1.25) | Unexplained within-segment variance | Low |
| `segment-parameters` | config values | Segment-level hypotheses; evidence ids attached per segment | **Dominant** uncertainty in the model |

## 9. Metrics emitted

- **Totals:** `reach`/`reach_rate` (aware share), `viewed`/`view_rate`, `engaged`/`engagement_rate`, `shares_total`, `discussions_total`, `shares_per_agent` — all labelled `simulated`.
- **Per round:** action counts, cumulative aware/viewed/engaged, average WOM exposure.
- **Per segment:** population, reach, engaged, rates.
- **Per primary language:** reach, engaged, engagement rate.
- **Comparisons:** per metric paired `delta_mean/std/min/max` + `relative_lift_mean`; per-segment engagement deltas; driver list.
- **Variability:** per-scenario metric distributions across seeds.

## 10. Execution cost

~1–5 ms per run for 40 agents × 6 rounds (stdlib-only). 5000 agents × 100 rounds remains sub-second-scale. No API cost, no LLM cost, no network I/O.
