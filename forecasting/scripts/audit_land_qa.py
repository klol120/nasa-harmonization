"""Reproduce the native fire/land-QA audit without fitting any model.

Run from forecasting/: uv run python scripts/audit_land_qa.py --out outputs/land-qa-audit.json
"""
import argparse
import json
from pathlib import Path
import h5py
import numpy as np


def audit(root):
    root=Path(root);maps={p.stem.removeprefix('pixel-map-'):dict(np.load(p)) for p in (root/'outputs/noaa20-real').glob('pixel-map-*.npz')}
    old_bad=[];count=0
    for path in sorted((root/'data/gridded-noaa20/raw').glob('*.h5')):
        tile=next(t for t in maps if '.'+t+'.' in path.name);m=maps[tile]
        with h5py.File(path) as source:
            base=source['HDFEOS/GRIDS/VIIRS_Grid_Daily_Fire/Data Fields'];mask=base['FireMask'][:][m['rows'],m['cols']];qa=base['QA'][:][m['rows'],m['cols']]
            bad=np.flatnonzero(np.isin(mask,[7,8,9])&~np.isin(qa&3,[1,2])&m['eligible'])
            for i in bad:old_bad.append({'file':path.name,'date':source.attrs['RangeBeginningDate'].decode(),'cell_id':str(m['cell_ids'][i]),'mask':int(mask[i]),'qa':int(qa[i])})
        count+=1
    reports={'original_lebanon':{'files':count,'eligible_incompatible_fire_pixels':old_bad}}
    for folder in ['global-panel','global-panel-2026','lebanon-2026-masks']:
        native_fire=0;bad_pixels=0;count=0
        for path in (root/'data'/folder/'fire').glob('*.npz'):
            with np.load(path) as source:
                fire=np.isin(source['FireMask'],[7,8,9]);native_fire+=int(fire.sum());bad_pixels+=int((fire&~np.isin(source['QA']&3,[1,2])).sum())
            count+=1
        reports[folder]={'files':count,'sampled_native_fire_pixels':native_fire,'incompatible_land_qa_fire_pixels':bad_pixels}
    return reports


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--out',required=True);args=p.parse_args()
    result=audit(args.root);out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
