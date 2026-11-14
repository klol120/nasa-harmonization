"""Acquire sealed 2026 NASA mask subsets; no confirmation model metrics are computed."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import shutil
import h5py
import numpy as np
import pandas as pd
from .global_acquire import discover_tile,fetch,science_meta,save_subset,valid_subset,now


def acquire(config_path,maps_dir,out,token_file):
    design=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
    start,end=design['fresh_lebanon_confirmation'];config=dict(design,start=start,end_exclusive=end)
    token=Path(token_file).read_text().strip();reports=[]
    for path in sorted(Path(maps_dir).glob('pixel-map-*.npz')):
        tile=path.stem.removeprefix('pixel-map-');m=dict(np.load(path));records=discover_tile(tile,config,out)
        def one(item):
            target=out/'fire'/(item['name']+'.npz')
            if valid_subset(target):return None
            if shutil.disk_usage(out).free<design['min_free_bytes']:raise RuntimeError('Disk reserve reached')
            raw=fetch(item['url'],token)
            with h5py.File(io.BytesIO(raw)) as f:
                if f.attrs.get('ShortName',b'').decode()!=design['product']:raise ValueError('Wrong confirmation product')
                base=f['HDFEOS/GRIDS/VIIRS_Grid_Daily_Fire/Data Fields'];mask=base['FireMask'][:][m['rows'],m['cols']];qa=base['QA'][:][m['rows'],m['cols']]
                if not np.isin(mask,np.arange(10)).all():raise ValueError('Unknown daily mask class')
                day=f.attrs['RangeBeginningDate'].decode()
                if day!=item['date']:raise ValueError('Wrong confirmation date')
            save_subset(target,{'FireMask':mask,'QA':qa},dict(science_meta(item['url'],raw),date=day,tile=tile,product='VJ114A1.002',pixel_map_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),role='sealed confirmation source arrays; no model metrics inspected'))
            return None
        failures=[]
        def safe(item):
            try:one(item);return None
            except Exception as e:return {'name':item['name'],'error_type':type(e).__name__}
        with ThreadPoolExecutor(max_workers=2) as pool:
            for i,error in enumerate(pool.map(safe,records),1):
                if error:failures.append(error)
                if i%50==0:print('Sealed source subsets',tile,i,'of',len(records),'failed',len(failures),flush=True)
        reports.append({'tile':tile,'catalogued':len(records),'failures':failures})
    report={'generated_at':now(),'complete':all(not r['failures'] for r in reports),'period':[start,end],'tiles':reports,'model_evaluation_performed':False}
    (out/'archive-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'complete':report['complete'],'role':'confirmation source acquisition only'}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--maps',required=True);p.add_argument('--out',required=True);p.add_argument('--token-file',required=True);a=p.parse_args();acquire(a.config,a.maps,a.out,a.token_file)

if __name__=='__main__':main()
