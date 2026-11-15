from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import h5py
import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.dummy import DummyClassifier
from firecast.clouds import cloud_point
from firecast.geos import decode_hour,aggregate_window
from firecast import forecast_acquire
from firecast.masks import swath_evidence
from firecast.release import assess_release,REQUIRED_EVIDENCE,EXPECTED_CHECKS
from firecast.service import create_app,load_release
from firecast.data import grid_id


def test_cloud_sentinel_and_units(monkeypatch,tmp_path):
    params=['CLOUD_AMT','CLOUD_AMT_DAY','CLOUD_AMT_NIGHT']
    payload={'header':{'time_standard':'UTC','fill_value':-999,'sources':['SYN1DEG','POWER']},
      'parameters':{c:{'units':'%'} for c in params},'properties':{'parameter':{c:{'20200101':-999,'20200102':20} for c in params}}}
    path=tmp_path/'cloud.json';path.write_text(json.dumps(payload));monkeypatch.setattr('firecast.clouds.nasa_download',lambda u,p:path)
    frame,meta=cloud_point((33.5,35.5),{'start':'20200101','end':'20200102'},tmp_path)
    assert frame.CLOUD_AMT.isna().iloc[0] and frame.CLOUD_AMT.iloc[1]==20 and meta['missing']['CLOUD_AMT']==1
    payload['properties']['parameter']['CLOUD_AMT']['20200102']=110;path.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='percent range'):cloud_point((33.5,35.5),{'start':'20200101','end':'20200102'},tmp_path)


