"""Validated ingestion, coverage-aware labels and as-of feature assembly."""
from pathlib import Path
import hashlib
import math
import numpy as np
import pandas as pd

WEATHER = ['temperature_c','humidity_pct','precip_mm','wind_u_ms','wind_v_ms','rain7_mm']
ENV = ['vegetation_fraction','elevation_m','slope_deg','aspect_sin','aspect_cos','ndvi']
REQUIRED = {
 'cells': ['cell_id','region','lat','lon','vegetation_fraction','elevation_m','slope_deg','aspect_deg','available_at'],
 'weather': ['cell_id','prediction_time','issue_time','available_at','valid_start','valid_end','history_end','history_available_at', *WEATHER],
 'environment': ['cell_id','observation_time','available_at','ndvi'],
 'detections': ['detection_id','lat','lon','detected_at','sensor','processing_version','confidence','type','flag_level','flag_reason','flag_source'],
 'coverage': ['cell_id','start','end','sensor','observable_fraction'],
 'events': ['event_id','lat','lon','start','end','radius_km','level','reason','source','reported_at'],
}
TIME = {'prediction_time','issue_time','available_at','valid_start','valid_end','history_end','history_available_at','observation_time','detected_at','start','end','reported_at'}

def grid_id(lat,lon,step):
    if not (0 < step <= 1 and -90 <= lat < 90 and -180 <= lon < 180): raise ValueError('Invalid coordinates/grid')
    return f'{math.floor((lat+90)/step+1e-8)}_{math.floor((lon+180)/step+1e-8)}'

def load_inputs(directory,config):
    result,provenance={},{}
    for name,required in REQUIRED.items():
        path=Path(directory)/f'{name}.csv'
        table=pd.read_csv(path,keep_default_na=False)
        missing=set(required)-set(table.columns)
        if missing: raise ValueError(f'{name}: missing columns {sorted(missing)}')
        for col in set(table.columns)&TIME: table[col]=pd.to_datetime(table[col],utc=True,errors='raise')
        if table[list(set(table.columns)&TIME)].isna().any().any(): raise ValueError(f'{name}: null timestamps')
        result[name]=table
        provenance[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(table)}
    c,d,w,cov,e,v=(result[k] for k in ['cells','detections','weather','coverage','events','environment'])
    for table in [c,d,e]:
        if not (table.lat.between(-90,90,inclusive='left').all() and table.lon.between(-180,180,inclusive='left').all()): raise ValueError('Coordinates must be WGS84 degrees')
    if c.cell_id.duplicated().any() or d.detection_id.duplicated().any(): raise ValueError('Duplicate identifiers')
    if d.duplicated(['lat','lon','detected_at','sensor','processing_version']).any(): raise ValueError('Duplicate detections')
    if w.duplicated(['cell_id','prediction_time','issue_time']).any(): raise ValueError('Duplicate weather issues')
    if not set(d.sensor)<={'MODIS','VIIRS'}: raise ValueError('Unknown sensor')
    if not set(d.flag_level)<={'confirmed','probable','uncertain','unflagged'}: raise ValueError('Unknown flag')
    if not set(e.level)<={'confirmed','probable','uncertain'}: raise ValueError('Unknown event confidence')
    if not (cov.observable_fraction.between(0,1).all() and (cov.end>cov.start).all()): raise ValueError('Invalid coverage')
    if not (e.radius_km.gt(0).all() and (e.end>e.start).all()): raise ValueError('Invalid event windows')
    for table in [w,v,cov]:
        if not set(table.cell_id)<=set(c.cell_id): raise ValueError('Unknown cell')
    if not c.apply(lambda x:grid_id(x.lat,x.lon,config['grid_deg'])==x.cell_id,axis=1).all(): raise ValueError('Cell ID disagrees with grid')
    for table,cols in [(w,WEATHER),(c,['vegetation_fraction','elevation_m','slope_deg','aspect_deg']),(v,['ndvi'])]:
        for col in cols:
            table[col]=pd.to_numeric(table[col],errors='raise')
            if not np.isfinite(table[col]).all(): raise ValueError(f'Nonfinite {col}')
    if not (w.humidity_pct.between(0,100).all() and w.precip_mm.ge(0).all() and w.rain7_mm.ge(0).all()): raise ValueError('Weather units/range')
    if not (c.vegetation_fraction.between(0,1).all() and c.slope_deg.between(0,90).all() and v.ndvi.between(-1,1).all()): raise ValueError('Environmental range')
    if not (w.valid_end>w.valid_start).all(): raise ValueError('Empty weather windows')
    return result,provenance

def km_distance(lat,lon,other_lat,other_lon):
    p,q=np.radians(lat),np.radians(other_lat)
    a=np.sin((p-q)/2)**2+np.cos(p)*np.cos(q)*np.sin(np.radians(lon-other_lon)/2)**2
    return 6371*2*np.arcsin(np.sqrt(np.clip(a,0,1)))

