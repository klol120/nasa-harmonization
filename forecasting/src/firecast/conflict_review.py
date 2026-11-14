"""Auditable historical conflict quarantine; never use these fields as predictors."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape,box,mapping
from shapely.ops import transform,unary_union
from .sources import cached_download


def acquire(config_path,out):
    config=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
    package=cached_download(config['source_api_url'],out/'hdx-package.json');metadata=json.loads(package.read_text())
    if not metadata.get('success'):raise ValueError('HDX catalogue request failed')
    record=metadata['result'];resource=next(x for x in record['resources'] if x.get('format')=='GeoJSON')
    archive=cached_download(resource['url'],out/'lbn_admin_boundaries.geojson.zip')
    with zipfile.ZipFile(archive) as z:boundaries=json.loads(z.read(config['source_layer']))
    selected=[f for f in boundaries['features'] if f['properties'].get('adm1_pcode') in config['governorate_pcodes']]
    if {f['properties']['adm1_pcode'] for f in selected}!=set(config['governorate_pcodes']):raise ValueError('Required southern governorates not found')
    report={'type':'FeatureCollection','features':selected,'source':config['source_url'],'source_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
      'source_layer':config['source_layer'],'license':record.get('license_title'),'license_url':record.get('license_url'),'provider':record.get('dataset_source')}
    (out/'southern_governorates.geojson').write_text(json.dumps(report,indent=2))
    return report


def load_geometry(path,config):
    collection=json.loads(Path(path).read_text());features=collection['features']
    geometry=unary_union([shape(f['geometry']) for f in features if f['properties'].get('adm1_pcode') in config['governorate_pcodes']])
    if geometry.is_empty or not geometry.is_valid:raise ValueError('Invalid southern-governorate exclusion geometry')
    if config.get('boundary_buffer_m',0):
        forward=Transformer.from_crs(4326,32636,always_xy=True).transform
        backward=Transformer.from_crs(32636,4326,always_xy=True).transform
        geometry=transform(backward,transform(forward,geometry).buffer(config['boundary_buffer_m']))
    return geometry


def excluded_cells(cells,geometry,grid_deg):
    result=set()
    for cid in cells.cell_id.unique():
        i,j=map(int,cid.split('_'));south=i*grid_deg-90;west=j*grid_deg-180
        if geometry.intersects(box(west,south,west+grid_deg,south+grid_deg)):result.add(cid)
    return result


def apply_quarantine(frame,config,geometry,grid_deg=.1):
    f=frame.copy();start=pd.Timestamp(config['start'])
    if start.tzinfo is None:raise ValueError('Conflict boundary requires explicit timezone')
    t=pd.to_datetime(f.prediction_time,utc=True);end=pd.to_datetime(f.window_end,utc=True)
    if (end<=t).any():raise ValueError('Invalid evaluation windows')
    cells=excluded_cells(f,geometry,grid_deg)
    overlap=end.gt(start)
    if config.get('end_exclusive'):overlap &= t.lt(pd.Timestamp(config['end_exclusive']))
    mask=f.region.eq('lebanon')&f.cell_id.isin(cells)&overlap
    f['y_before_conflict_quarantine']=f.y
    f['label_status_before_conflict_quarantine']=f.label_status
    f['conflict_excluded']=mask
    f['exclusion_policy_id']=np.where(mask,config['policy_id'],'')
    f['exclusion_reason']=np.where(mask,config['reason'],'')
    f['exclusion_source']=np.where(mask,config['source_url'],'')
    f.loc[mask,'y']=np.nan;f.loc[mask,'label_status']='excluded_conflict_region'
    return f


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=acquire(a.config,a.out);print(json.dumps({'governorates':[f['properties']['adm1_name'] for f in r['features']],'license':r['license'],'role':'historical label/evaluation quarantine only'}))

if __name__=='__main__':main()
