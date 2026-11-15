# Lebanon: shape-donor robustness check (2026-11-12)

`affine_shape_single_level` takes its monthly shape from an affine model and its annual level from the
single ratio. Here the shape model is either the Cyprus blend or the whole EastMed pool. Persistence is
excluded from fitting; hold-out fit 2012-16 / test 2017-20, plus the reverse fold.

| shape from | k (fwd / rev) | forward WAPE | reverse WAPE | forward bias | reverse bias | step index (new band) |
|---|---|---|---|---|---|---|
| `affine_blend:cyprus` | 0 / 5 | 0.338 | 0.417 | −4.7% | +4.9% | 1.025 [0.77, 1.29] |
| `affine_blend:eastmed_pool` | 5 / 5 | 0.342 | **0.379** | −4.7% | +4.9% | 1.025 [0.77, 1.29] |

**Rule:** use the pool if its WAPE is within 0.03 of Cyprus on both folds. The forward difference is
+0.004. The reverse difference is −0.038, so the pool is *better* there. I read "within 0.03" as "no more
than 0.03 worse", and the pool passes.

**Decision:** the default is now `affine_shape_single_level_pool`. Bias and continuity are identical
(both use single's annual level), and the pool shape rests on far more data. The Cyprus version stays
selectable in `calibration.composites`.
