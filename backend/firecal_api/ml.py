"""Read training data and write model predictions.

Training data: the `ml_cell_month` view (current release of every region: per-cell values, region-wide
flags, cell attributes). For example with polars, which loads on this machine (pandas does not):

    import polars as pl
    df = pl.read_database_uri("select * from ml_cell_month where region_id = 'lebanon'", DATABASE_URL)

Predictions: call `save_run`, which records the run against the release it was trained on, so results
stay reproducible when a newer export replaces it. The API then serves them at
/regions/{region}/predictions.
"""

from collections.abc import Iterable
from datetime import date

import asyncpg

from . import contract as C


def _ym(v) -> date:
    return v if isinstance(v, date) else C.parse_ym(v)


async def save_run(
    conn: asyncpg.Connection,
    *,
    region: str,
    model_name: str,
    model_version: str,
    region_predictions: Iterable[tuple] = (),  # (ym, value, value_low, value_high)
    cell_predictions: Iterable[tuple] = (),  # (cell_id, ym, value, value_low, value_high)
    release_id: int | None = None,  # default: the region's current release
    target: str = "harmonized",
    params: dict | None = None,
    metrics: dict | None = None,
    artifact_uri: str | None = None,
    notes: str | None = None,
) -> int:
    """Store a model run and its predictions in one transaction. Returns the run_id.

    `ym` may be a 'YYYY-MM' string or a date. Values are in the target's units (VIIRS-equivalent
    fire-days for 'harmonized'); low/high may be None.
    """
    async with conn.transaction():
        if release_id is None:
            release_id = await conn.fetchval("select release_id from release where region_id = $1 and is_current", region)
            if release_id is None:
                raise ValueError(f"region {region!r} has no current release")
        run_id = await conn.fetchval(
            """insert into model_run (model_name, model_version, release_id, target, params, metrics, artifact_uri, notes)
               values ($1,$2,$3,$4,$5,$6,$7,$8) returning run_id""",
            model_name, model_version, release_id, target, params or {}, metrics or {}, artifact_uri, notes,
        )
        reg = [(run_id, _ym(ym), float(v), lo, hi) for ym, v, lo, hi in region_predictions]
        if reg:
            await conn.copy_records_to_table("prediction_region_month", records=reg)
        cells = [
            (run_id, C.cell_key(*C.parse_cell_id(cid)), _ym(ym), float(v), lo, hi)
            for cid, ym, v, lo, hi in cell_predictions
        ]
        if cells:
            await conn.copy_records_to_table("prediction_cell_month", records=cells)
    return run_id
