"""Normalize complete NASA forecast windows and genuine available antecedent history."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
import h5py
import numpy as np
import pandas as pd
from .geos import decode_hour,aggregate_window,text_attr
from .acquire import nasa_download


def auxiliary_hour(path,cells,variable,unit):
    rows=[]
    with h5py.File(path) as f:
        if text_attr(f[variable].attrs['units'])!=unit:raise ValueError('Unexpected auxiliary forecast units')
        lat=f['lat'][:];lon=f['lon'][:];array=f[variable][0,:,:]
        for r in cells.itertuples():
            i=int(np.argmin(abs(lat-r.lat)));j=int(np.argmin(abs(lon-r.lon)));value=float(array[i,j])
            if not np.isfinite(value) or abs(value)>1e10:raise ValueError('Missing auxiliary forecast value')
            if variable=='PRECTOT':
                if value<0:raise ValueError('Negative precipitation rate')
                value*=3600 # kg m-2 s-1 averaged over one hour -> mm/hour
            elif variable=='CLDTOT' and not 0<=value<=1:raise ValueError('Cloud fraction outside [0,1]')
            rows.append(value)
    return rows


def recent_rain(cells,prediction_time,history_lag_days,out):
    prediction=pd.Timestamp(prediction_time);end=prediction-pd.Timedelta(days=history_lag_days);start=end-pd.Timedelta(days=7)
    if end>pd.Timestamp(datetime.now(timezone.utc)).floor('D'):raise ValueError('Requested recent history is not yet fully observed')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);rows=[]
    # Reuse the coarse sampling grid, rather than fetching the same weather field per fine cell.
    points=cells[['weather_point_id','weather_lat','weather_lon']].drop_duplicates()
    for p in points.itertuples():
        params={'parameters':'PRECTOTCORR','community':'AG','latitude':p.weather_lat,'longitude':p.weather_lon,'start':start.strftime('%Y%m%d'),'end':(end-pd.Timedelta(days=1)).strftime('%Y%m%d'),'format':'JSON','time-standard':'UTC'}
        url='https://power.larc.nasa.gov/api/temporal/daily/point?'+urlencode(params)
        file=nasa_download(url,out/f'rain_{p.weather_point_id}_{start:%Y%m%d}_{end:%Y%m%d}.json')
        raw=json.loads(file.read_text());values=raw['properties']['parameter']['PRECTOTCORR']
        expected=[t.strftime('%Y%m%d') for t in pd.date_range(start,periods=7,freq='D')]
        if raw['header']['time_standard']!='UTC' or any(k not in values or values[k]==raw['header']['fill_value'] or values[k]<0 for k in expected):raise ValueError('Incomplete genuine antecedent rainfall; no zero filling allowed')
        manifest=json.loads(file.with_suffix(file.suffix+'.manifest.json').read_text());available=pd.Timestamp(manifest['downloaded_at'])
        if available>prediction:raise ValueError('Antecedent data retrieved after prediction; cannot backdate')
        rows.append({'weather_point_id':p.weather_point_id,'rain7_mm':sum(values[k] for k in expected),'history_end':end,'history_available_at':available})
    return pd.DataFrame(rows)


def build_features(forecast_dir,cells_path,environment,out,history_lag_days=3,observation_product='VJ114A1.002'):
    forecast_dir=Path(forecast_dir);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report=json.loads((forecast_dir/'forecast-report.json').read_text())
    if not report['complete']:raise ValueError('Forecast archive incomplete')
    cells=pd.read_csv(cells_path);hourlies=[];files=forecast_dir/'subsets'
    # Preserve the historical POWER grid for the rainfall feature definition.
    historical=pd.read_csv(Path(environment).parent/'nasa-lebanon/weather_historical.csv',usecols=['weather_point_id','lat','lon']).drop_duplicates()
    from .data import km_distance
    links=[]
    for r in cells.itertuples():
        distances=km_distance(historical.lat,historical.lon,r.lat,r.lon);p=historical.loc[distances.idxmin()]
        links.append({'cell_id':r.cell_id,'weather_point_id':p.weather_point_id,'weather_lat':p.lat,'weather_lon':p.lon})
    cells=cells.merge(pd.DataFrame(links),on='cell_id',validate='one_to_one')
    for path in sorted(files.glob('*_slv_*.nc4')):
        meta=json.loads(path.with_suffix(path.suffix+'.manifest.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Subset checksum mismatch')
        frame=decode_hour(path,cells,meta['downloaded_at'])
        flux=files/path.name.replace('_slv_','_flx_');rad=files/path.name.replace('_slv_','_rad_')
        for auxiliary in [flux,rad]:
            m=json.loads(auxiliary.with_suffix(auxiliary.suffix+'.manifest.json').read_text())
            if hashlib.sha256(auxiliary.read_bytes()).hexdigest()!=m['sha256']:raise ValueError('Auxiliary subset checksum mismatch')
            frame['available_at']=max(pd.Timestamp(m['downloaded_at']),pd.Timestamp(frame.available_at.iloc[0]))
        frame['precip_mm']=auxiliary_hour(flux,cells,'PRECTOT','kg m-2 s-1')
        frame['forecast_cloud_fraction']=auxiliary_hour(rad,cells,'CLDTOT','1')
        hourlies.append(frame)
    hourly=pd.concat(hourlies,ignore_index=True)
    aggregate=aggregate_window(hourly,report['prediction_time'],report['horizon_hours'])
    clouds=hourly.groupby('cell_id').forecast_cloud_fraction.mean().rename('forecast_cloud_fraction').reset_index()
    rain=recent_rain(cells,report['prediction_time'],history_lag_days,out/'antecedent_raw')
    aggregate=aggregate.merge(clouds,on='cell_id',validate='one_to_one').merge(cells,on='cell_id',validate='one_to_one').merge(rain,on='weather_point_id',validate='many_to_one')
    timestamps=[]
    for manifest in (Path(environment)/'raw').glob('*.manifest.json'):
        timestamps.append(pd.Timestamp(json.loads(manifest.read_text())['downloaded_at']))
    aggregate['static_available_at']=max(timestamps)
    aggregate['observation_product']=observation_product
    aggregate['source_note']='Actual issued NASA GEOS forecast; historical model validation may remain retrospective'
    aggregate.to_csv(out/'forecast-features.csv',index=False)
    meta={'cells':len(aggregate),'issue_time':report['issue_time'],'prediction_time':report['prediction_time'],'complete_window':True,
      'history_lag_days':history_lag_days,'forecast_cloud_role':'Coarse forecast context, not a guarantee of future satellite observation coverage',
      'validated_model':False,'source_forecast_report_sha256':hashlib.sha256((forecast_dir/'forecast-report.json').read_bytes()).hexdigest()}
    (out/'feature-report.json').write_text(json.dumps(meta,indent=2))
    return aggregate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--forecast-dir',required=True);p.add_argument('--cells',required=True);p.add_argument('--environment',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    f=build_features(a.forecast_dir,a.cells,a.environment,a.out);print('Complete issued-forecast feature rows:',len(f))

if __name__=='__main__':main()
