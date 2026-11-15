# Initial plan review, before implementation

The repository was inspected read-only before any files changed. It contains a monthly
fire-calendar dashboard and database service, monthly exports and a storage helper for
monthly predictions. CONTRIBUTING requires dev-based work and warns that main merges
deploy automatically. Implementation uses a feature branch from origin/dev.

The requested task is scientifically reasonable but its main dependencies are data,
not model complexity. Monthly harmonized totals cannot establish a next-day binary
label. NOAA/NASA satellite detections are incomplete observations and their observing
systems change over time. A historical weather fit is not operational forecasting.

The existing fire-associated grid may omit never-burning vegetation: reusing it could
inflate prevalence and invalidate location-wide probabilities. EastMed includes
Lebanon; country-level pooling can duplicate data and hide unsuitable climate strata.
A broad global model would add data-management and transfer uncertainty before a
credible local baseline is established.

Automatic industrial filtering would risk erasing recurring vegetation fires. Conflict
and explosion records have variable reporting/coordinate precision and cannot prove
that a nearby detection is non-target. Exclusion must quarantine the cell-window,
not erase a detection and manufacture a negative. Policy selection should not minimize
metrics across populations changed by exclusions.

Therefore the first delivery isolates daily research code from the monthly app,
requires explicit forecast/feature availability and label observability, runs simple
baselines first, compares fixed filtering analyses, provides a synthetic mechanics
fixture when archives are absent, and documents blocked real-data integration. Deep
learning, global training, real operational performance and causal infrastructure
impact are outside what the available evidence supports.