def flag_detections(tables,config):
    d=tables['detections'].copy()
    d['cell_id']=[grid_id(a,b,config['grid_deg']) for a,b in zip(d.lat,d.lon)]
    levels={'unflagged':0,'uncertain':1,'probable':2,'confirmed':3}
    for i,r in d.iterrows():
        if str(r.type) in {'1','2','3','1.0','2.0','3.0'}:
            if levels[r.flag_level]<2: d.loc[i,'flag_level']='probable'
            d.loc[i,'flag_reason']=str(r.flag_reason)+'; source type indicates non-vegetation'
            d.loc[i,'flag_source']=str(r.flag_source)+'; original FIRMS type'
        confidence=str(r.confidence).lower()
        low=(r.sensor=='VIIRS' and confidence in {'l','low'}) or (r.sensor=='MODIS' and confidence.replace('.','',1).isdigit() and float(confidence)<30)
        if low and d.loc[i,'flag_level']=='unflagged':
            d.loc[i,'flag_level']='uncertain'
            d.loc[i,'flag_reason']='low sensor-specific confidence'
            d.loc[i,'flag_source']='original FIRMS confidence'
        for _,ev in tables['events'].iterrows():
            if ev.start<=r.detected_at<ev.end and km_distance(r.lat,r.lon,ev.lat,ev.lon)<=ev.radius_km:
                if levels[ev.level]>levels[d.loc[i,'flag_level']]: d.loc[i,'flag_level']=ev.level
                d.loc[i,'flag_reason']=str(d.loc[i,'flag_reason'])+'; '+ev.reason
                d.loc[i,'flag_source']=str(d.loc[i,'flag_source'])+'; '+ev.source
    # Only the training-period archive can fit recurrence review candidates.
    cutoff=pd.Timestamp(config['train_end'])
    history=d[d.detected_at<cutoff].copy()
    if not history.empty:
        history['review_lat']=history.lat.round(3);history['review_lon']=history.lon.round(3)
        groups=history.groupby(['review_lat','review_lon'])['detected_at']
        stats=groups.agg(['min','max']);stats['days']=groups.apply(lambda x:x.dt.floor('D').nunique())
        span=(stats['max']-stats['min']).dt.total_seconds()/86400+1
        candidates=set(stats.index[(stats.days>=30)&(stats.days/span>=.5)])
        mask=pd.Series([(round(a,3),round(b,3)) in candidates for a,b in zip(d.lat,d.lon)],index=d.index)&d.flag_level.eq('unflagged')
        d.loc[mask,'flag_level']='uncertain'
        d.loc[mask,'flag_reason']='>=30 active days and >=50% of training source-span days at rounded 0.001 degree location; review recurrence'
        d.loc[mask,'flag_source']='training-only recurrence heuristic (not industrial proof)'
    return d

def build_dataset(tables,config,policy):
    if policy not in {'conservative','strict'}: raise ValueError('Unknown policy')
    horizon=pd.Timedelta(hours=config['horizon_hours'])
    if horizon<=pd.Timedelta(0): raise ValueError('Positive horizon required')
    w=tables['weather'].copy()
    if config['mode'] not in {'archived_forecast','retrospective'}: raise ValueError('Unknown mode')
    if config['mode']=='archived_forecast': w=w[(w.issue_time<=w.prediction_time)&(w.available_at<=w.prediction_time)]
    w=w[(w.valid_start==w.prediction_time)&(w.valid_end==w.prediction_time+horizon)]
    w=w[(w.history_end<=w.prediction_time)&(w.history_available_at<=w.prediction_time)]
    w=w.sort_values('issue_time').drop_duplicates(['cell_id','prediction_time'],keep='last')
    d=flag_detections(tables,config)
    cells=tables['cells'].set_index('cell_id'); rows=[]
    blocked={'confirmed'} if policy=='conservative' else {'confirmed','probable','uncertain'}
    for _,r in w.iterrows():
        start=r.prediction_time; end=start+horizon; cell=cells.loc[r.cell_id]
        if cell.available_at>start: continue
        veg=tables['environment']
        veg=veg[(veg.cell_id==r.cell_id)&(veg.available_at<=start)&(veg.observation_time<=start)]
        if veg.empty: continue
        veg=veg.sort_values(['observation_time','available_at']).iloc[-1]
        hits=d[(d.cell_id==r.cell_id)&(d.detected_at>=start)&(d.detected_at<end)]
        excluded=hits.flag_level.isin(blocked).any()
        coverage=tables['coverage']
        coverage=coverage[(coverage.cell_id==r.cell_id)&(coverage.start<=start)&(coverage.end>=end)&(coverage.observable_fraction>=config['min_observable_fraction'])]
        observable=not coverage.empty
        status='excluded' if excluded else ('positive' if len(hits) else ('negative' if observable else 'uncertain'))
        row=r.to_dict(); row.update({k:cell[k] for k in ['region','lat','lon','vegetation_fraction','elevation_m','slope_deg']})
        row.update(static_available_at=cell.available_at,ndvi=veg.ndvi,environment_available_at=veg.available_at,environment_observed_at=veg.observation_time,
          aspect_sin=math.sin(math.radians(cell.aspect_deg)),aspect_cos=math.cos(math.radians(cell.aspect_deg)),window_end=end,
          label_status=status,y=(1 if status=='positive' else 0) if status in {'positive','negative'} else np.nan,
          detection_count=len(hits),sensor='|'.join(sorted(set(hits.sensor))) or 'no_detection',
          event_type='flagged' if hits.flag_level.ne('unflagged').any() else 'unflagged',observable=observable)
        rows.append(row)
    frame=pd.DataFrame(rows)
    if frame.empty: raise ValueError('No eligible feature windows; inspect issue/availability times')
    frame.attrs['omitted_feature_windows']=len(tables['weather'][['cell_id','prediction_time']].drop_duplicates())-len(frame)
    return frame,d

def summarize(frame):
    return {'observations':len(frame),'statuses':frame.label_status.value_counts().to_dict(),
      'positive_windows':int(frame.y.eq(1).sum()),'detections':int(frame.detection_count.sum()),
      'omitted_feature_windows':frame.attrs.get('omitted_feature_windows',0),
      'by_region':frame.groupby('region').y.agg(['count','sum']).to_dict(),
      'by_month':frame.groupby(frame.prediction_time.dt.month).y.agg(['count','sum']).to_dict()}
