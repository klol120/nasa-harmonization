"""Add genuine, already available 30-day history to a complete NASA GEOS input frame."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
import numpy as np
import pandas as pd
from .global_acquire import cached_json,now
from .global_data import add_features,FEATURES


def augment(input_path,out,lag=3):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);f=pd.read_csv(input_path)
    for col in ['prediction_time','history_end','history_available_at']:f[col]=pd.to_datetime(f[col],utc=True)
    if f.prediction_time.nunique()!=1:raise ValueError('One prediction window per transfer feature batch')
    prediction=f.prediction_time.iloc[0];end=prediction-pd.Timedelta(days=lag);start=end-pd.Timedelta(days=30)
    rows=[]
    for point in f[['weather_point_id','weather_lat','weather_lon']].drop_duplicates().itertuples():
        params={'parameters':'PRECTOTCORR,T2M','community':'AG','latitude':point.weather_lat,'longitude':point.weather_lon,'start':start.strftime('%Y%m%d'),'end':(end-pd.Timedelta(days=1)).strftime('%Y%m%d'),'format':'JSON','time-standard':'UTC'}
        path=out/'antecedent_raw'/f'{point.weather_point_id}-{start:%Y%m%d}-{end:%Y%m%d}.json.gz'
        raw=cached_json('https://power.larc.nasa.gov/api/temporal/daily/point?'+urlencode(params),path)
        meta=json.loads(path.with_suffix(path.suffix+'.manifest.json').read_text());available=pd.Timestamp(meta['downloaded_at'])
        if available>prediction:raise ValueError('History was not available at requested prediction time')
        if raw['header']['time_standard']!='UTC':raise ValueError('History must be UTC')
        keys=[d.strftime('%Y%m%d') for d in pd.date_range(start,periods=30,freq='D')];values=raw['properties']['parameter'];fill=raw['header']['fill_value']
        rain=np.array([values['PRECTOTCORR'].get(k,fill) for k in keys],dtype=float)
        temperature=np.array([values['T2M'].get(k,fill) for k in keys[-7:]],dtype=float)
        if not np.isfinite(rain).all() or (rain<0).any() or not np.isfinite(temperature).all() or (temperature==fill).any():raise ValueError('Incomplete actual antecedent history; cannot fill missing values')
        rows.append({'weather_point_id':point.weather_point_id,'rain7_mm':float(rain[-7:].sum()),'rain30_mm':float(rain.sum()),'temperature7_c':float(temperature.mean()),'history_end':end,'history_available_at':available})
    history=pd.DataFrame(rows)
    f=f.drop(columns=['rain7_mm','history_end','history_available_at']).merge(history,on='weather_point_id',validate='many_to_one')
    f['vpd_kpa']=.6108*np.exp(17.27*f.temperature_c/(f.temperature_c+237.3))*(1-f.humidity_pct/100)
    f=add_features(f)
    if not np.isfinite(f[FEATURES].to_numpy()).all():raise ValueError('Incomplete transfer inference features')
    f.to_csv(out/'forecast-features.csv',index=False)
    (out/'feature-report.json').write_text(json.dumps({'generated_at':now(),'cells':len(f),'prediction_time':str(prediction),'history_lag_days':lag,'feature_count':len(FEATURES),'mode':'Actual issued NASA forecast with unvalidated retrospective model transfer','production_validated':False},indent=2))
    return f


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--out',required=True);a=p.parse_args();f=augment(a.input,a.out);print('Transfer inference rows with actual history:',len(f))

if __name__=='__main__':main()