def test_next_day_archive_retries_older_cycles_and_requires_on_time_retrieval(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(forecast_acquire, "source_exists", lambda url: "/D15/H12/" not in url)

    def acquire(issue, prediction, horizon, bbox, out):
        calls.append((issue, prediction, horizon, out))
        retrieved = prediction if issue.endswith("06:00:00+00:00") else "2026-11-15T17:00:00Z"
        return {"complete": True, "subsets": [{"downloaded_at": retrieved}]}

    monkeypatch.setattr(forecast_acquire, "acquire_forecast", acquire)
    assert forecast_acquire.archive_next_day(tmp_path, now="2026-11-15T16:45:00Z")
    assert [call[0] for call in calls] == ["2026-11-15T06:00:00+00:00", "2026-11-15T00:00:00+00:00"]
    assert all(call[1:3] == ("2026-11-16T00:00:00+00:00", 24) for call in calls)
    assert calls[-1][-1] == tmp_path / "20261116" / "20261115-00"


def geos_fixture(tmp_path):
    path=tmp_path/'GEOS.fp.fcst.tavg1_2d_slv_Nx.20200101_00+20200102_0030.V01.nc4'
    with h5py.File(path,'w') as f:
        f.create_dataset('lat',data=[33.5,34.5]);f.create_dataset('lon',data=[35.5,36.5])
        time=f.create_dataset('time',data=[0]);time.attrs['units']='minutes since 2020-01-02 00:30:00'
        for name,value,unit in [('T2M',280,'K'),('QV2M',.005,'kg kg-1'),('PS',100000,'Pa'),('U10M',3,'m s-1'),('V10M',4,'m s-1')]:
            ds=f.create_dataset(name,data=np.full((1,2,2),value));ds.attrs['units']=unit;ds.attrs['_FillValue']=1e15
    return path


def test_geos_units_timestamp_and_humidity(tmp_path):
    path=geos_fixture(tmp_path);cells=pd.DataFrame([{'cell_id':'x','lat':33.8,'lon':35.8}])
    f=decode_hour(path,cells,'2020-01-01T12:00Z')
    assert f.temperature_c.iloc[0]==pytest.approx(6.85) and 0<f.humidity_pct.iloc[0]<100
    assert f.valid_start.iloc[0]==pd.Timestamp('2020-01-02T00:00Z') and f.lead_hours.iloc[0]==24.5
    with h5py.File(path,'r+') as h:h['T2M'].attrs['units']='C'
    with pytest.raises(ValueError,match='unit mismatch'):decode_hour(path,cells,'2020-01-01T12:00Z')


def test_geos_requires_complete_single_issue_forecast():
    t=pd.Timestamp('2020-01-02',tz='UTC');f=pd.DataFrame({'cell_id':['x']*24,'issue_time':[t-pd.Timedelta(hours=12)]*24,'available_at':[t-pd.Timedelta(hours=10)]*24,
      'valid_start':pd.date_range(t,periods=24,freq='h'),'valid_end':pd.date_range(t+pd.Timedelta(hours=1),periods=24,freq='h'),
      'temperature_c':[20]*24,'humidity_pct':[40]*24,'wind_u_ms':[3]*24,'wind_v_ms':[4]*24,'precip_mm':[1]*24})
    assert aggregate_window(f,t).precip_mm.iloc[0]==24
    with pytest.raises(ValueError,match='complete'):aggregate_window(f.iloc[:-1],t)
    f.loc[0,'issue_time']=t-pd.Timedelta(hours=6)
    with pytest.raises(ValueError,match='complete'):aggregate_window(f,t)


def test_swath_cloud_counts_remain_unqualified(tmp_path):
    mask=tmp_path/'VNP14IMG.A2019213.0948.002.fixture.nc';geo=tmp_path/'VNP03IMG.A2019213.0948.002.fixture.nc'
    with h5py.File(mask,'w') as f:f.create_dataset('fire_mask',data=[[4,5],[8,0]])
    with h5py.File(geo,'w') as f:
        f.create_dataset('latitude',data=np.full((2,2),33.85));f.create_dataset('longitude',data=np.full((2,2),35.55))
    out=swath_evidence(mask,geo,{'bbox':[35,33,37,35],'grid_deg':.1})
    assert out.sampled_pixels.iloc[0]==4 and out.cloud_fraction_of_sampled_pixels.iloc[0]==.25
    assert out.fire_pixels.iloc[0]==1 and not out.coverage_evidence_qualified.any()
    wrong=tmp_path/'VNP03IMG.A2019213.0954.002.fixture.nc'
    with pytest.raises(ValueError,match='times must match'):swath_evidence(mask,wrong,{'bbox':[35,33,37,35],'grid_deg':.1})


def qualified_evaluation_fixture():
    return {'synthetic':False,'mode':'archived_forecast','evidence':{k:{'passed':True,'source':'TEST FIXTURE ONLY'} for k in REQUIRED_EVIDENCE},
      'test':{'positive_windows':300,'start':'2023-01-01T00:00:00Z','end':'2026-01-01T00:00:00Z','pr_auc_average_precision':.3,'brier':.04},
      'baseline_test':{'pr_auc_average_precision':.1,'brier':.05},'validated_cells':['x'],'validated_products':['viirs-jpss1'],'validated_weather_sources':['NASA_GEOS_FP']}


def test_release_requires_evidence_and_improvement():
    e=qualified_evaluation_fixture();assert assess_release(e)['approved']
    e['synthetic']=True;assert not assess_release(e)['approved']
    e['synthetic']=False;e['test']['brier']=.06;assert not assess_release(e)['approved']
    e['test']['brier']=.04;e['evidence']['issued_forecast_backtest']['source']='';assert not assess_release(e)['approved']


@pytest.fixture
def service_files(tmp_path):
    cid=grid_id(33.85,35.55,.1)
    model=DummyClassifier(strategy='prior').fit(pd.DataFrame({'temperature_c':[-10,10]}),[0,1])
    artifact={'model':model,'id':'TEST_ONLY','version':'TEST_ONLY','features':['temperature_c'],'threshold':.5,
      'bounds':{'temperature_c':[-10,10]},'config':{'synthetic':False,'mode':'archived_forecast','grid_deg':.1,'horizon_hours':24}}
    path=tmp_path/'model.joblib';joblib.dump(artifact,path)
    release={'approved':True,'checks':{k:True for k in EXPECTED_CHECKS},'model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'validated_cells':[cid],'validated_products':['viirs-jpss1'],'validated_weather_sources':['NASA_GEOS_FP']}
    manifest=tmp_path/'release.json';manifest.write_text(json.dumps(release))
    return path,manifest,artifact


def test_api_liveness_does_not_claim_readiness():
    with TestClient(create_app(api_key='test')) as c:
        assert c.get('/healthz').status_code==200
        assert c.get('/readyz').status_code==503
        assert c.post('/forecast',json={'records':[{}]}).status_code==503


def test_api_auth_and_domain_withholding(service_files):
    model,manifest,_=service_files
    t=pd.Timestamp(datetime.now(timezone.utc)).floor('h')
    row={'cell_id':grid_id(33.85,35.55,.1),'lat':33.85,'lon':35.55,'region':'lebanon','prediction_time':str(t),
      'issue_time':str(t-pd.Timedelta(hours=2)),'available_at':str(t-pd.Timedelta(hours=1)),'valid_start':str(t),'valid_end':str(t+pd.Timedelta(hours=24)),
      'temperature_c':0,'observation_product':'viirs-jpss1','weather_source':'NASA_GEOS_FP'}
    with TestClient(create_app(str(model),str(manifest),'test-key')) as c:
        assert c.get('/readyz').status_code==200
        assert c.post('/forecast',json={'records':[row]}).status_code==401
        r=c.post('/forecast',json={'records':[row]},headers={'x-api-key':'test-key'});assert r.status_code==200
        assert r.json()['predictions'][0]['probability']==.5
        row['weather_source']='NASA_POWER_OBSERVED'
        r=c.post('/forecast',json={'records':[row]},headers={'x-api-key':'test-key'})
        assert r.json()['predictions'][0]['probability'] is None
        row['issue_time']=str(t+pd.Timedelta(days=1))
        assert c.post('/forecast',json={'records':[row]},headers={'x-api-key':'test-key'}).status_code==422


def test_synthetic_release_and_tampering_rejected(service_files):
    model,manifest,artifact=service_files
    artifact['config']['synthetic']=True;joblib.dump(artifact,model)
    release=json.loads(manifest.read_text());release['model_sha256']=hashlib.sha256(model.read_bytes()).hexdigest();manifest.write_text(json.dumps(release))
    assert load_release(model,manifest)[1]==['synthetic_model_forbidden']
    release['model_sha256']='wrong';manifest.write_text(json.dumps(release))
    assert load_release(model,manifest)[1]==['model_checksum_mismatch']

def test_cloud_join_does_not_fabricate_availability(tmp_path):
    from firecast.clouds import attach_cloud_context
    w=tmp_path/'weather.csv';c=tmp_path/'cloud.csv'
    pd.DataFrame([{'weather_point_id':'a','lat':33.8,'lon':35.8,'date':'2020-01-01'}]).to_csv(w,index=False)
    pd.DataFrame([{'cloud_point_id':'b','lat':33.5,'lon':35.5,'date':'2020-01-01','CLOUD_AMT':20,'CLOUD_AMT_DAY':25,'CLOUD_AMT_NIGHT':15}]).to_csv(c,index=False)
    f=attach_cloud_context(w,c,tmp_path/'joined.csv.gz')
    assert len(f)==1 and f.CLOUD_AMT.iloc[0]==20 and f.cloud_available_at.isna().all()
    assert f.cloud_sample_distance_km.iloc[0]>0


def test_old_or_impossible_forecast_is_withheld(service_files):
    from firecast.inference import predict_frame
    _,_,artifact=service_files
    t=pd.Timestamp('2020-01-02T00:00:00Z')
    row={'cell_id':grid_id(33.85,35.55,.1),'lat':33.85,'lon':35.55,'region':'lebanon','prediction_time':t,
      'issue_time':t-pd.Timedelta(hours=48),'available_at':t-pd.Timedelta(hours=47),'valid_start':t,'valid_end':t+pd.Timedelta(hours=24),'temperature_c':0}
    result=predict_frame(artifact,pd.DataFrame([row]))[0]
    assert result['probability'] is None and 'forecast_issue_too_old' in result['flags']
    row.update(issue_time=t-pd.Timedelta(hours=2),available_at=t-pd.Timedelta(hours=3))
    result=predict_frame(artifact,pd.DataFrame([row]))[0]
    assert result['probability'] is None and 'forecast_available_before_issue' in result['flags']
