import json
from pathlib import Path
import pandas as pd
import pytest
from firecast.fixture import create_fixture
from firecast.data import load_inputs,build_dataset,grid_id,flag_detections
from firecast.models import split,train_experiments
from firecast.inference import predict

@pytest.fixture(scope='module')
def data(tmp_path_factory):
    p=tmp_path_factory.mktemp('inputs')
    config=json.loads((Path(__file__).parents[1]/'configs/lebanon.json').read_text())
    config=create_fixture(p,config);tables,prov=load_inputs(p,config)
    return tables,config,prov

def minimal(data):
    tables,config,_=data
    tables={k:v.copy() for k,v in tables.items()}
    w=tables['weather'].iloc[[0]].copy();t=w.prediction_time.iloc[0];cid=w.cell_id.iloc[0]
    tables['weather']=w
    tables['detections']=tables['detections'].iloc[:0].copy()
    tables['coverage']=tables['coverage'].iloc[:0].copy()
    return tables,config,t,cid

def test_grid_boundaries():
    assert grid_id(33.9,35.5,.1)=='1239_2155'
    assert grid_id(33.89999,35.49999,.1)=='1238_2154'
    with pytest.raises(ValueError): grid_id(91,35,.1)

def test_no_coverage_is_not_negative(data):
    tables,c,_,_=minimal(data);f,_=build_dataset(tables,c,'strict')
    assert f.label_status.iloc[0]=='uncertain' and f.y.isna().all()

def test_future_forecasts_and_vegetation_rejected(data):
    tables,c,t,_=minimal(data);tables['weather']['issue_time']=t+pd.Timedelta(hours=1)
    with pytest.raises(ValueError,match='No eligible'): build_dataset(tables,c,'strict')
    tables,c,t,_=minimal(data);tables['environment']['available_at']=t+pd.Timedelta(days=1)
    with pytest.raises(ValueError,match='No eligible'): build_dataset(tables,c,'strict')

def test_excluded_positive_never_becomes_negative_and_end_exclusive(data):
    tables,c,t,cid=minimal(data)
    raw=data[0]['detections'].iloc[[0]].copy()
    raw['lat']=tables['cells'].iloc[0].lat;raw['lon']=tables['cells'].iloc[0].lon
    raw['detected_at']=t+pd.Timedelta(hours=12);raw['flag_level']='confirmed';tables['detections']=raw
    f,_=build_dataset(tables,c,'conservative')
    assert f.label_status.iloc[0]=='excluded' and f.y.isna().all()
    raw['detected_at']=t+pd.Timedelta(hours=c['horizon_hours']);tables['detections']=raw
    f,_=build_dataset(tables,c,'strict');assert f.label_status.iloc[0]=='uncertain'

def test_strict_vs_conservative(data):
    tables,c,t,_=minimal(data);raw=data[0]['detections'].iloc[[0]].copy()
    raw['lat']=tables['cells'].iloc[0].lat;raw['lon']=tables['cells'].iloc[0].lon
    raw['detected_at']=t;raw['flag_level']='probable';tables['detections']=raw
    a,_=build_dataset(tables,c,'conservative');b,_=build_dataset(tables,c,'strict')
    assert a.y.iloc[0]==1 and b.y.isna().all()

def test_event_radius_and_window(data):
    tables,c,t,_=minimal(data);raw=data[0]['detections'].iloc[[0]].copy();raw['flag_level']='unflagged';raw['type']=0;raw['detected_at']=t
    tables['detections']=raw
    tables['events']=pd.DataFrame([dict(event_id='review',lat=raw.iloc[0].lat,lon=raw.iloc[0].lon,start=t-pd.Timedelta(hours=1),end=t+pd.Timedelta(hours=1),radius_km=1,level='confirmed',reason='test',source='fixture',reported_at=t+pd.Timedelta(days=1))])
    assert flag_detections(tables,c).flag_level.iloc[0]=='confirmed'
    tables['events']['lon']=0
    assert flag_detections(tables,c).flag_level.iloc[0]=='unflagged'

