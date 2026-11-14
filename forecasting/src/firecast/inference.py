"""Inference from one normalized feature row per cell/window; no label/event inputs."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from .data import grid_id,WEATHER,ENV
from .models import features
from shapely.geometry import shape,box,mapping,Point

TIMES=['prediction_time','issue_time','available_at','valid_start','valid_end','history_end','history_available_at','environment_available_at','environment_observed_at','static_available_at']

def predict_frame(artifact,frame,location=None,strict_domain=False):
    config=artifact['config'];f=frame.copy()
    time_columns=['prediction_time','issue_time','available_at','valid_start','valid_end']
    if 'rain7_mm' in artifact['features']: time_columns+=['history_end','history_available_at']
    if set(artifact['features'])&set(ENV): time_columns+=['static_available_at']
    if 'ndvi' in artifact['features']:time_columns+=['environment_available_at','environment_observed_at']
    required=['cell_id','lat','lon','region',*time_columns,*[c for c in artifact['features'] if c not in {'month','season_sin','season_cos'}]]
    if set(required)-set(f): raise ValueError(f'Missing columns: {set(required)-set(f)}')
    for col in time_columns:f[col]=pd.to_datetime(f[col],utc=True,errors='raise')
    if f.duplicated(['cell_id','prediction_time']).any(): raise ValueError('Duplicate inference windows')
    if location:
        cid=grid_id(*location,config['grid_deg']);f=f[f.cell_id==cid].copy()
        if f.empty: raise ValueError('Location has no supplied grid features')
    f=features(f); output=[]
    for _,r in f.iterrows():
        flags=[]; t=r.prediction_time;end=t+pd.Timedelta(hours=config['horizon_hours'])
        if not r.cell_id==grid_id(r.lat,r.lon,config['grid_deg']): raise ValueError('Grid mismatch')
        if r.issue_time>t or r.available_at>t: flags.append('forecast_unavailable_at_prediction')
        if r.available_at<r.issue_time:flags.append('forecast_available_before_issue')
        if (t-r.issue_time)>pd.Timedelta(hours=config.get('max_issue_age_hours',24)):flags.append('forecast_issue_too_old')
        if r.valid_start!=t or r.valid_end!=end: flags.append('forecast_window_mismatch')
        for col in [c for c in time_columns if c not in {'prediction_time','issue_time','available_at','valid_start','valid_end'}]:
            if pd.isna(r[col]) or r[col]>t: flags.append(f'unavailable_{col}')
        if any(pd.isna(r[c]) for c in time_columns): flags.append('missing_timestamp')
        if not np.isfinite(r[artifact['features']].to_numpy(dtype=float)).all(): flags.append('missing_input')
        if r.region!='lebanon': flags.append('outside_validated_region')
        if any(r[c]<lo or r[c]>hi for c,(lo,hi) in artifact['bounds'].items()): flags.append('outside_training_feature_range')
        if 'ndvi' in artifact['features'] and (t-r.environment_observed_at)>pd.Timedelta(days=60): flags.append('vegetation_older_than_60_days')
        if 'validated_cells' in artifact and r.cell_id not in artifact['validated_cells']:flags.append('outside_validated_cell_grid')
        if 'validated_products' in artifact and r.get('observation_product') not in artifact['validated_products']:flags.append('outside_validated_observation_product')
        if 'validated_weather_sources' in artifact and r.get('weather_source') not in artifact['validated_weather_sources']:flags.append('outside_validated_weather_source')
        if 'analysis_geometry' in artifact and not shape(artifact['analysis_geometry']).covers(Point(r.lon,r.lat)):flags.append('outside_country_geometry')
        fatal=any(s.startswith(('forecast_','unavailable_','missing_')) for s in flags)
        if 'outside_country_geometry' in flags or 'outside_validated_observation_product' in flags:fatal=True
        if strict_domain and flags:fatal=True
        p=None if fatal else float(artifact['model'].predict_proba(pd.DataFrame([r])[artifact['features']])[0,1])
        if config['synthetic']: flags.append('SYNTHETIC_MODEL_NOT_VALIDATED')
        if config['mode']=='retrospective': flags.append('RETROSPECTIVE_MODEL_NOT_OPERATIONALLY_VALIDATED')
        if config.get('prediction_scope'):flags.append('COVERAGE_CONDITIONAL_RESEARCH_ESTIMATE')
        output.append({'cell_id':r.cell_id,'lat':float(r.lat),'lon':float(r.lon),'prediction_time':str(t),'window_end':str(end),
          'prediction_scope':config.get('prediction_scope','detected_fire_occurrence_research'),'label_product':config.get('label_product','configured fixture target'),'validation_mode':config['mode'],
          'probability':p,'above_validation_threshold':None if p is None else p>=artifact['threshold'],
          'threshold':artifact['threshold'],'model_version':artifact.get('version',artifact['id']),'issue_time':str(r.issue_time),
          'weather_available_at':str(r.available_at),'environment_available_at':str(r.get('environment_available_at','not_used')),
          'history_available_at':str(r.get('history_available_at','not_used')),'flags':';'.join(flags)})
    if not output: raise ValueError('No inference rows')
    return output

def predict(model_path,input_path,out,location=None):
    artifact=joblib.load(model_path) # trusted locally produced artifacts only
    config=artifact['config']
    output=predict_frame(artifact,pd.read_csv(input_path),location)
    out=Path(out);out.mkdir(parents=True,exist_ok=True);pd.DataFrame(output).to_csv(out/'risk.csv',index=False)
    geo=[];step=config['grid_deg']
    for row in output:
        i,j=map(int,row['cell_id'].split('_'));south=i*step-90;west=j*step-180
        ring=[[west,south],[west+step,south],[west+step,south+step],[west,south+step],[west,south]]
        geometry=box(west,south,west+step,south+step)
        if 'analysis_geometry' in artifact:geometry=geometry.intersection(shape(artifact['analysis_geometry']))
        geo.append({'type':'Feature','properties':row,'geometry':mapping(geometry)})
    (out/'risk.geojson').write_text(json.dumps({'type':'FeatureCollection','features':geo},indent=2,allow_nan=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.colors import Normalize
    finite=[r['probability'] for r in output if r['probability'] is not None]
    upper=min(1,max([artifact['threshold'],*finite,1e-6]))
    fig,ax=plt.subplots(figsize=(7,6)); norm=Normalize(0,upper)
    for feature in geo:
        geometry=shape(feature['geometry']);p=feature['properties']['probability']
        polygons=list(geometry.geoms) if geometry.geom_type=='MultiPolygon' else [geometry]
        for polygon in polygons:
            if not polygon.is_empty:ax.add_patch(Polygon(list(polygon.exterior.coords),facecolor='grey' if p is None else plt.cm.YlOrRd(norm(p)),edgecolor='black'))
    ax.autoscale();ax.set_aspect(1/np.cos(np.radians(34)));ax.set_xlabel('Longitude');ax.set_ylabel('Latitude')
    ax.set_title(('SYNTHETIC DEMONSTRATION\n' if config['synthetic'] else 'RETROSPECTIVE MODEL — RESEARCH ONLY\n')+'Satellite-detected vegetation-fire probability\n'+str(output[0]['prediction_time'])+'\nSupplied vegetation cells; grey = unavailable')
    if config.get('prediction_scope'):
        fig.text(.5,.01,'Conditional on daily observation coverage; live GEOS transfer unvalidated',ha='center',fontsize=8)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='YlOrRd'),ax=ax,label='Probability in forecast window');fig.tight_layout();fig.savefig(out/'risk.png',dpi=160);plt.close(fig)
    return output

def overlay(risk_path,assets_path,out,buffer_km=1):
    """Conservative bbox overlap for point/line assets. Exposure screening, not spread."""
    if buffer_km<0: raise ValueError('Nonnegative buffer required')
    risk=json.loads(Path(risk_path).read_text());assets=json.loads(Path(assets_path).read_text());found=[]
    for asset in assets['features']:
        geom=asset['geometry']
        if geom['type'] not in {'Point','LineString'}: raise ValueError('Overlay supports Point/LineString WGS84 assets')
        points=[geom['coordinates']] if geom['type']=='Point' else geom['coordinates']
        x,y=zip(*points);matches=[]
        for cell in risk['features']:
            if cell['properties']['above_validation_threshold'] is not True: continue
            geometry=shape(cell['geometry'])
            if geometry.is_empty:continue
            west,south,east,north=geometry.bounds;dy=buffer_km/111;dx=dy/np.cos(np.radians((south+north)/2))
            if max(x)>=west-dx and min(x)<=east+dx and max(y)>=south-dy and min(y)<=north+dy: matches.append(cell['properties']['cell_id'])
        if matches:
            asset['properties']=dict(asset.get('properties') or {},near_high_risk_cells=matches,method='buffered bbox screening; may overselect',buffer_km=buffer_km)
            found.append(asset)
    Path(out).write_text(json.dumps({'type':'FeatureCollection','features':found},indent=2))
