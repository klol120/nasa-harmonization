# NASA harmonization / Wel3a

* [`web/`](web/README.md): React/TypeScript fire-history dashboard.
* [`backend/`](backend/README.md): FastAPI/PostgreSQL monthly harmonized data service.
* [`forecasting/`](forecasting/README.md): isolated Python research pipeline for
  next-24-hour satellite-detected vegetation-fire occurrence in Lebanon, with
  notebooks, auditable labels, real NASA training, reserved-year evaluation and documented release gates.
* [`data_contract.md`](data_contract.md): existing monthly export contract.
* [`CONTRIBUTING.md`](CONTRIBUTING.md): branches, checks and deployment behavior.

The daily forecasting project does not reinterpret monthly exports as daily ground
truth. Its real-data model is retrospective and does not establish operational forecast reliability.
