import json
from pathlib import Path
import pandas as pd
import pytest
from firecast.acquire import fire_request,weather_request,nasa_download
from firecast.sources import SOURCES

def test_only_nasa_default_sources():
    from urllib.parse import urlparse
    assert all(urlparse(u).hostname.endswith('.nasa.gov') for u in SOURCES.values())
    with pytest.raises(ValueError,match='NASA-hosted'): nasa_download('https://example.org/file',Path('unused'))

def test_fire_country_csv_preserves_time_product_version(monkeypatch,tmp_path):
    raw=b'latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,type,frp\n33.9,35.5,2020-08-04,0006,N,VIIRS,n,2,0,5.1\n'
    p=tmp_path/'input.csv';p.write_bytes(raw)
    monkeypatch.setattr('firecast.acquire.nasa_download',lambda u,pth:p)
    frame,meta=fire_request(('viirs-snpp_2020_Lebanon.csv',len(raw),'date'),tmp_path)
    assert frame.detected_at.iloc[0]==pd.Timestamp('2020-08-04T00:06:00Z')
    assert meta['versions']==['2'] and frame.satellite.iloc[0]=='N'
    assert meta['rows']==1 and frame['type'].iloc[0]==0

def test_fire_country_csv_checks_inventory_size(monkeypatch,tmp_path):
    p=tmp_path/'input.csv';p.write_text('bad')
    monkeypatch.setattr('firecast.acquire.nasa_download',lambda u,pth:p)
    with pytest.raises(ValueError,match='byte-size'): fire_request(('modis_2020_Lebanon.csv',999,'date'),tmp_path)

def test_power_fill_utc_and_shifted_rain(monkeypatch,tmp_path):
    variables=['T2M','T2M_MAX','RH2M','PRECTOTCORR','WS10M','WD10M']
    dates=pd.date_range('2020-01-01','2020-01-09')
    raw={v:{t.strftime('%Y%m%d'):float(i+1) for i,t in enumerate(dates)} for v in variables}
    raw['T2M']['20200101']=-999
    payload={'header':{'fill_value':-999,'time_standard':'UTC'},'properties':{'parameter':raw},'parameters':{}}
    path=tmp_path/'power.json';path.write_text(json.dumps(payload))
    monkeypatch.setattr('firecast.acquire.nasa_download',lambda u,p:path)
    config=dict(weather_parameters=variables,weather_start='20200101',weather_end='20200109',weather_time_standard='UTC')
    frame,meta=weather_request((33.9,35.5),tmp_path,config)
    assert pd.isna(frame.T2M.iloc[0]) and meta['missing_by_variable']['T2M']==1
    assert frame.rain_preceding_7days_mm.iloc[7]==28 # 1..7, excludes target day's 8 mm
    assert frame.rain_preceding_7days_mm.iloc[:7].isna().all()
    payload['header']['time_standard']='LST';path.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='UTC'): weather_request((33.9,35.5),tmp_path,config)
