"""Decode NASA GEOS hourly files with verified timestamps and physical units."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import h5py
import numpy as np
import pandas as pd

VARIABLES={'T2M':'K','QV2M':'kg kg-1','PS':'Pa','U10M':'m s-1','V10M':'m s-1'}

def text_attr(value):
    return value.decode() if isinstance(value,(bytes,np.bytes_)) else str(value)

def decode_hour(path,cells,available_at):
    path=Path(path)
    match=re.search(r'GEOS\.fp\.fcst\.tavg1_2d_slv_Nx\.(\d{8}_\d{2})\+(\d{8}_\d{4})\.V\d+\.nc4$',path.name)
    if not match:raise ValueError('Explicit GEOS forecast issue/valid file name required')
    issue=pd.to_datetime(match[1],format='%Y%m%d_%H',utc=True)
    midpoint=pd.to_datetime(match[2],format='%Y%m%d_%H%M',utc=True)
    available=pd.Timestamp(available_at)
    if available.tzinfo is None:raise ValueError('Availability needs an explicit timezone')
    if available<issue or midpoint<=issue:raise ValueError('Invalid issue/availability/lead times')
    rows=[]
    with h5py.File(path) as f:
        for var,unit in VARIABLES.items():
            if var not in f or text_attr(f[var].attrs.get('units',''))!=unit:raise ValueError(f'Missing variable or unit mismatch: {var}')
        units=text_attr(f['time'].attrs['units'])
        if not units.startswith('minutes since '):raise ValueError('Unsupported GEOS time units')
        actual=pd.Timestamp(units.removeprefix('minutes since '),tz='UTC')+pd.Timedelta(minutes=float(f['time'][0]))
        if len(f['time'])!=1 or actual!=midpoint:raise ValueError('File time disagrees with valid midpoint')
        lat=f['lat'][:];lon=f['lon'][:]
        arrays={name:f[name][0,:,:] for name in VARIABLES}
        for r in cells.itertuples():
            i=int(np.argmin(abs(lat-r.lat)));j=int(np.argmin(abs(lon-r.lon)))
            values={name:float(arrays[name][i,j]) for name in VARIABLES}
            for name,value in values.items():
                fill=np.asarray(f[name].attrs.get('_FillValue',f[name].attrs.get('missing_value',np.nan))).ravel()[0]
                if not np.isfinite(value) or value==fill:raise ValueError(f'Missing forecast {name}')
            if abs(values['U10M'])>200 or abs(values['V10M'])>200:raise ValueError('Unphysical wind or missing sentinel')
            t=values['T2M']-273.15;q=values['QV2M'];pressure=values['PS']
            if not (150<values['T2M']<350 and 0<=q<.1 and 20000<pressure<120000):raise ValueError('Unphysical temperature/humidity/pressure')
            vapor=q*pressure/(.622+.378*q)
            rh=100*vapor/(611.2*np.exp(17.67*t/(t+243.5)))
            rows.append({'cell_id':r.cell_id,'lat':r.lat,'lon':r.lon,'weather_lat':float(lat[i]),'weather_lon':float(lon[j]),
                'issue_time':issue,'available_at':available,'valid_start':midpoint-pd.Timedelta(minutes=30),'valid_end':midpoint+pd.Timedelta(minutes=30),
                'lead_hours':(midpoint-issue).total_seconds()/3600,'temperature_c':t,'humidity_pct':float(np.clip(rh,0,100)),
                'humidity_clipped':bool(rh<0 or rh>100),'wind_u_ms':values['U10M'],'wind_v_ms':values['V10M'],
                'weather_source':'NASA_GEOS_FP','source_file':path.name})
    return pd.DataFrame(rows)

def aggregate_window(hourly,prediction_time,horizon_hours=24):
    """Precipitation must already be decoded from its own NASA collection in mm/hour."""
    start=pd.Timestamp(prediction_time);end=start+pd.Timedelta(hours=horizon_hours)
    if start.tzinfo is None or horizon_hours<=0 or horizon_hours%1:raise ValueError('UTC-aware time and whole-hour horizon required')
    required={'cell_id','issue_time','available_at','valid_start','valid_end','temperature_c','humidity_pct','wind_u_ms','wind_v_ms','precip_mm'}
    if required-set(hourly):raise ValueError(f'Incomplete forecast variables: {required-set(hourly)}')
    f=hourly.copy()
    for c in ['issue_time','available_at','valid_start','valid_end']:f[c]=pd.to_datetime(f[c],utc=True,errors='raise')
    rows=[]
    for (cell,issue),g in f.groupby(['cell_id','issue_time']):
        g=g[(g.valid_start>=start)&(g.valid_end<=end)].sort_values('valid_start')
        if issue>start or g.available_at.isna().any() or (g.available_at>start).any():continue
        expected=pd.date_range(start,periods=int(horizon_hours),freq='h')
        if len(g)!=len(expected) or not np.array_equal(g.valid_start.to_numpy(),expected.to_numpy()) or not (g.valid_end==g.valid_start+pd.Timedelta(hours=1)).all():continue
        cols=['temperature_c','humidity_pct','wind_u_ms','wind_v_ms','precip_mm']
        if not np.isfinite(g[cols].to_numpy(dtype=float)).all() or g.precip_mm.lt(0).any():continue
        rows.append({'cell_id':cell,'prediction_time':start,'valid_start':start,'valid_end':end,'issue_time':issue,'available_at':g.available_at.max(),
          **{c:float(g[c].mean()) for c in cols if c!='precip_mm'},'precip_mm':float(g.precip_mm.sum()),'weather_source':'NASA_GEOS_FP'})
    if not rows:raise ValueError('No complete, available, single-issue forecast window')
    return pd.DataFrame(rows).sort_values('issue_time').drop_duplicates(['cell_id','prediction_time'],keep='last')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--file',required=True);p.add_argument('--cells',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    path=Path(a.file);manifest=json.loads(path.with_suffix(path.suffix+'.manifest.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Forecast checksum mismatch')
    frame=decode_hour(path,pd.read_csv(a.cells),manifest['downloaded_at']);frame.to_csv(a.out,index=False)
    print(json.dumps({'decoded_cell_hours':len(frame),'complete_daily_window':False,'precipitation_available':False}))

if __name__=='__main__':main()
