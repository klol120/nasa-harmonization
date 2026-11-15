# Greece: comparison with docs/methods.pdf (Phase 4)

PDF rules (no persistence exclusion). Source tables: `docs/reports/greece_validation.md`.

| quantity | PDF | ours | match |
|---|---|---|---|
| single ratio, fit 2012-16 (Table 2) | 2.78 | **2.783** | yes |
| Table 1, cleaned detections | 3.41 | 3.40 | yes |
| Table 1, fire-days 0.01° / 0.05° / 0.10° | 2.63 / 2.86 / 2.89 | 2.63 / 2.86 / 2.88 | yes |
| Table 2, single ratio WAPE / bias | 0.26 / −7% | 0.261 / −7.0% | yes |
| Table 2, monthly a_m WAPE / bias | 0.19 / 0% | 0.189 / +0.7% | yes |
| kT overall, range | 2.16, 1.7 (Aug) to 4.0 (Feb) | 2.15, 1.73 (Aug) to 3.97 (Feb) | yes |
| a_m range | 2.2 (Aug) to 5.0 (Dec) | 2.20 (Aug) to 5.15 (Jan); Dec 4.99 | see 1 |
| cleaned totals MODIS / VIIRS | 43,623 / 70,195 | 43,623 / 70,197 | see 2 |
| monthly log-count r | 0.95 | 0.943 | see 3 |

## Remaining differences, one line each (none points to a bug)
1. **January vs December maximum.** We fit only on days both sensors have data, so January 2012
   MODIS days 1–19 (before VIIRS) are excluded. Counting them, as the PDF apparently did, gives
   Jan 4.95 < Dec 4.99, which matches the PDF.
2. **VIIRS 70,197 vs 70,195.** A 2-detection (0.003%) difference, most likely an archive revision or a
   one-off duplicate rule. It changes no reported ratio at the shown precision.
3. **r 0.943 vs 0.95.** The definition is unstated. log1p over all months gives 0.946 and including
   outage days gives 0.945, both 0.95 at one decimal less. This is a rounding or definition difference.
4. **kT 2.15 vs 2.16.** We drop flagged outage days (e.g. Terra 2016-02-19→27) from the fit. This is
   within rounding.