def test_splits_and_training(data,tmp_path):
    tables,c,prov=data
    f,_=build_dataset(tables,c,'conservative');tr,val,te,_=split(f,c)
    assert tr.window_end.max()<val.prediction_time.min()
    assert val.window_end.max()<te.prediction_time.min()
    assert set(te.region)=={'lebanon'}
    # Model fit excludes labels/flags, which are not known at inference time.
    report=train_experiments({'conservative':f},dict(c,regional_cells=[]),tmp_path,prov)
    assert len(report['experiments'])==3
    assert all('y' not in x['features'] and 'event_type' not in x['features'] for x in report['experiments'])
    req=f[f.prediction_time==f.prediction_time.max()].copy();req.to_csv(tmp_path/'input.csv',index=False)
    result=predict(tmp_path/'model.joblib',tmp_path/'input.csv',tmp_path/'risk')
    assert all(r['probability'] is not None and 0<=r['probability']<=1 for r in result)
    req['issue_time']=req.prediction_time+pd.Timedelta(hours=1);req.to_csv(tmp_path/'future.csv',index=False)
    assert all(r['probability'] is None for r in predict(tmp_path/'model.joblib',tmp_path/'future.csv',tmp_path/'invalid'))

def test_explicit_observability_allows_negative(data):
    tables,c,t,cid=minimal(data)
    tables['coverage']=pd.DataFrame([{'cell_id':cid,'start':t,'end':t+pd.Timedelta(hours=24),'sensor':'VIIRS','observable_fraction':1}])
    f,_=build_dataset(tables,c,'strict');assert f.y.iloc[0]==0 and f.label_status.iloc[0]=='negative'

def test_issue_selection_falls_back_to_available_cycle(data):
    tables,c,t,_=minimal(data);old=tables['weather'].copy();future=old.copy()
    future['issue_time']=t+pd.Timedelta(hours=1);future['available_at']=t+pd.Timedelta(hours=2);future['temperature_c']=99
    tables['weather']=pd.concat([old,future]);f,_=build_dataset(tables,c,'strict')
    assert len(f)==1 and f.temperature_c.iloc[0]==old.temperature_c.iloc[0]

def test_history_availability_enforced_even_retrospectively(data):
    tables,c,t,_=minimal(data);tables['weather']['history_available_at']=t+pd.Timedelta(hours=1)
    with pytest.raises(ValueError,match='No eligible'): build_dataset(tables,dict(c,mode='retrospective'),'strict')

def test_geographic_holdout(data):
    tables,c,_=data;f,_=build_dataset(tables,c,'conservative')
    cid=tables['cells'].iloc[0].cell_id
    tr,val,test,geo=split(f,dict(c,heldout_cells=[cid]))
    assert cid not in set(tr.cell_id)|set(val.cell_id)|set(test.cell_id)
    assert set(geo.cell_id)=={cid}

def test_sensor_confidence_is_not_shared_scale(data):
    tables,c,t,_=minimal(data);raw=data[0]['detections'].iloc[[0]].copy();raw['type']=0;raw['flag_level']='unflagged'
    raw['sensor']='MODIS';raw['confidence']='20';tables['detections']=raw
    assert flag_detections(tables,c).flag_level.iloc[0]=='uncertain'
    raw['sensor']='VIIRS';raw['confidence']='n';tables['detections']=raw
    assert flag_detections(tables,c).flag_level.iloc[0]=='unflagged'

def test_asset_screening(tmp_path):
    from firecast.inference import overlay
    risk={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'cell_id':'x','above_validation_threshold':True},'geometry':{'type':'Polygon','coordinates':[[[35,33],[35.1,33],[35.1,33.1],[35,33.1],[35,33]]]}}]}
    assets={'type':'FeatureCollection','features':[{'type':'Feature','properties':{},'geometry':{'type':'Point','coordinates':[35.05,33.05]}},{'type':'Feature','properties':{},'geometry':{'type':'Point','coordinates':[0,0]}}]}
    for name,obj in [('risk',risk),('assets',assets)]: (tmp_path/f'{name}.json').write_text(json.dumps(obj))
    overlay(tmp_path/'risk.json',tmp_path/'assets.json',tmp_path/'out.json')
    assert len(json.loads((tmp_path/'out.json').read_text())['features'])==1
