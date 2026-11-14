"""Auditable real-data preparation. Unknown negatives cannot pass the training gate.

This module does not train on a bounding rectangle, assume fire-free observations,
backdate POWER, or represent archived observations as issued forecasts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import math
import numpy as np
import pandas as pd
from .data import grid_id, km_distance

TYPE_REASONS={1:'source type: active volcano',2:'source type: other static land source',3:'source type: offshore source'}

def audit_detections(frame,config):
    f=frame.copy()
    required={'detection_id','lat','lon','detected_at','product','sensor','satellite','processing_version','confidence','type'}
    if required-set(f): raise ValueError(f'Missing detection columns {required-set(f)}')
    f['detected_at']=pd.to_datetime(f.detected_at,utc=True,errors='raise')
    if f.detected_at.isna().any() or f.detection_id.duplicated().any(): raise ValueError('Null time or duplicate identifier')
    if not (f.lat.between(-90,90,inclusive='left').all() and f.lon.between(-180,180,inclusive='left').all()): raise ValueError('Invalid WGS84 location')
    if not set(f.sensor)<={'VIIRS','MODIS'}: raise ValueError('Unknown sensor')
    supplied_level=f.get('flag_level',pd.Series('unflagged',index=f.index)).copy()
    supplied_reason=f.get('flag_reason',pd.Series('',index=f.index)).fillna('').copy()
    supplied_source=f.get('flag_source',pd.Series('',index=f.index)).fillna('').copy()
    severity={'unflagged':0,'uncertain':1,'probable':2,'confirmed':3}
    if not set(supplied_level)<=set(severity):raise ValueError('Unknown supplied review level')
    reviewed=supplied_level.ne('unflagged')
    if (reviewed&(supplied_reason.eq('')|supplied_source.eq(''))).any():raise ValueError('Reviewed flags require a reason and source')
    types=pd.to_numeric(f['type'],errors='coerce')
    numeric_conf=pd.to_numeric(f.confidence,errors='coerce')
    confidence=f.confidence.astype(str).str.lower()
    low=(f.sensor.eq('VIIRS')&confidence.isin(['l','low']))|(f.sensor.eq('MODIS')&numeric_conf.lt(30))
    invalid=(f.sensor.eq('VIIRS')&~confidence.isin(['l','n','h','low','nominal','high']))|(f.sensor.eq('MODIS')&~numeric_conf.between(0,100))|~types.isin([0,1,2,3])
    f['source_type_flag']=types.isin(TYPE_REASONS)
    f['low_confidence_flag']=low
    f['invalid_metadata_flag']=invalid
    # Freeze recurrence evidence on the training archive only, never the held-out years.
    cutoff=pd.Timestamp(config['recurrence_fit_end_exclusive'])
    if cutoff>pd.Timestamp(config['train_end_exclusive']): raise ValueError('Recurrence fit must not inspect validation/test')
    step=config['recurrence_round_degrees']
    if not 0<step<=.1: raise ValueError('Invalid recurrence bin')
    f['review_bin']=[grid_id(a,b,step) for a,b in zip(f.lat,f.lon)]
    history=f[(f.detected_at>=pd.Timestamp(config['start']))&(f.detected_at<cutoff)].copy();history['day']=history.detected_at.dt.floor('D');history['year']=history.detected_at.dt.year
    counts=history.groupby('review_bin').agg(active_days=('day','nunique'),years=('year','nunique'))
    candidates=set(counts.index[(counts.active_days>=config['recurrence_min_active_days'])&(counts.years>=config['recurrence_min_years'])])
    f['recurrence_candidate']=f.review_bin.isin(candidates)
    f['flag_level']=np.select([f.source_type_flag,invalid|low|f.recurrence_candidate],['probable','uncertain'],default='unflagged')
    f.loc[supplied_level.map(severity)>f.flag_level.map(severity),'flag_level']=supplied_level
    reasons=[];sources=[]
    for _,r in f.iterrows():
        tags=[];src=[]
        if supplied_level.loc[r.name]!='unflagged':
            tags.append(supplied_reason.loc[r.name]);src.append(supplied_source.loc[r.name])
        if r.source_type_flag:
            tags.append(TYPE_REASONS[int(float(r['type']))]);src.append('NASA FIRMS original type')
        if r.low_confidence_flag: tags.append('low sensor-specific confidence');src.append('NASA FIRMS original confidence')
        if r.invalid_metadata_flag: tags.append('invalid or unrecognized source metadata');src.append('schema/range validation')
        if r.recurrence_candidate:
            tags.append('recurrent location in training archive; non-vegetation cause NOT established');src.append(f'NASA detection history before {cutoff.isoformat()}')
        reasons.append('; '.join(tags));sources.append('; '.join(src))
    f['flag_reason']=reasons;f['flag_source']=sources
    f['cell_id']=[grid_id(a,b,config['grid_deg']) for a,b in zip(f.lat,f.lon)]
    f['window_start']=f.detected_at.dt.floor('D')
    f['conservative_action']='retain_detection_candidate'
    f['strict_action']=np.where(f.flag_level.eq('unflagged'),'retain_detection_candidate','quarantine_entire_cell_window')
    # Invalid metadata is unusable even in the broad policy; every policy quarantines its window.
    f.loc[invalid|f.flag_level.eq('confirmed'),'conservative_action']='quarantine_entire_cell_window'
    # Beirut association is review evidence only, never an automatic confirmed exclusion.
    f['beirut_review_match']=(f.detected_at>=pd.Timestamp('2020-08-04T14:00:00Z'))&(f.detected_at<pd.Timestamp('2020-08-05T18:00:00Z'))&(km_distance(f.lat,f.lon,33.901,35.519)<=3)
    f['recurrence_fit_end_exclusive']=cutoff.isoformat()
    return f,counts.reset_index()

def candidate_grid(config):
    west,south,east,north=config['bbox'];step=config['grid_deg']
    if not (-180<=west<east<=180 and -90<=south<north<=90): raise ValueError('Invalid bbox')
    cells=[]
    for i in range(math.floor((south+90)/step+1e-8),math.ceil((north+90)/step-1e-8)):
        for j in range(math.floor((west+180)/step+1e-8),math.ceil((east+180)/step-1e-8)):
            cells.append({'cell_id':f'{i}_{j}','lat':(i+.5)*step-90,'lon':(j+.5)*step-180,'scope_status':config['scope']})
    return pd.DataFrame(cells)

def cell_day_labels(cells,audit,config,policy,start,end):
    if config['horizon_hours']!=24: raise ValueError('This real-data adapter currently supports UTC daily 24-hour windows only')
    if policy not in {'conservative','strict'}: raise ValueError('Unknown policy')
    days=pd.date_range(start,pd.Timestamp(end)-pd.Timedelta(days=1),freq='D')
    frame=pd.MultiIndex.from_product([cells.cell_id,days],names=['cell_id','prediction_time']).to_frame(index=False)
    hits=audit[(audit.detected_at>=pd.Timestamp(start))&(audit.detected_at<pd.Timestamp(end))].copy()
    primary=hits[hits['product'].eq(config['primary_product'])]
    primary_counts=primary.groupby(['cell_id','window_start']).size()
    all_counts=hits.groupby(['cell_id','window_start']).size()
    blocked=hits[hits[f'{policy}_action'].eq('quarantine_entire_cell_window')].groupby(['cell_id','window_start']).size()
    idx=pd.MultiIndex.from_frame(frame[['cell_id','prediction_time']])
    frame['primary_detection_count']=primary_counts.reindex(idx,fill_value=0).to_numpy()
    frame['all_sensor_detection_count']=all_counts.reindex(idx,fill_value=0).to_numpy()
    frame['excluded_detection_count']=blocked.reindex(idx,fill_value=0).to_numpy()
    frame['label_status']=np.select([frame.excluded_detection_count.gt(0),frame.primary_detection_count.gt(0)],['excluded','positive'],default='uncertain')
    frame['y']=np.where(frame.label_status.eq('positive'),1.0,np.nan)
    frame['policy']=policy;frame['coverage_status']='unknown_no_mask_supplied'
    frame['window_end']=frame.prediction_time+pd.Timedelta(days=1)
    a,b=pd.Timestamp(config['train_end_exclusive']),pd.Timestamp(config['validation_end_exclusive']);gap=pd.Timedelta(days=config['embargo_days'])
    if gap<pd.Timedelta(days=1): raise ValueError('Embargo must cover horizon')
    frame['split']=np.select([frame.window_end<a-gap,(frame.prediction_time>=a+gap)&(frame.window_end<b-gap),frame.prediction_time>=b+gap],['train','validation','test'],default='embargo')
    return frame

def prepare_real(data,config_path,out):
    root=Path(data);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    config=json.loads(Path(config_path).read_text())
    raw=pd.read_csv(root/'detections.csv',keep_default_na=False,dtype={'confidence':str,'processing_version':str})
    audit,recurrence=audit_detections(raw,config)
    audit.to_csv(out/'detection-audit.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    recurrence.to_csv(out/'recurrence-training-evidence.csv',index=False)
    cells=candidate_grid(config)
    observed=set(audit.cell_id);outside=observed-set(cells.cell_id)
    if outside: raise ValueError(f'{len(outside)} detection cells outside analysis bbox; revise config, never silently drop')
    weather=pd.read_csv(root/'weather_historical.csv')
    points=weather[['weather_point_id','lat','lon']].drop_duplicates()
    # Geographic distance only; this does not imply weather fidelity at cell scale.
    match=[]
    for r in cells.itertuples():
        dist=km_distance(points.lat,points.lon,r.lat,r.lon);i=dist.idxmin();match.append((points.loc[i,'weather_point_id'],float(dist.loc[i])))
    cells[['weather_point_id','distance_to_weather_sample_km']]=pd.DataFrame(match,index=cells.index)
    cells.to_csv(out/'candidate-grid.csv',index=False)
    # Existing complete weather table stays separate to avoid duplicating coarse data over every grid cell.
    # A scientific as-of feature join is blocked until historical publication times are established.
    counts={};files=[]
    for policy in ['conservative','strict']:
        path=out/f'candidate-windows-{policy}.csv.gz';first=True;totals={};by_split={}
        for year in range(pd.Timestamp(config['start']).year,pd.Timestamp(config['end_exclusive']).year+1):
            if pd.Timestamp(f'{year}-01-01',tz='UTC')>=pd.Timestamp(config['end_exclusive']):break
            start=max(pd.Timestamp(config['start']),pd.Timestamp(f'{year}-01-01',tz='UTC'))
            end=min(pd.Timestamp(config['end_exclusive']),pd.Timestamp(f'{year+1}-01-01',tz='UTC'))
            frame=cell_day_labels(cells,audit,config,policy,start,end)
            frame.to_csv(path,index=False,mode='w' if first else 'a',header=first,compression={'method':'gzip','mtime':0});first=False
            for k,v in frame.label_status.value_counts().items():totals[k]=totals.get(k,0)+int(v)
            for (s,l),v in frame.groupby(['split','label_status']).size().items():
                by_split.setdefault(s,{});by_split[s][l]=by_split[s].get(l,0)+int(v)
        counts[policy]={'windows':sum(totals.values()),'labels':totals,'split_counts':by_split};files.append(path)
    blockers=['no compatible satellite observability masks: no verified negative labels',
      'candidate bbox lacks a verified national/vegetation mask',
      'historically available vegetation/terrain features missing',
      'POWER history has no verified issue/availability timestamps for operational evaluation',
      'complete multi-year forecast meteorology not acquired']
    report={'code_sha256':hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest(),'config':config,'training_allowed':False,'blockers':blockers,'raw_detection_rows':len(audit),
      'flags':audit.flag_level.value_counts().to_dict(),'reason_flags':{c:int(audit[c].sum()) for c in ['source_type_flag','low_confidence_flag','invalid_metadata_flag','recurrence_candidate','beirut_review_match']},
      'candidate_cells':len(cells),'primary_product':config['primary_product'],'policies':counts,
      'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'detections.csv',root/'weather_historical.csv',Path(config_path)]},
      'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
      'test_usage':'Only label-quality bookkeeping; test labels/features not fitted or used for model selection',
      'notes':['No confirmed industrial or conflict attribution made','No-detection examples remain uncertain','No probability model was trained','Recurrence evidence frozen before validation/test','Candidate rectangle is NOT a Lebanon national forecast grid']}
    (out/'readiness.json').write_text(json.dumps(report,indent=2,default=str))
    from .statecharts import write_statecharts
    write_statecharts(report,out/'statecharts.md')
    return report

def require_ready(report):
    if not report.get('training_allowed'):
        raise ValueError('Real-data training blocked: '+'; '.join(report.get('blockers',[])))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--config',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=prepare_real(a.data,a.config,a.out);print(json.dumps({'training_allowed':r['training_allowed'],'policies':r['policies'],'blockers':r['blockers']},indent=2))

if __name__=='__main__':main()
