# While you were away (2026-11-12)

## Most important first
1. **All three regions are exported** to `data/export/{lebanon,greece,eastmed}/`:
   `calendar.parquet`, `calendar.csv.gz`, `region_monthly.csv`, `region_monthly.json`, `cells.json`,
   `cells.geojson`, `meta.json`. The data contract is 0.2 (`docs/data_contract.md`), with
   `low_confidence`, `is_persistent`, `data_available` and `partial_month`.
   - data/ is gitignored, so the files are local only.
   - Regenerate them with `.venv/bin/python -m firecal all --region eastmed greece lebanon` (about 1.5 min).
2. **Lebanon's default is now `single`**, one ratio of 5.47 for every month, also for kT (2.20).
   - It is the top-ranked strategy under your rule (continuity and bias first, WAPE second).
   - It ignores the seasonal shape of the ratio, and its monthly error is high (WAPE 0.55).
   - The affine models halve the error (WAPE 0.26–0.28, bias near 0), but they add a 14–19% step at
     2012.
   - **This is the main decision for you to review.** See the table below.
3. **Greece matches the PDF.** The 2012–16 single ratio is 2.783 against 2.78, and Tables 1 and 2 match.
   No difference points to a bug (`docs/reports/greece_phase4.md`).
4. **Lebanon's problem is structural.** 84–100% of VIIRS fire-days fall in cell-days where MODIS saw
   nothing, in every month. No transfer from MODIS can recover that activity before 2012, so the
   pre-2012 values are flagged `low_confidence` for Jan–Jun and Dec.
5. **Git.** `main` holds the approved Phases 0–3. Phases 4–5 are on the branch
   **`autonomous-phase4-5`** (4 commits), not merged.
6. **Tests.** All 74 pass. None was loosened or deleted.

## Lebanon strategy comparison
- Persistence-excluded fitting (the default), hold-out fit 2012–16 / test 2017–20.
- The ranking rule:
  1. continuity not flagged under the new band;
  2. score = |step − 1| + mean(|forward bias|, |reverse bias|);
  3. forward WAPE.
- Full table (28 strategies): `docs/reports/lebanon_experiment.md`.

| rank | strategy | step index | new band | old band | fwd bias | fwd WAPE | rev bias | rev WAPE | score |
|---|---|---|---|---|---|---|---|---|---|
| **1** | **single** (default) | 1.025 | [0.77, 1.29] ok | [0.87, 1.16] ok | −4.7% | 0.547 | +4.9% | 0.532 | 0.073 |
| 2 | local | 1.033 | [0.71, 1.28] ok | [0.78, 1.14] ok | +2.0% | 0.525 | +19.8% | 0.622 | 0.142 |
| 3 | affine_blend:cyprus (k=0, ≈ affine_local) | 1.138 | [0.99, 1.27] ok | flag | +3.2% | 0.283 | −1.0% | 0.373 | 0.159 |
| 4 | donor:israel_palestine | 1.138 | [0.89, 1.37] ok | flag | −9.8% | 0.537 | +2.0% | 0.595 | 0.197 |
| 5 | blend:israel_palestine | 1.126 | [0.89, 1.35] ok | flag | −12.7% | 0.414 | +6.3% | 0.498 | 0.221 |
| 8 | affine_local | 1.138 | [1.02, 1.28] flag | flag | +3.2% | 0.283 | −3.3% | 0.298 | 0.170 |
| 11 | affine_blend_a:israel_palestine | 1.159 | [1.03, 1.30] flag | flag | +5.2% | 0.260 | −3.3% | 0.261 | 0.201 |
| 18 | blend:eastmed_pool (old default) | 1.284 | [1.01, 1.56] flag | flag | −27.5% | 0.437 | −3.6% | 0.445 | 0.439 |

