"""Reproducible acquisition from public NASA FIRMS country files and NASA POWER.

Country 'yearly summaries' are per-detection CSV files, not monthly/annual totals.
No Earthdata credentials are required for this public route. Preserve provider bytes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode, urlparse
import urllib.request
import pandas as pd
import numpy as np
from .data import km_distance
from .sources import cached_download

FIRMS='https://firms.modaps.eosdis.nasa.gov/data/country/'

def nasa_download(url,path):
    if not urlparse(url).hostname.endswith('.nasa.gov'): raise ValueError('NASA-hosted sources only')
    error=None
    for attempt in range(3):
        try: return cached_download(url,path)
        except Exception as exc:
            error=exc
            if attempt<2: time.sleep(2**attempt)
    raise error

def fire_request(item,out):
    name,size,updated=item;product,year=name.split('_')[:2]
    url=f'{FIRMS}{product}/{year}/{name}';path=nasa_download(url,out/'raw/firms'/name)
    if path.stat().st_size!=int(size): raise ValueError(f'Listing byte-size mismatch: {name}; refresh inventory')
    f=pd.read_csv(path, dtype={'acq_time':str,'version':str,'confidence':str})
    required={'latitude','longitude','acq_date','acq_time','satellite','instrument','confidence','version','type','frp'}
    if not required<=set(f): raise ValueError(f'Unexpected FIRMS schema {name}')
    if not f.latitude.between(-90,90).all() or not f.longitude.between(-180,180).all(): raise ValueError('Invalid coordinate')
    hh=f.acq_time.str.zfill(4)
    f['detected_at']=pd.to_datetime(f.acq_date+'T'+hh.str[:2]+':'+hh.str[2:]+':00Z',utc=True,errors='raise')
    if not f.detected_at.dt.year.eq(int(year)).all(): raise ValueError('Unexpected acquisition year')
    f['source_file']=name;f['source_url']=url;f['product']=product
    # Keep each provider version/platform; duplicate removal belongs to an audited downstream step.
    return f,{'file':name,'url':url,'listing_updated_at':updated,'rows':len(f),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'versions':sorted(f.version.unique().tolist()),'satellites':sorted(f.satellite.astype(str).unique().tolist())}

def weather_request(item,out,config):
    lat,lon=item;params=dict(parameters=','.join(config['weather_parameters']),community='AG',longitude=lon,latitude=lat,start=config['weather_start'],end=config['weather_end'],format='JSON')
    params['time-standard']=config['weather_time_standard']
    url='https://power.larc.nasa.gov/api/temporal/daily/point?'+urlencode(params)
    name=f'power_{lat}_{lon}_{config["weather_start"]}_{config["weather_end"]}.json'
    path=nasa_download(url,out/'raw/power'/name);payload=json.loads(path.read_text())
    if payload.get('header',{}).get('time_standard')!='UTC': raise ValueError('POWER did not return UTC daily data')
    raw=payload['properties']['parameter'];fill=payload['header']['fill_value'];rows=[]
    dates=pd.date_range(config['weather_start'],config['weather_end'],freq='D')
    for day in dates:
        key=day.strftime('%Y%m%d'); row={'weather_point_id':f'{lat}_{lon}','lat':lat,'lon':lon,'date':str(day.date())}
        for variable in config['weather_parameters']:
            value=raw[variable].get(key,fill);row[variable]=np.nan if value==fill else value
        rows.append(row)
    frame=pd.DataFrame(rows)
    # Antecedent summaries exclude the target day. They still need actual availability metadata.
    frame['rain_preceding_7days_mm']=frame.PRECTOTCORR.shift(1).rolling(7,min_periods=7).sum()
    angle=np.radians(frame.WD10M)
    frame['wind_u_ms']=-frame.WS10M*np.sin(angle);frame['wind_v_ms']=-frame.WS10M*np.cos(angle)
    return frame,{'file':name,'url':url,'rows':len(frame),'missing_by_variable':frame[config['weather_parameters']].isna().sum().to_dict(),'parameters':payload.get('parameters'),'header':payload.get('header'),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def geos_snapshot(out, config):
    """One immutable issue-indexed NetCDF sample, not a multi-year forecast archive."""
    issue=config['geos_issue'];valid=config['geos_valid']
    issued=datetime.strptime(issue,'%Y%m%d_%H').replace(tzinfo=timezone.utc)
    valid_at=datetime.strptime(valid,'%Y%m%d_%H%M').replace(tzinfo=timezone.utc)
    if valid_at<=issued: raise ValueError('GEOS forecast valid time must follow issue')
    directory=f'Y{issued:%Y}/M{issued:%m}/D{issued:%d}/H{issued:%H}/'
    name=f'GEOS.fp.fcst.tavg1_2d_slv_Nx.{issue}+{valid}.V01.nc4'
    url='https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/forecast/'+directory+name.replace('+','%2B')
    path=nasa_download(url,Path(out)/'raw/geos'/name)
    with path.open('rb') as handle:
        if handle.read(8)!=b'\x89HDF\r\n\x1a\n': raise ValueError('GEOS response is not an HDF5/NetCDF4 file')
    return {'url':url,'path':str(path),'issue_time':issued.isoformat(),'valid_midpoint':valid_at.isoformat(),
        'lead_hours':(valid_at-issued).total_seconds()/3600,'available_at_evidence':'download timestamp in manifest only; historical dissemination lag not verified',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
        'status':'Real global one-hour-mean forecast sample; not a complete daily window or historical training archive',
        'spatial_resolution_deg':[.25,.3125],'collection':'tavg1_2d_slv_Nx','regional_decoding':'Not performed; preserve raw NetCDF4'}


def acquire(config_path,out):
    config=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
    listing=nasa_download(FIRMS+'yearly_summary_files.txt',out/'raw/firms/yearly_summary_files.txt')
    nasa_download(FIRMS+'AttributesReadme.txt',out/'raw/firms/AttributesReadme.txt')
    table=pd.read_csv(listing);selected=[]
    for r in table.itertuples(index=False):
        name=r.filename;parts=name.removesuffix('.csv').split('_')
        if name.endswith('.csv') and len(parts)>=3 and parts[0] in config['fire_products'] and '_'.join(parts[2:]) in config['countries'] and config['fire_start_year']<=int(parts[1])<=config['fire_end_year']:
            selected.append((name,r.size,r.updated))
    if not selected: raise ValueError('No matching public country files')
    fire_frames=[];fire_meta=[];failures=[]
    def fire_safe(item):
        try: return fire_request(item,out),None
        except Exception as exc: return None,{'file':item[0],'error':str(exc)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result,error in pool.map(fire_safe,selected):
            if error: failures.append(error);print('Failed:',error,flush=True)
            else:
                frame,meta=result;fire_frames.append(frame);fire_meta.append(meta);print('FIRMS',meta['file'],meta['rows'],flush=True)
    if not fire_frames: raise ValueError('No valid FIRMS downloads')
    fires=pd.concat(fire_frames,ignore_index=True)
    fires.to_csv(out/'detections_raw_combined.csv',index=False)
    # Export the pipeline contract with original platform/product and every flag provenance intact.
    canonical=fires.rename(columns={'latitude':'lat','longitude':'lon','instrument':'sensor','version':'processing_version'}).copy()
    canonical['detection_id']=[hashlib.sha256(f'{r.product}|{r.satellite}|{r.processing_version}|{r.detected_at}|{r.lat}|{r.lon}'.encode()).hexdigest()[:24] for r in canonical.itertuples()]
    canonical['flag_level']='unflagged';canonical['flag_reason']='';canonical['flag_source']=canonical.source_file
    canonical.to_csv(out/'detections.csv',index=False)
    counts=fires.groupby(['product',fires.detected_at.dt.year.rename('year')]).size().rename('detections').reset_index()
    counts.to_csv(out/'fire_counts_by_year.csv',index=False)
    hits=fires[(fires.detected_at>=pd.Timestamp('2020-08-04T14:00:00Z'))&(fires.detected_at<pd.Timestamp('2020-08-05T18:00:00Z'))].copy()
    hits['distance_to_port_km']=km_distance(hits.latitude,hits.longitude,33.901,35.519)
    hits=hits[hits.distance_to_port_km<=3];hits.to_csv(out/'beirut_port_review_hits.csv',index=False)
    weather_frames=[];weather_meta=[]
    def weather_safe(item):
        try: return weather_request(item,out,config),None
        except Exception as exc:return None,{'point':list(item),'error':str(exc)}
    points=[(lat,lon) for lat in config['weather_latitudes'] for lon in config['weather_longitudes']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result,error in pool.map(weather_safe,points):
            if error:failures.append(error);print('Failed:',error,flush=True)
            else:
                frame,meta=result;weather_frames.append(frame);weather_meta.append(meta);print('POWER',meta['file'],meta['rows'],flush=True)
    if weather_frames:pd.concat(weather_frames,ignore_index=True).to_csv(out/'weather_historical.csv',index=False)
    report={'schema_version':1,'retrieved_at':datetime.now(timezone.utc).isoformat(),'config':config,'fire_files':fire_meta,'weather_files':weather_meta,'failures':failures,
      'fire_detection_rows':len(fires),'duplicates_within_product':int(fires.duplicated(['product','satellite','version','latitude','longitude','detected_at']).sum()),
      'fire_first_detection':str(fires.detected_at.min()),'fire_last_detection':str(fires.detected_at.max()),
      'beirut_review':{'radius_km':3,'center':[35.519,33.901],'start':'2020-08-04T14:00:00Z','end_exclusive':'2020-08-05T18:00:00Z','detections':len(hits),'attribution':'Spatial-temporal association only; no cause inferred'},
      'limitations':['POWER is historical observed/reanalysis-derived weather, NOT a forecast','FIRMS country fire detections do not supply clear-land coverage or negative labels','Do not train operational risk probabilities without the missing label/forecast evidence','Country membership follows NASA country files; the weather bounding rectangle includes non-Lebanese points','Dates not containing detections do not prove a fire did not occur','No real incident-model training or evaluation performed by this acquisition command']}
    if config.get('download_geos_snapshot',False):
        try: report['forecast_snapshot']=geos_snapshot(out,config)
        except Exception as exc: report['failures'].append({'source':'GEOS snapshot','error':str(exc)})
    (out/'acquisition-report.json').write_text(json.dumps(report,indent=2,default=str,allow_nan=False))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    acquire(a.config,a.out)

if __name__=='__main__':main()
