"""Shared feature contracts and split exports for global-to-Lebanon experiments."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .data import km_distance
from .gridded import label_counts
from .global_acquire import sample_days,now
from .global_weather import history_features
from .conflict_review import load_geometry,apply_quarantine,excluded_cells

FEATURES=['temperature_c','humidity_pct','precip_mm','wind_u_ms','wind_v_ms','rain7_mm','rain30_mm','temperature7_c','vpd_kpa',
 'vegetation_fraction','elevation_m','slope_deg','aspect_sin','aspect_cos','latitude','season_sin','season_cos','hemisphere_season_sin','hemisphere_season_cos']


def add_features(frame):
    f=frame.copy();time=pd.to_datetime(f.prediction_time,utc=True)
    f['latitude']=f.lat;f['season_sin']=np.sin(2*np.pi*time.dt.day_of_year/365.25);f['season_cos']=np.cos(2*np.pi*time.dt.day_of_year/365.25)
    sign=np.where(f.lat>=0,1,-1);f['hemisphere_season_sin']=f.season_sin*sign;f['hemisphere_season_cos']=f.season_cos*sign
    return f


def count_pixels(mask,qa,mapping,region,date):
    eligible=np.asarray(mapping['eligible'],bool);mask=np.asarray(mask);land=np.isin(np.asarray(qa)&3,[1,2])
    if len(mask)!=len(eligible):raise ValueError('Raw mask and pixel-map length mismatch')
    return pd.DataFrame({'region':region,'cell_id':mapping['cell_ids'],'prediction_time':pd.Timestamp(date,tz='UTC'),
      'processed':eligible&land&np.isin(mask,[5,7,8,9]),'fire':eligible&land&np.isin(mask,[7,8,9]),
      'nominal_fire':eligible&land&np.isin(mask,[8,9]),'low_fire':eligible&land&(mask==7),
      'noneligible_fire':((~eligible)|(~land))&np.isin(mask,[7,8,9]),'unknown_fire':eligible&(mask==6),'cloud':eligible&(mask==4),
      'missing':eligible&np.isin(mask,[0,1,2])}).groupby(['region','cell_id','prediction_time']).sum().reset_index()


def quality_labels(frame,config):
    f=frame.copy();f['processed_fraction']=f.processed/f.eligible_pixels
    for policy in ['conservative','strict']:
        f['label_status_'+policy],f['y_'+policy]=label_counts(f,np.zeros(len(f),bool),policy,config['min_processed_fraction'])
    f['y']=f.y_strict;f['label_status']=f.label_status_strict
    return f


def join_weather(frame,weather):
    links=[]
    for region,cells in frame[['region','cell_id','lat','lon']].drop_duplicates().groupby('region'):
        points=weather[weather.weather_region.eq(region)][['weather_point_id','lat','lon']].drop_duplicates()
        if points.empty:raise ValueError('No weather points for '+region)
        for r in cells.itertuples():
            distance=km_distance(points.lat,points.lon,r.lat,r.lon);p=points.loc[distance.idxmin()]
            links.append({'region':region,'cell_id':r.cell_id,'weather_point_id':p.weather_point_id})
    f=frame.merge(pd.DataFrame(links),on=['region','cell_id'],validate='many_to_one')
    w=weather.rename(columns={'date':'prediction_time','weather_region':'region'}).copy();w['prediction_time']=pd.to_datetime(w.prediction_time,utc=True)
    cols=['region','weather_point_id','prediction_time']+FEATURES[:9]
    return f.merge(w[cols],on=['region','weather_point_id','prediction_time'],how='left',validate='many_to_one')


def build_global(config,archive,weather_path):
    if config.get('horizon_hours')!=24:raise ValueError('Global daily-composite adapter requires a 24-hour horizon')
    archive=Path(archive);report=json.loads((archive/'archive-report.json').read_text())
    if not report['complete']:raise ValueError('Global scientific subset archive incomplete')
    cells=pd.concat([pd.read_csv(p) for p in sorted((archive/'static').glob('*-cells.csv'))],ignore_index=True)
    if cells.duplicated(['region','cell_id']).any():raise ValueError('Duplicate global cells')
    maps={p.stem:dict(np.load(p)) for p in (archive/'maps').glob('*.npz')};counts=[]
    for i,path in enumerate(sorted((archive/'fire').glob('*.npz'))):
        meta=json.loads(path.with_suffix('.npz.manifest.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['subset_sha256']:raise ValueError('Global raw subset checksum mismatch')
        with np.load(path) as raw:
            for site in meta['site_order']:
                mapping=maps[site+'-'+meta['tile']];use=raw['site_id']==site
                counts.append(count_pixels(raw['FireMask'][use],raw['QA'][use],mapping,site,meta['date']))
        if (i+1)%1000==0:print('Prepared global raw subsets',i+1,flush=True)
    daily=pd.concat(counts,ignore_index=True).groupby(['region','cell_id','prediction_time']).sum().reset_index()
    # Full configured spatial/date panel includes missing catalogue/source dates as uncertainty.
    windows=cells.merge(pd.DataFrame({'prediction_time':sample_days(config)}),how='cross')
    f=windows.merge(daily,on=['region','cell_id','prediction_time'],how='left',validate='one_to_one');f=quality_labels(f,config)
    f['window_end']=f.prediction_time+pd.Timedelta(hours=24)
    weather=pd.read_csv(weather_path);wanted=set(sample_days(config).strftime('%Y-%m-%d'));weather=weather[weather.date.isin(wanted)]
    f=join_weather(f,weather);f['source_product']='VJ114A1.002';f['firms_review_available']=False
    # Recurrence is a training-era review candidate, not an automatic industrial exclusion.
    tr=f[(f.prediction_time<pd.Timestamp(config['training_end']))&~f.geographic_holdout]
    active=tr[tr.fire.gt(0)].assign(year=lambda x:x.prediction_time.dt.year).groupby(['region','cell_id']).agg(active_dates=('prediction_time','nunique'),active_years=('year','nunique'))
    candidates=set(active.index[(active.active_dates>=12)&(active.active_years>=3)])
    f['recurrence_review_candidate']=[(r,c) in candidates for r,c in zip(f.region,f.cell_id)]
    return add_features(f)


def build_lebanon(config,old_data,masks,old_weather,new_weather):
    old_data=Path(old_data);masks=Path(masks)
    source_config=json.loads((old_data/'static-report.json').read_text())['config']
    if source_config['grid_deg']!=config['grid_deg'] or source_config['horizon_hours']!=config['horizon_hours']:
        raise ValueError('Global and Lebanese grid/horizon must match; rebuild the Lebanese source dataset')
    if not json.loads((masks/'archive-report.json').read_text())['complete']:raise ValueError('Lebanese confirmation source archive incomplete')
    cells=pd.read_csv(old_data/'cells.csv');maps={p.stem.removeprefix('pixel-map-'):dict(np.load(p)) for p in old_data.glob('pixel-map-*.npz')};counts=[]
    for path in sorted((masks/'fire').glob('*.npz')):
        meta=json.loads(path.with_suffix('.npz.manifest.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['subset_sha256']:raise ValueError('Confirmation raw checksum mismatch')
        with np.load(path) as raw:counts.append(count_pixels(raw['FireMask'],raw['QA'],maps[meta['tile']],'lebanon',meta['date']))
    daily=pd.concat(counts,ignore_index=True).groupby(['region','cell_id','prediction_time']).sum().reset_index()
    dates=pd.date_range(config['fresh_lebanon_confirmation'][0],pd.Timestamp(config['fresh_lebanon_confirmation'][1])-pd.Timedelta(days=1),freq='D')
    fresh=cells.merge(pd.DataFrame({'prediction_time':dates}),how='cross').merge(daily,on=['region','cell_id','prediction_time'],how='left',validate='one_to_one')
    fresh=quality_labels(fresh,config);fresh['window_end']=fresh.prediction_time+pd.Timedelta(hours=24)
    old=pd.read_csv(old_data/'dataset-strict.csv.gz');conservative=pd.read_csv(old_data/'dataset-conservative.csv.gz',usecols=['cell_id','prediction_time','y','label_status'])
    for c in ['prediction_time','window_end']:old[c]=pd.to_datetime(old[c],utc=True)
    conservative['prediction_time']=pd.to_datetime(conservative.prediction_time,utc=True)
    old['y_strict']=old.y;old['label_status_strict']=old.label_status
    old=old.merge(conservative.rename(columns={'y':'y_conservative','label_status':'label_status_conservative'}),on=['cell_id','prediction_time'],validate='one_to_one')
    old['firms_review_available']=True;fresh['firms_review_available']=False
    f=pd.concat([old,fresh],ignore_index=True)
    rawcols=['weather_point_id','lat','lon','date',*config['weather_parameters']]
    w=pd.concat([pd.read_csv(old_weather)[rawcols],pd.read_csv(new_weather)[rawcols]],ignore_index=True).drop_duplicates(['weather_point_id','date'],keep='first')
    w=history_features(w,config['history_lag_days']);w['weather_region']='lebanon'
    # Recompute shared weather features identically from the NASA daily values.
    f=f.drop(columns=[c for c in ['weather_point_id',*FEATURES[:9]] if c in f])
    f=join_weather(f,w);f['continent']='asia';f['geographic_holdout']=False;f['source_product']='VJ114A1.002'
    return add_features(f)


def split_masks(frame,config,domain):
    t=pd.to_datetime(frame.prediction_time,utc=True);end=pd.to_datetime(frame.window_end,utc=True);gap=pd.Timedelta(days=config['embargo_days'])
    a,b,c=map(pd.Timestamp,[config['training_end'],config['calibration_end'],config['validation_end']]);geo=frame.geographic_holdout.astype(bool)
    result={'train':(end<a-gap)&~geo,'calibration':(t>=a+gap)&(end<b-gap)&~geo,'validation':(t>=b+gap)&(end<c-gap)&~geo}
    if domain=='global':
        test=(t>=c+gap)&(end<=pd.Timestamp(config['end_exclusive']))
        result['test-sealed']=test&~geo;result['geographic-test-sealed']=test&geo
    else:
        year=pd.Timestamp(config['fresh_lebanon_confirmation'][0]);stop=pd.Timestamp(config['fresh_lebanon_confirmation'][1])
        result['known-test']=(t>=c+gap)&(end<year-gap)
        result['confirmation-sealed']=(t>=year+gap)&(end<=stop)
    counts=np.column_stack([m.to_numpy() for m in result.values()]).sum(axis=1)
    if (counts>1).any():raise ValueError('Dataset splits overlap')
    return result


def export_splits(frame,config,domain,out,conflict_config=None,geometry=None):
    f=frame.copy();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if conflict_config:
        for policy in ['conservative','strict']:
            part=f.copy();part['y']=part['y_'+policy];part['label_status']=part['label_status_'+policy]
            part=apply_quarantine(part,conflict_config,geometry,config['grid_deg'])
            f['y_'+policy]=part.y;f['label_status_'+policy]=part.label_status
            if policy=='strict':
                for key in ['conflict_excluded','exclusion_policy_id','exclusion_reason','exclusion_source','y_before_conflict_quarantine','label_status_before_conflict_quarantine']:f[key]=part[key]
        f['y']=f.y_strict;f['label_status']=f.label_status_strict
    else:f['conflict_excluded']=False
    missing=~np.isfinite(f[FEATURES].to_numpy(dtype=float)).all(axis=1)
    for policy in ['conservative','strict']:
        f.loc[missing&f['y_'+policy].notna(),'label_status_'+policy]='excluded_missing_feature';f.loc[missing,'y_'+policy]=np.nan
    f['y']=f.y_strict;f['label_status']=f.label_status_strict
    keep=['region','continent','geographic_holdout','cell_id','prediction_time','window_end','lat','lon','source_product','firms_review_available',
      'processed_fraction','fire','low_fire','noneligible_fire','unknown_fire','cloud','missing','eligible_pixels','y','label_status',
      'y_strict','label_status_strict','y_conservative','label_status_conservative','conflict_excluded',*FEATURES]
    keep+=['exclusion_policy_id','exclusion_reason','exclusion_source','y_before_conflict_quarantine','label_status_before_conflict_quarantine'] if conflict_config else []
    f=f[list(dict.fromkeys(keep))];reports={}
    for name,mask in split_masks(f,config,domain).items():
        part=f[mask].copy();path=out/f'{domain}-{name}.csv.gz'
        part.to_csv(path,index=False,compression={'method':'gzip','mtime':0})
        report={'rows':len(part),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'first_prediction':str(part.prediction_time.min()),'last_window_end':str(part.window_end.max()),'conflict_quarantined_windows':int(part.conflict_excluded.sum())}
        if 'sealed' not in name:
            report['qualified_rows']=int(part.y.notna().sum());report['positive_windows']=int(part.y.fillna(0).sum())
        reports[name]=report
    return reports


def prepare(config_path,archive,weather,old_data,confirmation_masks,old_weather,new_weather,conflict_path,conflict_geometry,out):
    config=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
    global_frame=build_global(config,archive,weather)
    global_report=export_splits(global_frame,config,'global',out)
    global_cells=set(global_frame.cell_id);del global_frame
    lebanon=build_lebanon(config,old_data,confirmation_masks,old_weather,new_weather)
    if set(lebanon.cell_id)&global_cells:raise ValueError('Lebanon cells leaked into global pretraining panels')
    conflict=json.loads(Path(conflict_path).read_text());geometry=load_geometry(conflict_geometry,conflict)
    lebanon_report=export_splits(lebanon,config,'lebanon',out,conflict,geometry)
    manifest={'generated_at':now(),'synthetic':False,'mode':'retrospective','features':FEATURES,'global':global_report,'lebanon':lebanon_report,
      'config':config,'config_sha256':hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),'conflict_policy':conflict,
      'conflict_geometry_sha256':hashlib.sha256(Path(conflict_geometry).read_bytes()).hexdigest(),
      'conflict_excluded_cell_ids':sorted(excluded_cells(lebanon,geometry,config['grid_deg'])),
      'input_sha256':{str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in [Path(archive)/'archive-report.json',Path(archive)/'static-report.json',Path(weather),Path(old_data)/'dataset-strict.csv.gz',Path(old_data)/'dataset-conservative.csv.gz',Path(old_weather),Path(new_weather),Path(confirmation_masks)/'archive-report.json',Path(conflict_path)]},
      'label_definition':'NOAA-20 VJ114A1.002 vegetation-associated detected occurrence conditional on >=0.8 processed eligible area',
      'limitations':['Sampled global panels are not exhaustive global coverage','Global labels lack full FIRMS facility/conflict review; confidence/vegetation masks remain imperfect','2026 Lebanon masks lack original FIRMS type/confidence review available for older Lebanese labels','No incident-independent truth or historically issued weather evaluation','No confirmation metrics computed during preparation']}
    (out/'dataset-manifest.json').write_text(json.dumps(manifest,indent=2));print('Prepared split files; confirmation labels remain sealed from model selection',flush=True)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['config','archive','weather','old-data','confirmation-masks','old-weather','new-weather','conflict-config','conflict-geometry','out']:p.add_argument('--'+key,required=True)
    a=p.parse_args();prepare(a.config,a.archive,a.weather,a.old_data,a.confirmation_masks,a.old_weather,a.new_weather,a.conflict_config,a.conflict_geometry,a.out)

if __name__=='__main__':main()
