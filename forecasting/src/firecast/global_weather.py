"""NASA-only POWER weather for sampled global panels and sealed Lebanese 2026 data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
import numpy as np
import pandas as pd
from .global_acquire import cached_json,now


def history_features(frame,lag=3):
    if not isinstance(lag,int) or lag<0:raise ValueError('History lag must be a nonnegative whole number of days')
    f=frame.sort_values(['weather_point_id','date']).copy()
    output=[]
    for _,g in f.groupby('weather_point_id',sort=False):
        g=g.copy();dates=pd.to_datetime(g.date,utc=True)
        if dates.duplicated().any() or not dates.diff().dropna().eq(pd.Timedelta(days=1)).all():raise ValueError('Weather history must be unique and daily contiguous')
        g['rain7_mm']=g.PRECTOTCORR.shift(lag+1).rolling(7,min_periods=7).sum()
        g['rain30_mm']=g.PRECTOTCORR.shift(lag+1).rolling(30,min_periods=30).sum()
        g['temperature7_c']=g.T2M.shift(lag+1).rolling(7,min_periods=7).mean()
        angle=np.radians(g.WD10M);g['wind_u_ms']=-g.WS10M*np.sin(angle);g['wind_v_ms']=-g.WS10M*np.cos(angle)
        g['temperature_c']=g.T2M;g['humidity_pct']=g.RH2M;g['precip_mm']=g.PRECTOTCORR
        g['vpd_kpa']=.6108*np.exp(17.27*g.T2M/(g.T2M+237.3))*(1-g.RH2M/100)
        output.append(g)
    return pd.concat(output,ignore_index=True)


def weather_point(lat,lon,start,end,region,config,out):
    lat=float(lat);lon=float(lon);point=f'{lat}_{lon}'
    params={'parameters':','.join(config['weather_parameters']),'community':'AG','latitude':lat,'longitude':lon,'start':start,'end':end,'format':'JSON','time-standard':'UTC'}
    payload=cached_json('https://power.larc.nasa.gov/api/temporal/daily/point?'+urlencode(params),Path(out)/'raw'/f'power-{point}-{start}-{end}.json.gz')
    if payload['header']['time_standard']!='UTC':raise ValueError('POWER returned non-UTC data')
    fill=payload['header']['fill_value'];data=payload['properties']['parameter'];dates=pd.date_range(start,end,freq='D')
    f=pd.DataFrame({'date':dates.strftime('%Y-%m-%d'),'weather_point_id':point,'lat':lat,'lon':lon,'weather_region':region})
    for key in config['weather_parameters']:
        f[key]=[data[key].get(t.strftime('%Y%m%d'),fill) for t in dates];f.loc[f[key].eq(fill),key]=np.nan
    if (f.RH2M.dropna().lt(0)|f.RH2M.dropna().gt(100)).any() or f.PRECTOTCORR.dropna().lt(0).any():raise ValueError('Invalid POWER physical range')
    return f


def acquire(config_path,out,lebanon_data=None):
    config=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True);tasks=[]
    if lebanon_data:
        old=pd.read_csv(Path(lebanon_data)/'weather_historical.csv',usecols=['weather_point_id','lat','lon']).drop_duplicates()
        tasks=[(p.lat,p.lon,config.get('weather_start','20251201'),config.get('weather_end','20261031'),'lebanon') for p in old.itertuples()]
    else:
        for site in config['sites']:
            for dy in [.25,.75,1.25,1.75]:
                for dx in [.25,.75,1.25,1.75]:tasks.append((site['south']+dy,site['west']+dx,config.get('weather_start','20171201'),config.get('weather_end','20251231'),site['id']))
    frames=[];failures=[]
    def run(task):
        try:return weather_point(*task,config,out),None
        except Exception as exc:return None,{'point':[task[0],task[1]],'error_type':type(exc).__name__}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i,(f,error) in enumerate(pool.map(run,tasks),1):
            if error:failures.append(error)
            else:frames.append(f)
            if i%8==0 or i==len(tasks):print('POWER points',i,'of',len(tasks),'failed',len(failures),flush=True)
    if failures:
        (out/'weather-failures.json').write_text(json.dumps(failures,indent=2));raise ValueError('Incomplete global weather acquisition')
    frame=history_features(pd.concat(frames,ignore_index=True),config['history_lag_days'])
    frame.to_csv(out/'weather.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    report={'generated_at':now(),'complete':True,'points':len(tasks),'point_days':len(frame),'missing_requested_values':int(frame[config['weather_parameters']].isna().sum().sum()),
      'mode':'retrospective','historical_availability_verified':False,'data_sha256':hashlib.sha256((out/'weather.csv.gz').read_bytes()).hexdigest(),
      'history_lag_days':config['history_lag_days'],'role':'Historical observed/reanalysis-derived NASA weather; never relabelled issued forecasts'}
    (out/'weather-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--lebanon-data');a=p.parse_args();acquire(a.config,a.out,a.lebanon_data)

if __name__=='__main__':main()
