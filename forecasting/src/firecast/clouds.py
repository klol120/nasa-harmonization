"""Acquire public NASA cloud history; never equate daily means with swath coverage."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
import numpy as np
import pandas as pd
from .acquire import nasa_download

PARAMETERS=['CLOUD_AMT','CLOUD_AMT_DAY','CLOUD_AMT_NIGHT']

def cloud_point(point,config,out):
    lat,lon=point
    params={'parameters':','.join(PARAMETERS),'community':'AG','latitude':lat,'longitude':lon,
      'start':config['start'],'end':config['end'],'format':'JSON','time-standard':'UTC'}
    url='https://power.larc.nasa.gov/api/temporal/daily/point?'+urlencode(params)
    path=nasa_download(url,Path(out)/'raw'/f'cloud_{lat}_{lon}_{config["start"]}_{config["end"]}.json')
    payload=json.loads(path.read_text());header=payload['header']
    if header['time_standard']!='UTC':raise ValueError('Cloud intervals must be UTC')
    data=payload['properties']['parameter'];fill=header['fill_value'];rows=[]
    for day in pd.date_range(config['start'],config['end']):
        row={'cloud_point_id':f'{lat}_{lon}','lat':lat,'lon':lon,'date':str(day.date())}
        for name in PARAMETERS:
            if payload['parameters'][name]['units']!='%':raise ValueError('Cloud amount units must be percent')
            value=data[name].get(day.strftime('%Y%m%d'),fill)
            if value!=fill and not 0<=value<=100:raise ValueError('Cloud amount outside percent range')
            row[name]=np.nan if value==fill else value
        rows.append(row)
    frame=pd.DataFrame(rows)
    return frame,{'file':str(path),'url':url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'point':[lat,lon],'point_days':len(frame),'missing':frame[PARAMETERS].isna().sum().to_dict(),
      'header':header,'parameters':payload['parameters']}

def acquire_clouds(config_path,out):
    config=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
    frames=[];metadata=[];failures=[]
    def safe(point):
        try:return cloud_point(point,config,out),None
        except Exception as exc:return None,{'point':point,'error':str(exc)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result,error in pool.map(safe,[(a,b) for a in config['latitudes'] for b in config['longitudes']]):
            if error:failures.append(error)
            else:frames.append(result[0]);metadata.append(result[1])
    if frames:pd.concat(frames,ignore_index=True).to_csv(out/'cloud_history.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'config':config,'files':metadata,'failures':failures,
      'point_days':sum(len(f) for f in frames),'coverage_evidence_qualified':False,
      'purpose':'Historical cloud context; not a cloud forecast, full satellite mask, or negative-label authorization',
      'limitations':['Daily total/day/night percentages do not identify cloud at each fire-satellite overpass',
        'POWER SYN1DEG is coarse; nearby requests need not be independent cloud observations',
        'Historical availability/latency is not established by observation date','Missing values remain missing']}
    (out/'cloud-report.json').write_text(json.dumps(report,indent=2))
    return report

def attach_cloud_context(weather_path,cloud_path,out):
    from .data import km_distance
    weather=pd.read_csv(weather_path);clouds=pd.read_csv(cloud_path)
    points=clouds[['cloud_point_id','lat','lon']].drop_duplicates()
    links=[]
    for r in weather[['weather_point_id','lat','lon']].drop_duplicates().itertuples():
        dist=km_distance(points.lat,points.lon,r.lat,r.lon);i=dist.idxmin()
        links.append({'weather_point_id':r.weather_point_id,'cloud_point_id':points.loc[i,'cloud_point_id'],'cloud_sample_distance_km':float(dist.loc[i])})
    merged=weather.merge(pd.DataFrame(links),on='weather_point_id',validate='many_to_one')
    merged=merged.merge(clouds[['cloud_point_id','date',*PARAMETERS]],on=['cloud_point_id','date'],how='left',validate='many_to_one')
    merged['cloud_available_at']=None
    merged['cloud_role']='observed_historical_context_not_overpass_mask_or_forecast'
    merged.to_csv(out,index=False,compression={'method':'gzip','mtime':0})
    return merged

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=acquire_clouds(a.config,a.out);print(json.dumps({'point_days':r['point_days'],'failures':r['failures'],'coverage_evidence_qualified':False}))

if __name__=='__main__':main()
