"""Provision the scheduled outlook worker and start an immediate deployment check."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


def az(*args: str, sensitive: bool = False):
    result = subprocess.run(["az", *args, "--only-show-errors", "-o", "json"], capture_output=True, text=True)
    if result.returncode:
        action = " ".join(args[:3])
        raise RuntimeError(f"{action} failed" + ("" if sensitive else f": {result.stderr.strip()}"))
    return json.loads(result.stdout) if result.stdout.strip() else None


def deployment_job(group: str, api: str, job: str, image: str) -> str:
    app = az("containerapp", "show", "-g", group, "-n", api, "--query", """{
        location:location, environment:properties.managedEnvironmentId, registries:properties.configuration.registries,
        database:properties.template.containers[0].env[?name=='DATABASE_URL'].secretRef | [0]}""")
    registry = next(r for r in app["registries"] if r["server"] == image.split("/", 1)[0])
    secret_names = [app["database"], registry.get("passwordSecretRef")]
    # Keep credentials out of the command line and deployment logs.
    secrets = [
        {"name": name, "value": az("containerapp", "secret", "show", "-g", group, "-n", api,
                                    "--secret-name", name, "--query", "value", sensitive=True)}
        for name in dict.fromkeys(filter(None, secret_names))
    ]
    if not app["database"] or any(not s["value"] for s in secrets):
        raise RuntimeError("The API needs a readable database secret and registry credentials for the outlook job.")
    spec = {
        "location": app["location"],
        "properties": {
            "environmentId": app["environment"],
            "configuration": {
                "triggerType": "Schedule",
                "replicaTimeout": 1200,
                "replicaRetryLimit": 2,
                # Azure wakes daily; the worker enforces a 15-day interval between successful checks.
                "scheduleTriggerConfig": {"cronExpression": "0 5 * * *", "parallelism": 1, "replicaCompletionCount": 1},
                "registries": [{key: registry[key] for key in ("server", "username", "passwordSecretRef")}],
                "secrets": secrets,
            },
            "template": {"containers": [{
                "name": "outlook",
                "image": image,
                "command": ["python", "-m", "firecal_api.outlook_job"],
                "resources": {"cpu": 2, "memory": "4Gi"},
                "env": [
                    {"name": "DATABASE_URL", "secretRef": app["database"]},
                    {"name": "OMP_NUM_THREADS", "value": "2"},
                    {"name": "OPENBLAS_NUM_THREADS", "value": "1"},
                ],
            }]},
        },
    }
    jobs = az("containerapp", "job", "list", "-g", group, "--query", "[].name")
    operation = "update" if job in jobs else "create"
    with TemporaryDirectory(prefix="phoenical-outlook-job-") as folder:
        config = Path(folder) / "job.yaml"  # JSON is also valid YAML.
        config.touch(mode=0o600)
        config.write_text(json.dumps(spec), encoding="utf-8")
        az("containerapp", "job", operation, "-g", group, "-n", job, "--yaml", str(config),
           "--query", "name", sensitive=True)
        execution_template = spec["properties"]["template"]
        execution_template["containers"][0]["args"] = ["--on-deploy"]
        execution = Path(folder) / "execution.yaml"
        execution.write_text(json.dumps(execution_template), encoding="utf-8")
        name = az("containerapp", "job", "start", "-g", group, "-n", job, "--yaml", str(execution), "--query", "name")
    if not name:
        raise RuntimeError("Azure did not return the first outlook execution's name.")
    return name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("group", "api", "job", "image"):
        parser.add_argument(field)
    args = parser.parse_args()
    print(deployment_job(args.group, args.api, args.job, args.image))


if __name__ == "__main__":
    main()