**Old vs new continuity band.**
- The old band (factor bootstrap only) flags every strategy except `single` and `local`.
- The new band (with year-to-year spread) flags 21 of 28 strategies:
  - every affine strategy except `affine_blend:cyprus`;
  - the ratio blends with Cyprus, southern Turkey and the whole pool;
  - the pooled/donor strategies with Cyprus, Syria, southern Turkey and the whole pool.
- 7 pass: `single`, `local`, `affine_blend:cyprus`, and the donor, pooled and blend strategies with
  Israel/Palestine, plus `blend:syria`.

**Hold-out bias by year (is it 2019–2020?).**
- **2019:** every strategy under-predicts (−16% to −44%).
- **2020:** most strategies over-predict (+9% to +30%).
- So the bias is not concentrated in the crisis period as a whole; only 2019 stands out. Year-to-year
  swings are large (local: +60% in 2013, −31% in 2014).

## Decisions I took on your behalf
1. **Bias in the ranking uses both hold-out folds.** One 4-year fold is too noisy for Lebanon. With
   forward bias only, `local` would rank first (its reverse bias is +20%).
2. **Lebanon kT is `single`** (2.20). Monthly local kT rests on 0–4 Terra fire-days in winter and has
   bands of 1.0–4.1. It only affects the 20 Terra-only months (2000-11 to 2002-07).
3. **Greece and EastMed stay on `local`** (the PDF method), validated with no step at 2012. Only Lebanon
   was ranked.
4. **The low_confidence rule.**
   - A pre-2012 month is flagged when its calendar month has, on 2012–2020, fewer than 20 local MODIS
     fire-days, or at least 95% of VIIRS fire-days in MODIS-zero cell-days.
   - Results: Lebanon Jan–Jun and Dec; Greece May; EastMed none.
   - The thresholds are my judgement and live in `config.low_confidence`.
5. **Affine strategies are in the pipeline** (selectable, not used).
   - The intercept b is spread over cells by each cell's share of overlap VIIRS fire-days.
   - The donor b is scaled by footprint cell counts.
   - The bands combine the a and b quantiles per component, which is approximate.
6. **Anomaly sensitivity** is reported in `docs/reports/{region}_anomalies.md`.
   - Lebanon region z: corr 0.90 and mean |Δz| 0.68 between the 2001–2025 and 2012–2025 baselines.
   - The months with |z| > 2 go from 11 to 35.
   - Greece: corr 0.90, |Δz| 0.47. EastMed: corr 0.94, |Δz| 0.41.
7. **Git setup.** I initialised git and committed Phases 0–3 to `main`, then branched. data/ is
   gitignored except the manifest, so the export files aren't committed.

## Failed, fixed or uncertain
- **Fixed bugs** found by the new tests:
  - `meta.json` `first_month` took the minimum year and minimum month separately (it showed 2000-01).
  - validate crashed when a break period had no years.
- **Uncertain:** the Lebanon default. `single` wins on continuity and bias but loses the seasonal
  pattern. `affine_blend:cyprus` / `affine_local` are about twice as accurate month by month, but show
  a 14% step.
- **Not reviewed:** the outage suspects (`docs/reports/outage_suspects.md`). Aqua 2020-08-26→28 has
  weak evidence (P ≈ 9e-4). None is flagged.
- **Coverage gap:** Northern Cyprus is still missing from the archives and excluded everywhere.
- **Nothing blocked.**

## Needs your review first
1. **The Lebanon strategy.** To switch, set `calibration.strategy.lebanon` in config.yaml to
   `local`, `affine_local` or `affine_blend_a:israel_palestine`, then rerun
   `python -m firecal all --region lebanon`.
2. **The low_confidence thresholds** (20 MODIS fire-days, 95% zero-MODIS share).
3. **Merging `autonomous-phase4-5` into `main`.**
4. **Export formats and sizes with the frontend team.** EastMed `calendar.csv.gz` is 15 MB; start from
   `region_monthly.json` and `cells.geojson`.
