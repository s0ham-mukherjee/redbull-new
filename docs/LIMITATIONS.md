# Limitations

**SakuraScore India — Simulation & Research Subsystem**

Read this before quoting any number produced by this subsystem. Limitations are also embedded in every result (`limitations[]`) so that downstream consumers cannot present outputs without them.

## 1. Critical (always shown in results)

1. **Not a forecast.** Outputs are simulations of a hypothesised audience under explicit assumptions. They are not predictions of real awareness, engagement, revenue or streaming performance, and must never be presented as such. The experiment's question is *mechanistic* ("under these assumptions, what shifts when language availability changes?"), not *predictive*.
2. **Synthetic personas are not Indian consumers.** Agents are stochastic-threshold actors with segment-level parameters. No survey was conducted, no survey responses were fabricated, and no persona claims to represent a real person or measured demographic group.

## 2. Model-structure limitations

3. **Compact scenario model.** sakura-abm does not generate natural-language behaviour, emergent discourse, or recommendation-algorithm dynamics (contrast OASIS/MiroFish, evaluated in `REPOSITORY_EVALUATION.md`). Social influence is abstracted to word-of-mouth over a Barabási–Albert graph with a fixed boost constant.
4. **Segment parameters are hypotheses.** Sizes, interests, discovery/view/share/discuss probabilities, language and channel affinities are interpretive judgements. Where public evidence exists it is cited (`source_references[]`), but the evidence → parameter mapping is qualitative. This is the **dominant** uncertainty in every number the engine produces.
5. **Key behavioural constants are assumptions.** `dub_lift` (default 1.6), language-fit modulation (0.7+0.3·fit discovery; 0.25+0.75·fit interest), subtitle-tolerance floor (0.25), `announcement_boost` (2.0), `word_of_mouth_boost` (0.8). None is a measured elasticity. The monotonicity invariant (dub ⊇ baseline ⇒ effect direction stable) holds for any lift in [1,3], but the *magnitude* scales with these constants.
6. **No marketing-side dynamics.** Marketing reach enters as static multipliers; no budgets, no creative quality, no timing curves beyond the round-0 announcement boost.
7. **Aggregate outputs only.** Per-agent action traces are intentionally not persisted in v1.0 (they exist transiently inside the engine); qualitative "what did agents say" outputs are impossible by design.
8. **Single media-market abstraction.** Channels (streaming/social/theatrical/search/tv) are generic; platform-specific dynamics (e.g. YouTube algorithm effects) are out of scope.

## 3. Evidence limitations

9. **Small, secondary, partly low-quality evidence base.** 18 curated items; market-report figures (Ken Research, MarkNtel) are commercial estimates with opaque methodology; community-sourced box-office tracking (Reddit) is labelled quality:low; global surveys contain few India-specific respondents (`animesurvey-2025-india-share`).
10. **No proprietary data.** No streaming platform viewership, no distributor deal data, no ticketing data. Dub-effect "evidence" is inferential (release language lists + headline box-office records), not causal identification.
11. **Baseline scenario is counterfactual.** The subs-only scenario did not occur for the example IP (the real release included regional dubs); it is a constructed control, labelled `counterfactual: true` in the config and results.

## 4. Validation status

12. **No external validation.** Outputs have not been compared against independent real-world outcomes (that would require holdout IPs with observed release-language variation and outcome data — a post-hackathon research project, not a 24-hour task). Internal validation only: contract tests (43), reproducibility test, paired-monotonicity invariant (30 seeds in-suite; 100 seeds via `scripts/debug_monotonic.py`), WOM ablation baseline, mechanism sanity checks (effect concentrated in dub-sensitive segments; zero in language-saturated segments).
13. **Statistical claims are bounded.** Multi-seed deltas report mean ± std over ≤25 seeds with shared populations (paired design). They characterise *model* variability, not real-world uncertainty.

## 5. Engineering & compliance scope

14. **Engine coverage.** Only `sakura-abm` is implemented. OASIS/MiroFish adapters are deliberately absent (no dead code); the documented activation paths live in `REPOSITORY_EVALUATION.md`.
15. **Research pipeline is planned, not wired.** Agent-Reach adaptation and YouTube Data API integration are specified (`RESEARCH_SOURCE_MAP.md` §4) but not installed; the shipped evidence dataset was hand-curated via ordinary web search with full provenance.
16. **Upstream licences.** MiroFish is AGPL-3.0 — nothing was copied from it. OASIS is Apache-2.0 (attribution required if we ever vendor code). Agent-Reach is MIT. Upstream checkouts remain isolated under `/home/z/my-project/upstream/` and are not distributed with this subsystem.
17. **Unresolved questions for organisers/counsel:** (a) whether embedding an AGPL-3.0 dependency (MiroFish) as a *separate network service* triggered by SakuraScore would be deemed derivative — we avoided it, but the boundary judgement is not ours to make; (b) whether hackathon judging rules permit citing commercial market-report summary figures (we cite only free public summaries).

## 6. How to probe sensitivity (cheaply)

- Rerun `run_simulation` with `simulation.dub_lift` ∈ {1.2, 1.6, 2.5}: direction should persist (monotonicity), magnitude shifts.
- Rerun with `word_of_mouth_boost = 0` (ablation shipped as a test): isolates network diffusion contribution.
- Vary `regional-language-first.size_share` (keep shares summing to 1.0): the per-segment comparison table shows where the effect lives.
- Any of these reruns cost milliseconds — there is no excuse for quoting a single-seed, single-parameter-set number as if it were robust.
