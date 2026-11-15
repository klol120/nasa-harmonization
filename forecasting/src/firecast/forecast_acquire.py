"""Range-read regional NASA GEOS forecasts; retain scientific subsets and provenance."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import fsspec
import h5py
import h5netcdf
import numpy as np
import pandas as pd

COLLECTIONS={'slv':['T2M','QV2M','PS','U10M','V10M'],'flx':['PRECTOT'],'rad':['CLDTOT']}

def subset_hour(issue,midpoint,collection,bbox,out):
    issue=pd.Timestamp(issue);midpoint=pd.Timestamp(midpoint);out=Path(out)
    if issue.tzinfo is None or midpoint.tzinfo is None or midpoint<=issue:raise ValueError('Explicit UTC issue and future valid midpoint required')
    label=f'GEOS.fp.fcst.tavg1_2d_{collection}_Nx.{issue:%Y%m%d_%H}+{midpoint:%Y%m%d_%H%M}.V01.nc4'
    path=out/'subsets'/label;manifest_path=path.with_suffix(path.suffix+'.manifest.json')
    if path.exists() and manifest_path.exists():
        m=json.loads(manifest_path.read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=m['sha256']:raise ValueError('Subset checksum mismatch')
        return m
    source='https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/forecast/'+f'Y{issue:%Y}/M{issue:%m}/D{issue:%d}/H{issue:%H}/'+label.replace('+','%2B')
    fs=fsspec.filesystem('https',client_kwargs={'trust_env':True},block_size=262144)
    arrays={};attrs={}
    with fs.open(source,'rb',cache_type='blockcache') as remote:
        with h5py.File(remote,'r') as f:
            lat=f['lat'][:];lon=f['lon'][:];west,south,east,north=bbox
            ri=np.flatnonzero((lat>=south-.25)&(lat<=north+.25));ci=np.flatnonzero((lon>=west-.3125)&(lon<=east+.3125))
            if not len(ri) or not len(ci):raise ValueError('No forecast region')
            rows=slice(ri[0],ri[-1]+1);cols=slice(ci[0],ci[-1]+1)
            for key in COLLECTIONS[collection]:
                arrays[key]=f[key][:,rows,cols]
                attrs[key]={a:v for a,v in f[key].attrs.items() if a in ['units','long_name','standard_name','missing_value','scale_factor','add_offset']}
            times=f['time'][:];time_attrs={a:v for a,v in f['time'].attrs.items() if a in ['units','begin_date','begin_time','time_increment','long_name']}
            latitude=lat[rows];longitude=lon[cols]
    info=fs.info(source);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.part')
    with h5netcdf.File(temp,'w') as f:
        f.dimensions={'time':len(times),'lat':len(latitude),'lon':len(longitude)}
        for name,values,dimensions in [('time',times,('time',)),('lat',latitude,('lat',)),('lon',longitude,('lon',))]:
            var=f.create_variable(name,dimensions,dtype=values.dtype);var[:]=values
            var.attrs.update(time_attrs if name=='time' else {'units':'degrees_north' if name=='lat' else 'degrees_east'})
        for name,values in arrays.items():
            var=f.create_variable(name,('time','lat','lon'),dtype=values.dtype,compression='gzip');var[:]=values;var.attrs.update(attrs[name])
        f.attrs.update({'source_url':source,'processing':'Geographic subset only; original physical units preserved'})
    temp.replace(path)
    manifest={'url':source,'source_size_bytes':info.get('size'),'source_etag':info.get('ETag'),
      'downloaded_at':datetime.now(timezone.utc).isoformat(),'issue_time':issue.isoformat(),'valid_midpoint':midpoint.isoformat(),
      'subset_bbox':bbox,'variables':COLLECTIONS[collection],'derived_geographic_subset':True,'path':str(path),
      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
      'provenance_note':'Hash covers retained scientific subset; original immutable source URL and available remote ETag identify source, not a computed whole-source checksum'}
    manifest_path.write_text(json.dumps(manifest,indent=2))
    return manifest

def acquire_forecast(issue,prediction_time,horizon,bbox,out):
    start=pd.Timestamp(prediction_time);tasks=[(start+pd.Timedelta(hours=h,minutes=30),c) for h in range(horizon) for c in COLLECTIONS]
    successes=[];failures=[]
    def run(task):
        midpoint,c=task
        try:return subset_hour(issue,midpoint,c,bbox,out),None
        except Exception as exc:return None,{'collection':c,'midpoint':str(midpoint),'error':type(exc).__name__,'status':getattr(exc,'code',None)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for success,error in pool.map(run,tasks):
            if error:failures.append(error)
            else:successes.append(success)
            if (len(successes)+len(failures))%6==0:print('Forecast subsets',len(successes),'failed',len(failures),'of',len(tasks),flush=True)
    report={'issue_time':issue,'prediction_time':prediction_time,'horizon_hours':horizon,'complete':len(successes)==len(tasks),'subsets':successes,'failures':failures,
      'purpose':'Real issued-forecast inference inputs; not multi-year historical forecast validation'}
    Path(out).mkdir(parents=True,exist_ok=True);(Path(out)/'forecast-report.json').write_text(json.dumps(report,indent=2))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--issue',required=True);p.add_argument('--prediction-time',required=True);p.add_argument('--out',required=True);p.add_argument('--horizon',type=int,default=24);a=p.parse_args()
    r=acquire_forecast(a.issue,a.prediction_time,a.horizon,[35,33,36.7,34.75],a.out);print(json.dumps({'complete':r['complete'],'failures':len(r['failures'])}))

if __name__=='__main__':main()
