#!/usr/bin/env python3
"""Run with a system Python providing GDAL/numpy; retain exact NASA HLS crops.

Uses protected NASA COG range reads. Credentials stay in process memory. This is
an outcome-independent, pre-2018 static landscape sample, not current fuel state.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from osgeo import gdal, osr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from firecast.pretrained_encoder import hls_clear_pixels as clear_pixels


def acquire(cells_path, catalog_path, out, token_file):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cells = list(csv.DictReader(open(cells_path)))
    catalog = json.loads(Path(catalog_path).read_text())
    entries = sorted(catalog['feed']['entry'], key=lambda x: (float(x.get('cloud_cover', 100)), x['time_start']))
    token = Path(token_file).read_text().strip()
    gdal.UseExceptions()
    gdal.SetConfigOption('GDAL_HTTP_HEADERS', 'Authorization: Bearer ' + token)
    gdal.SetConfigOption('GDAL_DISABLE_READDIR_ON_OPEN', 'EMPTY_DIR')
    gdal.SetConfigOption('CPL_VSIL_CURL_ALLOWED_EXTENSIONS', '.tif')
    gdal.SetConfigOption('CPL_VSIL_CURL_USE_HEAD', 'NO')
    gdal.SetConfigOption('GDAL_HTTP_TIMEOUT', '45')
    gdal.SetConfigOption('GDAL_HTTP_MAX_RETRY', '2')
    gdal.SetConfigOption('GDAL_HTTP_RETRY_DELAY', '1')
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    failures, attempted = [], []
    for entry in entries:
        pending = [c for c in cells if not ((out / (c['cell_id'] + '.npz')).exists() and (out / (c['cell_id'] + '.json')).exists())]
        if not pending:
            break
        polygon = [list(map(float, ring.split())) for group in entry.get('polygons', []) for ring in group]
        if polygon:
            latitudes = [lat for ring in polygon for lat in ring[::2]]
            longitudes = [lon for ring in polygon for lon in ring[1::2]]
            if not any(min(latitudes) <= float(c['lat']) <= max(latitudes) and min(longitudes) <= float(c['lon']) <= max(longitudes) for c in pending):
                continue
        urls = {x['href'].split('.')[-2]: x['href'] for x in entry['links']
                if x.get('href', '').startswith('https://data.lpdaac.earthdatacloud.nasa.gov/') and x['href'].endswith('.tif')}
        if not all(b in urls for b in ['Fmask', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07']):
            continue
        try:
            mask = gdal.Open('/vsicurl/' + urls['Fmask'])
            srs = osr.SpatialReference(wkt=mask.GetProjection())
            srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            transform = osr.CoordinateTransformation(wgs, srs)
            gt = mask.GetGeoTransform()
            proposals = []
            for cell in pending:
                x, y, _ = transform.TransformPoint(float(cell['lon']), float(cell['lat']))
                col, row = int((x - gt[0]) / gt[1]) - 16, int((y - gt[3]) / gt[5]) - 16
                if col < 0 or row < 0 or col + 32 > mask.RasterXSize or row + 32 > mask.RasterYSize:
                    continue
                qa = mask.ReadAsArray(col, row, 32, 32)
                if clear_pixels(qa).mean() >= .95:
                    proposals.append((cell, col, row, qa))
            if not proposals:
                continue
            bands = [gdal.Open('/vsicurl/' + urls[b]) for b in ['B02', 'B03', 'B04', 'B05', 'B06', 'B07']]
            count = 0
            for cell, col, row, qa in proposals:
                reflectance = np.stack([b.ReadAsArray(col, row, 32, 32) for b in bands]).astype(np.int16)
                good = clear_pixels(qa) & ((reflectance >= -1000) & (reflectance <= 10000)).all(axis=0)
                if good.mean() < .95:
                    continue
                path = out / (cell['cell_id'] + '.npz')
                np.savez_compressed(path, reflectance=reflectance, Fmask=qa, good=good)
                metadata = {'cell_id': cell['cell_id'], 'latitude': float(cell['lat']), 'longitude': float(cell['lon']),
                            'granule': entry['title'], 'observation_time': entry['time_start'],
                            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'catalog_updated_at': entry.get('updated'),
                            'product': 'HLSL30.020', 'urls': urls, 'bands': ['B02', 'B03', 'B04', 'B05', 'B06', 'B07'],
                            'raw_units': 'scaled reflectance, scale factor 0.0001', 'window': [col, row, 32, 32],
                            'pixel_metres': 30, 'good_fraction': float(good.mean()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'source_containers_retained': False, 'retained': 'Exact native six-band crops, Fmask and derived good-pixel mask',
                            'historical_availability_proven': False, 'availability_assumption': 'pre-2018 static landscape; reprocessing availability unverified'}
                path.with_suffix('.json').write_text(json.dumps(metadata, indent=2))
                count += 1
            attempted.append({'granule': entry['title'], 'retained_cells': count})
            print(entry['title'], 'retained', count, 'remaining', len(pending) - count, flush=True)
        except Exception as exc:
            # GDAL errors may contain request context; retain only a safe class.
            failures.append({'granule': entry['title'], 'error_type': type(exc).__name__})
    records = [json.loads(p.read_text()) for p in sorted(out.glob('*.json')) if p.name != 'manifest.json']
    report = {'cells_requested': len(cells), 'cells_obtained': len(records), 'records': records, 'attempted': attempted,
              'failures': failures, 'source_catalog_sha256': hashlib.sha256(Path(catalog_path).read_bytes()).hexdigest(),
              'selection': '2017 June-October, catalogue cloud ordering; no fire outcomes used',
              'limitations': ['One 960m landscape crop per roughly 10km cell', 'Static 2017 proxy becomes stale',
                             'Source versions processed after original acquisition; retrospective availability assumption']}
    (out / 'manifest.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'cells_requested': len(cells), 'cells_obtained': len(records), 'failed_granules': len(failures)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cells', required=True)
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--token-file', required=True)
    args = parser.parse_args()
    acquire(args.cells, args.catalog, args.out, args.token_file)
