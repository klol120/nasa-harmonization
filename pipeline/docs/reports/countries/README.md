# Countries added with `python -m firecal add-country`

Generated from the per-country reports in this folder. Grades: config `add_country.grades` (judgement thresholds; the v1.0 regions grade Greece A, EastMed B, Lebanon B).

| country | detections (raw / clean) | strategy (outcome) | VIIRS/MODIS | hold-out WAPE fwd / rev | bias fwd / rev | step at 2012 [band] | grade | runtime | in the app |
|---|---|---|---|---|---|---|---|---|---|
| [Cyprus](cyprus.md) | 10,604 / 6,474 | `affine_shape_single_level_pool_ex_cyprus` (thin) | 3.98 | 0.559 / 0.648 | -14.0% / +16.3% | 0.971 [0.74, 1.277] | **D** | 7.2 min | yes |
| [Jordan](jordan.md) | 17,611 / 9,920 | `affine_shape_single_level_pool` (thin) | 6.138 | 0.466 / 0.518 | +18.9% / -15.9% | 1.733 [0.977, 2.879] | **C** | 10.0 min | yes |
| [Portugal](portugal.md) | 245,126 / 226,100 | `local` (rich) | 1.701 | 0.231 / 0.192 | +12.3% / -6.1% | 1.098 [0.943, 1.242] | **B** | 10.5 min | yes |
| [Syria](syria.md) | 378,070 / 221,381 | `local` (rich) | 3.461 | 0.275 / 0.229 | +11.0% / -7.8% | 1.187 [0.927, 1.464] | **B** | 10.4 min | yes |
| [Turkey](turkey.md) | 1,255,497 / 879,340 | `local` (rich) | 2.463 | 0.143 / 0.157 | -7.4% / +10.4% | 0.962 [0.884, 1.039] | **B** | 15.7 min | no |
