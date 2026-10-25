# SakuraScore simulation summary — Demon Slayer: Kimetsu no Yaiba - The Movie: Infinity Castle

- Experiment: `regional-dubbing-test` | Status: **completed** | Engine: `sakura-abm v0.1.0`
- ALL numeric results below are **SIMULATED** under stated assumptions (see output `assumptions` and `limitations`). They are not forecasts.

## Scenario headline metrics (seed = configuration seed)

| Scenario | Languages | Reach rate | View rate | Engagement rate | Shares | Discussions |
|---|---|---|---|---|---|---|
| Baseline: Japanese + English (subbed) availability | ja, en | 55.0% | 50.0% | 37.5% | 17 | 18 |
| Regional-language strategy: + Hindi, Tamil, Telugu dubs | ja, en, hi, ta, te | 60.0% | 57.5% | 45.0% | 20 | 27 |

**Variability** (5 seeds [42, 43, 44, 45, 46]): engagement_rate mean 49.0% ± 8.3% [min 37.5%, max 62.5%] — simulated.

**Variability** (5 seeds [42, 43, 44, 45, 46]): engagement_rate mean 60.5% ± 8.4% [min 45.0%, max 70.0%] — simulated.

## Paired scenario comparison (same seeds, identical populations)

### regional-dub vs baseline-subs-only (5 paired repetitions)

| Metric | Baseline mean | Comparison mean | Δ mean | Relative lift |
|---|---|---|---|---|
| reach_rate | 68.5% | 74.0% | 5.5% | +8.4% |
| engagement_rate | 49.0% | 60.5% | 11.5% | +24.5% |
| view_rate | 63.0% | 68.0% | 5.0% | +8.7% |
| shares_total | 17.00 | 29.60 | 12.60 | +81.9% |
| discussions_total | 17.20 | 29.60 | 12.40 | +81.6% |

- Driver: `languages_available` → dub_lift applied to agents whose primary language is regional and newly offered (simulation.dub_lift); language-fit modulation of discovery/interest (constants in adapters/abm_engine.py).

Per-segment engagement-rate delta (simulated): `casual-streaming-viewers` +10.3%, `film-event-audiences` +15.0%, `mainstream-anime-fans` +2.9%, `manga-first-readers` +0.0%, `regional-language-first` +28.0%

## Key assumptions (all labelled simulated/inferred in the JSON)
- **dub-lift**: Agents whose primary language is a regional language newly offered by a scenario receive a multiplicative lift on interest, share and discuss probabilities (simulation.dub_lift).
- **language-fit-modulation**: Discovery probability scales with language fit via 0.7 + 0.3*fit; interest scales via 0.25 + 0.75*fit; agents without any offered-language fit fall back to a 0.25 subtitle-tolerance floor.
- **announcement-boost**: Round 0 models a release announcement: discovery probability is multiplied by simulation.announcement_boost in the first round only.
- **word-of-mouth**: Discovery probability is multiplied by (1 + simulation.word_of_mouth_boost * engaged-neighbour share) over a Barabasi-Albert preferential-attachment graph.
- **population-heterogeneity**: Personal susceptibility ~ U(0.7, 1.3) and vocalness ~ U(0.75, 1.25) are unexplained heterogeneity drawn per agent from the seeded stream.
- **segment-parameters**: Segment sizes, base_interest, discovery_base, view/share/discuss probabilities, language and channel affinities are supplied by the config and treated as hypotheses; each segment lists its evidence_ids. (evidence: animesurvey-2025-india-share, ann-muse-hindi-launch, crunchyroll-dubs-may-2024, forbes-nrg-india-penetration, ign-infinity-castle-opening, imdb-crunchyroll-13-dubs-2024, imdb-infinity-castle-india-release, kenresearch-india-180m-fans, koyoharu-opening-day-record, muse-india-channel-scale, statista-crunchyroll-subs, wiki-infinity-castle-worldwide)

## Limitations (excerpt)
- [critical] Outputs are simulations of a hypothesised audience under explicit assumptions. They are NOT predictions of real awareness, revenue, viewership or streaming performance, and must never be presented as such.
- [critical] Agents are stochastic-threshold actors parameterised by segment hypotheses. They do not represent real Indian consumers, and no survey responses were collected or fabricated.
- [high] Audience segment sizes and behavioural parameters are modelling hypotheses informed (where noted) by cited public evidence, not measured demographics.
- [high] sakura-abm is a compact scenario model. Unlike OASIS/MiroFish LLM agents it cannot generate novel discourse; interaction structure (word-of-mouth over a preferential-attachment graph) is a simplifying assumption.

## Evidence base: 18 cited source(s) in `source_references` (all labelled observed/inferred, with URL + date).