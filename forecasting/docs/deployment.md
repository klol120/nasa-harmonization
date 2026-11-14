# Deployment implementation and remaining release conditions

The API/container can run, but **no real operationally validated model exists**.
Do not describe a successful image build as successful scientific validation.
The current statecharts show both conditions separately.

## Local service

```sh
uv run uvicorn firecast.service:app --host 127.0.0.1 --port 8000
```

`GET /healthz` reports liveness. `GET /readyz` returns 503 until a trusted real
operational release passes validation. `POST /forecast` requires `X-API-Key` and
JSON `{ "records": [...] }` matching the model's feature/time contract.

Configure `FIRECAST_MODEL`, `FIRECAST_RELEASE` and a securely supplied
`FIRECAST_API_KEY`. Artifact files must come from the trusted training/release
publisher and be mounted read-only; never load user-supplied pickle/joblib files.
The approved manifest must match the artifact SHA-256 and identify validated grid
cells, observation products and weather sources. Synthetic and retrospective models
are refused even if a manifest incorrectly labels them approved.

Requests are bounded to 10,000 cell windows. Unknown/missing columns or malformed
times return 422. Future issue/availability times are rejected. Domain/range/stale
feature flags suppress probabilities in production serving. A request ID and row/
withheld counts are logged; API keys are never logged. The model loads once at
startup and inference does not write plots or temporary CSVs on each API request.
Offline CLI inference still produces CSV, GeoJSON and PNG outputs.

## Container

```sh
docker build -t lebanon-firecast forecasting
```

Where a session HTTPS proxy requires its own CA bundle, preserve certificate
verification and supply the build's optional public CA mount:

```sh
docker build --secret id=build_ca_bundle,src=/etc/ssl/certs/ca-certificates.crt \
  -t lebanon-firecast forecasting
```

The image uses the checked-in lock and a non-root user. A tested restricted run:

```sh
docker run --rm --read-only --tmpfs /tmp:rw,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8000:8000 lebanon-firecast
```

This intentionally remains unready without a release. For an approved release,
mount its directory read-only and provide the three runtime variables through your
platform's secret/runtime-variable facilities. Terminate TLS and apply network
access/rate controls at the deployment gateway. Use `/readyz` as the orchestrator's
readiness probe; the Docker healthcheck tests only process liveness.

## Release checks

`firecast.release.assess_release` checks synthetic/operational mode, documented
coverage/grid/feature-availability/forecast-backtest/incident/calibration/current-
sensor evidence, test sample size/span, baseline skill and validated domain.
The minimum is 200 positives across at least two test years plus improved AP/Brier.
Those chosen minimums do not prove useful operational recall, calibration or alert
cost; review the full held-out results and intended response workflow.

Once a real operational evaluation record exists, build its manifest with:

```sh
uv run python -m firecast.release --evaluation evaluation.json \
  --model model.joblib --out release.json
```

The command exits 2 and writes `approved: false` when checks fail. There is no real
passing evaluation to feed it yet. Authenticating NASA downloads does not by itself
close the subsequent geolocation, QA, feature-availability, label, split and forecast
validation steps.

## Actually verified

The latest locked image built successfully (image SHA and status in
[production-status.json](production-status.json)). Creating its container exhausted
this workspace's disk capacity under Docker VFS copying; the latest container smoke
test therefore did not complete. Disposable task-owned images/cache were removed,
while all NASA raw data, models and reports were preserved. Retry on a host with
12–16 GB free disk. An earlier image did pass a non-root, read-only, tmpfs and dropped-
capabilities smoke test; that result is not claimed as validation of the latest image.

The latest service was tested directly in the locked Python environment with the
actual retrospective artifact and failed release manifest. See
[service-validation.json](service-validation.json): liveness returns 200, readiness
503, and a valid request to `/forecast` returns 503. This verifies that the real
research artifact cannot be silently published as an approved operational model.

The 49 passing focused tests include authenticated fixture inference, domain
withholding, future input rejection, unapproved/synthetic models and checksum
mismatch. Approved-path unit tests use explicitly artificial fixtures, not a real
operational artifact. Nothing has been published or deployed externally.

## Global-transfer extension status

The current [global model release](global-release.json) is also **not approved**.
Its actual refitted global/local neural artifact was tested directly against the
service; [global service validation](global-service-validation.json) records health
200, readiness 503 and refusal of a forecast request with the failed manifest.
The latest global extension has not been rebuilt/smoke-tested as a container in this
small disk-limited workspace. The prior container result is not claimed as a fresh
global-model container verification. Use sufficient disk and run the checked-in
Docker build/CI before deployment, after scientific release conditions are met.

The generic research artifact stores its sampled domains and temporal conflict
exclusions. Its Lebanese view withholds South/El Nabatieh-intersecting cells after
the exclusion start. Real-time forecast-source transfer, conditional observation
selection and the lack of operational validation remain explicit; research maps
must not be exposed as approved emergency warnings.
