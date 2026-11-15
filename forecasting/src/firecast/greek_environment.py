"""NASA monthly NDVI and daily modeled soil-wetness acquisition for temporal models."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode

import numpy as np
import pandas as pd
from pyhdf.SD import SD, SDC

from .global_acquire import cached_json, fetch, save_subset, valid_subset, now
from .earthdata import data_link


def all_cells(root):
    root = Path(root)
    global_cells = pd.concat([pd.read_csv(p) for p in sorted((root / 'data/global-panel/static').glob('*-cells.csv'))])
    local = pd.read_csv(root / 'outputs/noaa20-real/cells.csv')
    return pd.concat([global_cells, local], ignore_index=True)[['region', 'cell_id', 'lat', 'lon']]


def cmg_indices(lat, lon):
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all() or (abs(lat) >= 90).any() or (abs(lon) >= 180).any():
        raise ValueError('Invalid CMG coordinate')
    return np.floor((90 - lat) / .05).astype(int), np.floor((lon + 180) / .05).astype(int)


def ndvi_good(ndvi, quality, reliability):
    # CMG bits 14-15 encode spatial contribution, NOT the tiled products' snow/shadow.
    # C6.1 guide Table 17: >=50% spatial contribution, reliable, clear land only.
    q = np.asarray(quality, np.uint16)
    return ((np.asarray(ndvi) >= -2000) & (np.asarray(ndvi) <= 10000)
            & ((q & 3) == 0) & (np.asarray(reliability) == 0)
            & ((q & (1 << 8)) == 0) & ((q & (1 << 10)) == 0)
            & (((q >> 11) & 7) == 1) & (((q >> 14) & 3) >= 2))


def acquire_ndvi(config, root, out, token_file):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cells = all_cells(root)
    cell_path = out / 'cells.csv'
    if cell_path.exists() and cell_path.read_text() != cells.to_csv(index=False):
        raise ValueError('NDVI cell order changed; use a new cache')
    cells.to_csv(cell_path, index=False)
    rows, cols = cmg_indices(cells.lat, cells.lon)
    token = Path(token_file).read_text().strip()
    months = sorted(set(m for start, end in config['ndvi_months'] for m in pd.date_range(start, end, freq='MS')))
    records = []
    for month in months:
        end = month + pd.offsets.MonthEnd(1)
        params = {'collection_concept_id': 'C2565788914-LPCLOUD', 'temporal': month.strftime('%Y-%m-%dT00:00:00Z') + ',' + end.strftime('%Y-%m-%dT23:59:59Z'), 'page_size': 20}
        payload = cached_json('https://cmr.earthdata.nasa.gov/search/granules.json?' + urlencode(params), out / 'catalog' / (month.strftime('%Y-%m') + '.json.gz'))
        entries = payload['feed']['entry']
        if not entries:
            records.append({'month': month.strftime('%Y-%m'), 'status': 'catalogue_missing'})
            continue
        entry = sorted(entries, key=lambda e: e['producer_granule_id'])[-1]
        name = entry['producer_granule_id']
        if not name.startswith('MOD13C2.A' + month.strftime('%Y%j') + '.061.'):
            raise ValueError('NASA NDVI catalogue returned the wrong composite month')
        path = out / 'subsets' / (name + '.npz')
        if not valid_subset(path):
            url = data_link(entry)
            if not url:
                raise ValueError('No NASA NDVI source URL')
            raw = fetch(url, token)
            # Linux memory-backed temporary file avoids a second on-disk global raster.
            # Other platforms retain the bounded disk-backed fallback.
            fd = os.memfd_create('nasa-mod13c2') if hasattr(os, 'memfd_create') else None
            handle = tempfile.NamedTemporaryFile(suffix='.hdf', dir=out) if fd is None else None
            try:
                if fd is not None:
                    with os.fdopen(os.dup(fd), 'wb') as stream:
                        stream.write(raw)
                    filename = '/proc/self/fd/' + str(fd)
                else:
                    handle.write(raw); handle.flush(); filename = handle.name
                hdf = SD(filename, SDC.READ)
                fields = ['CMG 0.05 Deg Monthly NDVI', 'CMG 0.05 Deg Monthly VI Quality', 'CMG 0.05 Deg Monthly pixel reliability']
                arrays = {}
                for field, key in zip(fields, ['NDVI', 'VI_Quality', 'pixel_reliability']):
                    dataset = hdf.select(field)
                    if dataset.info()[2] != [3600, 7200]:
                        raise ValueError('Unexpected NASA CMG shape')
                    arrays[key] = dataset[:][rows, cols]
                    dataset.endaccess()
                hdf.end()
            finally:
                if fd is not None: os.close(fd)
                if handle is not None: handle.close()
            save_subset(path, arrays, {'url': url, 'downloaded_at': now(), 'original_sha256': hashlib.sha256(raw).hexdigest(),
                        'original_bytes': len(raw), 'source_container_retained': False,
                        'retained_data': 'Exact raw NDVI, quality and reliability at recorded cell sample coordinates',
                        'product': 'MOD13C2.061', 'month': month.strftime('%Y-%m'),
                        'composite_start': month.isoformat(), 'composite_end_exclusive': (month + pd.offsets.MonthBegin(1)).isoformat(),
                        'cell_order_sha256': hashlib.sha256(cell_path.read_bytes()).hexdigest(),
                        'historical_version_availability_verified': False})
        with np.load(path) as arrays:
            good = ndvi_good(arrays['NDVI'], arrays['VI_Quality'], arrays['pixel_reliability'])
        records.append({'month': month.strftime('%Y-%m'), 'file': path.name, 'good_cells': int(good.sum()), 'cells': len(cells), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        print('NASA NDVI', month.strftime('%Y-%m'), 'good cells', int(good.sum()), flush=True)
    report = {'generated_at': now(), 'product': 'MOD13C2.061', 'records': records, 'months_requested': len(months), 'months_obtained': sum('file' in r for r in records), 'cell_count': len(cells), 'mode': 'retrospective', 'config': config}
    (out / 'ndvi-report.json').write_text(json.dumps(report, indent=2))
    return report


def acquire_soil(config, root, out):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    points = []
    for path, region in [(root / 'data/global-weather/weather.csv.gz', None), (root / 'data/nasa-lebanon/weather_historical.csv', 'lebanon')]:
        cols = ['weather_point_id', 'lat', 'lon'] + ([] if region else ['weather_region'])
        f = pd.read_csv(path, usecols=cols).drop_duplicates()
        if region:
            f['weather_region'] = region
        points.append(f)
    points = pd.concat(points).drop_duplicates(['weather_region', 'weather_point_id'])
    if config.get('soil_regions'):
        points = points[points.weather_region.isin(config['soil_regions'])]
    tasks = [(p, start, end) for p in points.itertuples() for start, end in config['soil_periods']]

    def one(task):
        p, start, end = task
        params = {'parameters': 'GWETROOT,GWETTOP', 'community': 'AG', 'latitude': float(p.lat), 'longitude': float(p.lon), 'start': start.replace('-', ''), 'end': end.replace('-', ''), 'format': 'JSON', 'time-standard': 'UTC'}
        url = 'https://power.larc.nasa.gov/api/temporal/daily/point?' + urlencode(params)
        payload = cached_json(url, out / 'raw' / (p.weather_region + '-' + p.weather_point_id + '-' + start + '-' + end + '.json.gz'))
        if payload['header']['time_standard'] != 'UTC':
            raise ValueError('Non-UTC NASA soil source')
        dates = pd.date_range(start, end)
        f = pd.DataFrame({'date': dates.strftime('%Y-%m-%d'), 'weather_region': p.weather_region, 'weather_point_id': p.weather_point_id})
        for key in ['GWETROOT', 'GWETTOP']:
            if payload['parameters'][key]['units'] != '1':
                raise ValueError('Unexpected soil wetness units')
            values = payload['properties']['parameter'][key]
            f[key] = [values.get(d.strftime('%Y%m%d'), np.nan) for d in dates]
            f.loc[~f[key].between(0, 1), key] = np.nan
        return f

    frames = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i, f in enumerate(pool.map(one, tasks), 1):
            frames.append(f)
            if i % 32 == 0 or i == len(tasks):
                print('NASA soil wetness requests', i, '/', len(tasks), flush=True)
    frame = pd.concat(frames, ignore_index=True)
    path = out / 'soil.csv.gz'
    frame.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
    report = {'generated_at': now(), 'point_days': len(frame), 'points': len(points), 'requests': len(tasks), 'missing_values': int(frame[['GWETROOT', 'GWETTOP']].isna().sum().sum()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mode': 'retrospective', 'source': 'NASA POWER MERRA-2 modeled relative soil wetness; not volumetric or direct fuel moisture', 'historical_availability_verified': False}
    (out / 'soil-report.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['soil', 'ndvi'])
    p.add_argument('--config', default='configs/greek-experiment.json')
    p.add_argument('--root', default='.')
    p.add_argument('--out', required=True)
    p.add_argument('--token-file')
    args = p.parse_args()
    config = json.loads(Path(args.config).read_text())
    result = acquire_soil(config, args.root, args.out) if args.operation == 'soil' else acquire_ndvi(config, args.root, args.out, args.token_file)
    print(json.dumps({k: v for k, v in result.items() if k not in {'records', 'config'}}))


if __name__ == '__main__':
    main()
