"""Deterministic synthetic mechanics fixture; contains NO real fire observations."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .data import grid_id, REQUIRED

def create_fixture(out, config):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(config['seed']); tables={k:[] for k in REQUIRED}
    points=[('lebanon',33.85,35.55),('lebanon',34.15,35.85),('lebanon',33.55,35.65),('cyprus',34.85,32.45),('cyprus',35.05,33.25)]
    for i,(region,lat,lon) in enumerate(points):
        cid=grid_id(lat,lon,config['grid_deg']); elev=200+i*300
        tables['cells'].append(dict(cell_id=cid,region=region,lat=lat,lon=lon,vegetation_fraction=.7,elevation_m=elev,slope_deg=10+i*3,aspect_deg=i*65,available_at='2018-01-01T00:00:00Z'))
        tables['environment'].append(dict(cell_id=cid,observation_time='2018-01-01T00:00:00Z',available_at='2018-02-01T00:00:00Z',ndvi=.4+i*.03))
        for t in pd.date_range('2019-01-01','2022-12-31',tz='UTC'):
            season=np.sin(2*np.pi*(t.day_of_year-110)/365.25)
            temp=20+10*season+rng.normal(0,3); rh=np.clip(60-20*season+rng.normal(0,10),5,100)
            rain=max(0,rng.normal(2-3*season,2)); u,v=rng.normal(0,3,2); rain7=max(0,20-15*season+rng.normal(0,4))
            end=t+pd.Timedelta(hours=config['horizon_hours'])
            tables['weather'].append(dict(cell_id=cid,prediction_time=t,issue_time=t-pd.Timedelta(hours=6),available_at=t-pd.Timedelta(hours=4),valid_start=t,valid_end=end,history_end=t-pd.Timedelta(days=2),history_available_at=t-pd.Timedelta(days=1),temperature_c=temp,humidity_pct=rh,precip_mm=rain,wind_u_ms=u,wind_v_ms=v,rain7_mm=rain7))
            tables['coverage'].append(dict(cell_id=cid,start=t,end=end,sensor='VIIRS',observable_fraction=1 if rng.random()>.08 else .2))
            prob=1/(1+np.exp(-(-5+.12*temp-.02*rh+.10*abs(u)-.025*rain7)))
            if rng.random()<prob:
                level=rng.choice(['unflagged','probable','confirmed'],p=[.8,.12,.08])
                sensor='VIIRS' if rng.random()<.8 else 'MODIS'
                tables['detections'].append(dict(detection_id=f'fixture-{i}-{t.date()}',lat=lat,lon=lon,detected_at=t+pd.Timedelta(hours=12),sensor=sensor,processing_version='SYNTHETIC',confidence='nominal' if sensor=='VIIRS' else 80,type=0,flag_level=level,flag_reason='synthetic review flag' if level!='unflagged' else '',flag_source='fixture'))
    for name,rows in tables.items(): pd.DataFrame(rows,columns=REQUIRED[name]).to_csv(out/f'{name}.csv',index=False)
    cfg=dict(config,synthetic=True,regional_cells=[grid_id(a,b,config['grid_deg']) for r,a,b in points if r!='lebanon'])
    (out/'config.json').write_text(json.dumps(cfg,indent=2))
    (out/'SYNTHETIC.txt').write_text('Generated mechanics fixture. No observations, forecast skill or regional similarity established.\n')
    return cfg
