"""Shared NASA temporal tensors, past-only vegetation joins and auditable exclusions."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark_global import load_part
from .data import km_distance
from .global_data import FEATURES, count_pixels, quality_labels, add_features, join_weather, split_masks
from .global_weather import history_features
from .greek_environment import ndvi_good

DYNAMIC = ['temperature_c', 'T2M_MAX', 'humidity_pct', 'precip_mm', 'wind_u_ms', 'wind_v_ms', 'vpd_kpa', 'GWETROOT', 'GWETTOP']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def past_indices(times, dates, days=10, lag=3):
    if days < 1 or lag < 0 or int(days) != days or int(lag) != lag:
        raise ValueError('Invalid history length or lag')
    times = np.asarray(times, dtype='datetime64[D]')
    dates = np.asarray(dates, dtype='datetime64[D]')
    if len(dates) == 0 or (np.diff(dates).astype(int) <= 0).any():
        raise ValueError('History dates must be unique and increasing')
    wanted = times[:, None] - np.arange(lag + days, lag, -1).astype('timedelta64[D]')
    indices = np.searchsorted(dates, wanted)
    valid = (indices < len(dates)).all(axis=1)
    indices = np.minimum(indices, len(dates) - 1)
    valid &= (dates[indices] == wanted).all(axis=1)
    return indices, valid


def ndvi_asof(times, cell_indices, months, values, lag_days=16, max_age=120):
    """Only use completed composites after a declared conservative lag; never backfill."""
    times = np.asarray(times, dtype='datetime64[D]')
    months = pd.DatetimeIndex(months)
    end = (months + pd.offsets.MonthBegin(1)).to_numpy(dtype='datetime64[D]')
    available = end + np.timedelta64(lag_days, 'D')
    result = np.full((len(times), 4), np.nan, np.float32)
    for i, (when, cell) in enumerate(zip(times, cell_indices)):
        candidates = np.flatnonzero((available <= when) & ((when - end).astype(int) <= max_age) & np.isfinite(values[:, cell]))
        if len(candidates):
            j = candidates[-1]
            result[i, :2] = values[j, cell], (when - end[j]).astype(int)
            # An explicit indicator distinguishes missing prior NDVI from zero change.
            result[i, 2] = values[j, cell] - values[candidates[-2], cell] if len(candidates) > 1 else 0.
            result[i, 3] = float(len(candidates) > 1)
    return result


class HistoryStore:
    def __init__(self, root, config, include_known=False):
        root = Path(root)
        self.config = config
        raw = ['weather_point_id', 'lat', 'lon', 'date', 'T2M', 'T2M_MAX', 'RH2M', 'PRECTOTCORR', 'WS10M', 'WD10M']
        global_weather = pd.read_csv(root / 'data/global-weather/weather.csv.gz', usecols=raw + ['weather_region'])
        local = pd.read_csv(root / 'data/nasa-lebanon/weather_historical.csv', usecols=raw)
        local['weather_region'] = 'lebanon'
        weather = pd.concat([global_weather, local], ignore_index=True)
        if include_known:
            for path in [root / 'data/global-2026-weather/weather.csv.gz', root / 'data/lebanon-2026-weather/weather.csv.gz']:
                extra = pd.read_csv(path, usecols=raw + ['weather_region'])
                weather = pd.concat([weather, extra], ignore_index=True)
            # Preserve the original cached source if overlapping December dates recur.
            weather = weather.drop_duplicates(['weather_region', 'weather_point_id', 'date'], keep='first')
        # Features use exact recorded POWER values and retain their modeled source.
        weather = history_features(weather, config['history_lag_days'])
        soil_path = root / 'data/greek-soil/soil.csv.gz'
        soil_report = json.loads((soil_path.parent / 'soil-report.json').read_text())
        if sha(soil_path) != soil_report['sha256']:
            raise ValueError('Soil archive checksum mismatch')
        soil = pd.read_csv(soil_path)
        if include_known:
            extra_path = root / 'data/greek-soil-known/soil.csv.gz'
            extra_report = json.loads((extra_path.parent / 'soil-report.json').read_text())
            if sha(extra_path) != extra_report['sha256']:
                raise ValueError('Known-benchmark soil checksum mismatch')
            soil = pd.concat([soil, pd.read_csv(extra_path)], ignore_index=True)
        weather = weather.merge(soil, on=['weather_region', 'weather_point_id', 'date'], how='left', validate='one_to_one')
        self.set_weather(weather)
        ndvi_root = root / 'data/greek-ndvi'
        cells = pd.read_csv(ndvi_root / 'cells.csv')
        self.ndvi_cells = {(r.region, r.cell_id): i for i, r in enumerate(cells.itertuples())}
        reports = [(ndvi_root, json.loads((ndvi_root / 'ndvi-report.json').read_text()))]
        if include_known:
            extra_root = root / 'data/greek-ndvi-known'
            reports.append((extra_root, json.loads((extra_root / 'ndvi-report.json').read_text())))
        months, values = [], []
        for source_root, report in reports:
            for record in report['records']:
                if 'file' not in record:
                    continue
                path = source_root / 'subsets' / record['file']
                if sha(path) != record['sha256']:
                    raise ValueError('NDVI subset checksum mismatch')
                source_meta = json.loads(path.with_suffix('.npz.manifest.json').read_text())
                if source_meta['cell_order_sha256'] != sha(ndvi_root / 'cells.csv'):
                    raise ValueError('NDVI source coordinate order differs from current cells')
                with np.load(path) as a:
                    v = a['NDVI'].astype(np.float32) * .0001
                    v[~ndvi_good(a['NDVI'], a['VI_Quality'], a['pixel_reliability'])] = np.nan
                months.append(record['month'] + '-01')
                values.append(v)
        if len(set(months)) != len(months):
            raise ValueError('Overlapping NDVI benchmark sources')
        order = np.argsort(months)
        self.ndvi_months = np.asarray(months)[order].tolist()
        self.ndvi_values = np.stack(values)[order]

    def set_weather(self, weather):
        self.weather = weather
        self.points = {region: g[['weather_point_id', 'lat', 'lon']].drop_duplicates() for region, g in weather.groupby('weather_region')}
        self.series = {}
        for key, g in weather.groupby(['weather_region', 'weather_point_id']):
            g = g.sort_values('date')
            if g.date.duplicated().any():
                raise ValueError('Duplicate NASA weather point-day')
            self.series[key] = (g.date.to_numpy(dtype='datetime64[D]'), g[DYNAMIC].to_numpy(np.float32))

    def make(self, frame, keep_unqualified=False):
        frame = frame.reset_index(drop=True)
        n = len(frame)
        sequence = np.full((n, self.config['history_days'], len(DYNAMIC)), np.nan, np.float32)
        missing_history = np.zeros(n, bool)
        if 'lon' not in frame:
            # Existing split contract exports latitude but not longitude; immutable cell coordinates supply it.
            raise ValueError('Temporal frames require actual cell longitude')
        for (region, cell), indices in frame.groupby(['region', 'cell_id'], observed=True).indices.items():
            points = self.points[str(region)]
            row = frame.iloc[indices[0]]
            point = points.loc[km_distance(points.lat, points.lon, row.lat, row.lon).idxmin()].weather_point_id
            dates, values = self.series[(str(region), point)]
            selected, valid = past_indices(frame.prediction_time.iloc[indices].to_numpy(dtype='datetime64[D]'), dates, self.config['history_days'], self.config['history_lag_days'])
            sequence[indices] = values[selected]
            missing_history[indices] = ~valid
        times = frame.prediction_time.to_numpy(dtype='datetime64[D]')
        indices = np.asarray([self.ndvi_cells[(str(r), str(c))] for r, c in zip(frame.region, frame.cell_id)])
        ndvi = ndvi_asof(times, indices, self.ndvi_months, self.ndvi_values, self.config['ndvi_lag_days_after_composite_end'], self.config['ndvi_max_age_days'])
        static = np.column_stack([frame[FEATURES].to_numpy(np.float32), ndvi])
        valid = ~missing_history & np.isfinite(sequence).all(axis=(1, 2)) & np.isfinite(static).all(axis=1)
        labelled = 'y' in frame
        report = {'input_windows': n, 'label_qualified_windows': n if labelled else None, 'qualified_positive_windows': int(frame.y.sum()) if labelled else None, 'missing_history': int((missing_history | ~np.isfinite(sequence).all(axis=(1, 2))).sum()), 'missing_past_ndvi': int((~np.isfinite(ndvi).all(axis=1)).sum()), 'feature_qualified_windows': int(valid.sum()), 'feature_qualified_positive_windows': int(frame.y[valid].sum()) if labelled else None, 'excluded_positive_windows': int(frame.y[~valid].sum()) if labelled else None}
        use = np.ones(n, bool) if keep_unqualified else valid
        result = {'sequence': sequence[use], 'static': static[use],
                  'time': times[use].astype('int64'), 'region': np.asarray(frame.region.astype(str), dtype='U32')[use], 'cell_id': np.asarray(frame.cell_id.astype(str), dtype='U32')[use]}
        if labelled: result['y'] = frame.y.to_numpy(np.int8)[use]
        return result, report


def greek_development_frame(root, old_config):
    root = Path(root)
    archive = root / 'data/greek-daily-panel'
    if not json.loads((archive / 'archive-report.json').read_text())['complete']:
        raise ValueError('Greek daily archive is incomplete')
    cells = pd.read_csv(archive / 'static/greece-cells.csv')
    maps = {p.stem: dict(np.load(p)) for p in (archive / 'maps').glob('greece-*.npz')}
    counts = []
    for path in sorted((archive / 'fire').glob('*.npz')):
        meta = json.loads(path.with_suffix('.npz.manifest.json').read_text())
        if 'greece' not in meta['site_order'] or meta['date'] >= '2023-01-01':
            continue
        if sha(path) != meta['subset_sha256']:
            raise ValueError('Greek fire subset checksum mismatch')
        with np.load(path) as a:
            use = a['site_id'] == 'greece'
            counts.append(count_pixels(a['FireMask'][use], a['QA'][use], maps['greece-' + meta['tile']], 'greece', meta['date']))
    daily = pd.concat(counts).groupby(['region', 'cell_id', 'prediction_time']).sum().reset_index()
    dates = pd.date_range('2018-01-01', '2022-12-31', tz='UTC', freq='D')
    f = cells.merge(pd.DataFrame({'prediction_time': dates}), how='cross').merge(daily, on=['region', 'cell_id', 'prediction_time'], how='left', validate='one_to_one')
    f = quality_labels(f, old_config)
    f['window_end'] = f.prediction_time + pd.Timedelta(days=1)
    weather = pd.read_csv(root / 'data/global-weather/weather.csv.gz')
    f = join_weather(f, weather[weather.weather_region.eq('greece')])
    f['conflict_excluded'] = False
    f['geographic_holdout'] = False
    return add_features(f)


def match_greek_cells(store, root, config):
    """Choose Greek cells from environmental development data, never fire labels."""
    from scipy.spatial import cKDTree
    root = Path(root)
    w = store.weather
    use = w.weather_region.isin(['greece', 'lebanon']) & w.date.ge('2018-01-01') & w.date.lt('2021-01-01')
    summer = w.loc[use & pd.to_datetime(w.date).dt.month.isin([6, 7, 8])]
    seasonal = summer.groupby(['weather_region', 'weather_point_id']).agg(summer_temperature_c=('temperature_c', 'mean'), summer_rain_mm=('precip_mm', 'sum'))
    seasonal['summer_rain_mm'] /= 3
    tables = {}
    for region, path in [('greece', root / 'data/global-panel/static/greece-cells.csv'), ('lebanon', root / 'outputs/noaa20-real/cells.csv')]:
        cells = pd.read_csv(path)
        points = store.points[region]
        values = []
        for row in cells.itertuples():
            point = points.loc[km_distance(points.lat, points.lon, row.lat, row.lon).idxmin()].weather_point_id
            season = seasonal.loc[(region, point)]
            values.append([season.summer_temperature_c, season.summer_rain_mm, row.elevation_m, row.slope_deg, row.vegetation_fraction])
        tables[region] = (cells.cell_id.to_numpy(), np.asarray(values))
    local = tables['lebanon'][1]
    scale = np.maximum(np.std(local, axis=0), [1., 10., 100., 1., .1])
    distance, _ = cKDTree(local / scale).query(tables['greece'][1] / scale)
    count = max(1, int(np.ceil(len(distance) * config['greek_matching_fraction'])))
    order = np.argsort(distance, kind='stable')[:count]
    return {'selected_cells': tables['greece'][0][order].tolist(), 'all_greek_cells': len(distance),
            'selected_count': count, 'features': config['greek_matching_features'], 'scale': scale.tolist(),
            'selected_distance_range': [float(distance[order].min()), float(distance[order].max())],
            'selection_period': ['2018-01-01', '2021-01-01'], 'fire_labels_used_for_matching': False}


def prepare(root, config_path, out):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(config_path).read_text())
    data = root / 'outputs/global-transfer-data'
    manifest = json.loads((data / 'dataset-manifest.json').read_text())
    store = HistoryStore(root, config)
    matching = match_greek_cells(store, root, config)
    greek = greek_development_frame(root, manifest['config'])
    greek = greek[greek.cell_id.isin(matching['selected_cells'])].copy()
    coords = pd.read_csv(root / 'data/greek-ndvi/cells.csv')[['region', 'cell_id', 'lon']]
    parts, reports = {}, {}
    for domain in ['global', 'lebanon', 'greek']:
        for stage in ['train', 'calibration', 'validation']:
            if domain == 'greek':
                masks = split_masks(greek, dict(manifest['config'], embargo_days=config['embargo_days']), 'global')
                f = greek[masks[stage] & greek.y.notna()].copy()
            else:
                f = load_part(data, domain + '-' + stage, manifest)
                a, b, c = map(pd.Timestamp, [config['training_end'], config['calibration_end'], config['validation_end']])
                gap = pd.Timedelta(days=config['embargo_days'])
                before, after = {'train': (None, a), 'calibration': (a, b), 'validation': (b, c)}[stage]
                f = f[(f.window_end < after - gap) & (True if before is None else f.prediction_time >= before + gap)].copy()
                f = f.merge(coords, on=['region', 'cell_id'], validate='many_to_one')
            tensors, report = store.make(f)
            name = domain + '-' + stage
            path = out / (name + '.npz')
            np.savez_compressed(path, **tensors)
            reports[name] = dict(report, sha256=sha(path))
            print('Prepared temporal part', name, reports[name], flush=True)
    report = {'mode': 'retrospective', 'config': config, 'greek_matching': matching, 'parts': reports, 'dynamic_features': DYNAMIC, 'static_features': FEATURES + ['ndvi', 'ndvi_age_days', 'ndvi_change_previous_valid', 'ndvi_prior_available'], 'source_manifest_sha256': sha(data / 'dataset-manifest.json'), 'greek_archive_sha256': sha(root / 'data/greek-daily-panel/archive-report.json'), 'soil_sha256': sha(root / 'data/greek-soil/soil.csv.gz'), 'ndvi_manifest_sha256': sha(root / 'data/greek-ndvi/ndvi-report.json'), 'source_config_sha256': sha(config_path), 'historical_availability_verified': False}
    (out / 'manifest.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--config', default='configs/greek-experiment.json')
    p.add_argument('--out', default='outputs/greek-temporal-data')
    a = p.parse_args()
    prepare(Path(a.root).resolve(), Path(a.config).resolve(), a.out)


if __name__ == '__main__':
    main()
