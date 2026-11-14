# Contributing

## Deploying & branches

- **Work on `dev`** (or a short-lived branch off `dev`). Don't push to `main` directly.
- **Open a pull request from `dev` into `main`.** The **CI** workflow runs on every PR (into `main` or
  `dev`) and on every push to `dev`: it typechecks and builds the website (`web/`) and runs the backend
  tests that don't need a database (`pytest -m "not db"` in `backend/`). Nothing is deployed from CI.
- **Merging into `main` deploys automatically** to Azure Container Apps (workflow **Deploy to Azure**,
  `.github/workflows/deploy-azure.yml`). Only what changed is rebuilt: `backend/**` rebuilds the API,
  `web/**` rebuilds the website. A merge that touches neither deploys nothing.
- **Watch the run:** GitHub → **Actions** tab → **Deploy to Azure** → the run for your merge commit.
  Each job builds the image in Azure, rolls it out, waits for the new revision and then checks the site
  answers. A red job means the new version is not live; the previous one keeps serving.
- **Live URLs**
  - Website: https://wel3a-web.blackwave-481696ae.francecentral.azurecontainerapps.io
  - API: https://wel3a-api.blackwave-481696ae.francecentral.azurecontainerapps.io
    (health: `/health`, docs: `/docs`)
- **Redeploy by hand:** Actions → **Deploy to Azure** → **Run workflow** → branch `main` → **Run workflow**.
  This rebuilds and redeploys both the API and the website from the current `main`.
- **Data loading is not part of the pipeline.** Deploying ships code only. Loading or refreshing data
  in the database (`python -m firecal_api.cli ingest`, see `backend/README.md`) is done by hand against
  the database; a deploy never runs it.

Run the same checks locally before opening a PR:

```sh
(cd web && npm ci && npm run build)
(cd backend && uv run python -m pytest -q -m "not db")
```
