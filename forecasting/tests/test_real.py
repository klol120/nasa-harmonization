import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from firecast.real import audit_detections,cell_day_labels,candidate_grid,require_ready
from firecast.data import grid_id
from firecast.environment import ndvi_values,vegetation_fraction,terrain,coverage_fraction
from firecast.earthdata import data_link,SafeRedirect,download_sample
import urllib.request

@pytest.fixture
def config():
    return json.loads((Path(__file__).parents[1]/'configs/real-preparation.json').read_text())

def detection(id='one',date='2020-07-01T12:00:00Z',**kwargs):
    return dict(detection_id=id,lat=33.85,lon=35.55,detected_at=date,product='viirs-snpp',sensor='VIIRS',satellite='N',processing_version='2',confidence='n',type=0,**kwargs)

def test_recurrence_does_not_learn_from_test(config):
    rows=[]
    for year in [2023,2024,2025]:
        for day in range(1,16):rows.append(detection(f'{year}-{day}',f'{year}-07-{day:02d}T12:00:00Z'))
    f,_=audit_detections(pd.DataFrame(rows),config)
    assert not f.recurrence_candidate.any()
    old=[detection(f'old-{y}-{d}',f'{y}-07-{d:02d}T12:00:00Z') for y in [2018,2019,2020] for d in range(1,16)]
    f,_=audit_detections(pd.DataFrame(old+rows),config)
    assert f.recurrence_candidate.all() and not f.flag_level.eq('confirmed').any()

def test_strict_mixed_window_never_becomes_negative(config):
    clean=detection();flagged=detection('two');flagged.update(type=2,confidence='l',lon=35.56)
    audit,_=audit_detections(pd.DataFrame([clean,flagged]),config)
    cells=pd.DataFrame([{'cell_id':grid_id(33.85,35.55,.1)}])
    args=(cells,audit,config)
    strict=cell_day_labels(*args,'strict',pd.Timestamp('2020-07-01',tz='UTC'),pd.Timestamp('2020-07-03',tz='UTC'))
    assert strict.label_status.tolist()==['excluded','uncertain'] and strict.y.isna().all()
    conservative=cell_day_labels(*args,'conservative',pd.Timestamp('2020-07-01',tz='UTC'),pd.Timestamp('2020-07-03',tz='UTC'))
    assert conservative.y.iloc[0]==1 and pd.isna(conservative.y.iloc[1])
    reason=audit.loc[audit.detection_id.eq('two'),'flag_reason'].iloc[0]
    assert 'static' in reason and 'confidence' in reason

def test_grid_is_not_selected_from_fire_locations(config):
    grid=candidate_grid(config)
    assert len(grid)==306 and grid.cell_id.nunique()==306
    assert grid.scope_status.str.contains('pending').all()

def test_readiness_stops_training():
    with pytest.raises(ValueError,match='no masks'):require_ready({'training_allowed':False,'blockers':['no masks']})

def test_recurrence_cutoff_must_precede_validation(config):
    config['recurrence_fit_end_exclusive']='2025-01-01T00:00:00Z'
    with pytest.raises(ValueError,match='must not inspect'):audit_detections(pd.DataFrame([detection()]),config)

def test_ndvi_quality_scaling_and_publication():
    values,good=ndvi_values([5000,-3000,7000],[0,0,3],'2020-01-16T00:00Z','2020-01-20T00:00Z')
    assert values[0]==.5 and np.isnan(values[1:]).all() and good.tolist()==[True,False,False]
    with pytest.raises(ValueError,match='before'):ndvi_values([5000],[0],'2020-01-16T00:00Z','2020-01-01T00:00Z')

def test_landcover_unknown_not_barren():
    assert vegetation_fraction([1,12,13,255],[True]*4)==pytest.approx(2/3)
    assert np.isnan(vegetation_fraction([255],[True]))

def test_terrain_planar_slope_and_flat_aspect():
    f=terrain([[0,30,60],[0,30,60]],30,30)
    assert np.allclose(f['slope_deg'],45) and np.allclose(f['aspect_deg'],270)
    assert np.isnan(terrain([[1,1],[1,1]],30,30)['aspect_deg']).all()

def test_coverage_cloud_missing_and_qa():
    result=coverage_fraction([5,4,0,8],[True]*4,[True,True,True,False])
    assert result['fraction']==.25
    assert coverage_fraction([5],[False])['fraction'] is None
    with pytest.raises(ValueError,match='Unrecognized'):coverage_fraction([255],[True])

def test_auth_redirect_drops_token():
    req=urllib.request.Request('https://data.lpdaac.earthdatacloud.nasa.gov/test',headers={'Authorization':'Bearer secret'})
    redirect=SafeRedirect().redirect_request(req,None,302,'found',{},'https://urs.earthdata.nasa.gov/login')
    assert redirect.get_header('Authorization') is None
    same=SafeRedirect().redirect_request(req,None,302,'found',{},'https://data.lpdaac.earthdatacloud.nasa.gov/test2')
    assert same.get_header('Authorization')=='Bearer secret'

def test_metadata_is_not_download_and_requires_nasa_auth(tmp_path):
    assert data_link({'links':[{'href':'https://example.org/x','rel':'http://esipfed.org/ns/fedsearch/1.1/data#'}]}) is None
    with pytest.raises(ValueError,match='absent'):download_sample('https://data.lpdaac.earthdatacloud.nasa.gov/test',tmp_path/'x.hdf','')

def test_confirmed_review_is_preserved_by_both_policies(config):
    row=detection();row.update(flag_level='confirmed',flag_reason='reviewed facility',flag_source='supplied documented review')
    f,_=audit_detections(pd.DataFrame([row]),config)
    assert f.flag_level.iloc[0]=='confirmed'
    assert f.conservative_action.iloc[0]==f.strict_action.iloc[0]=='quarantine_entire_cell_window'
    assert 'reviewed facility' in f.flag_reason.iloc[0]

def test_review_without_source_fails(config):
    row=detection();row.update(flag_level='confirmed',flag_reason='',flag_source='')
    with pytest.raises(ValueError,match='reason and source'):audit_detections(pd.DataFrame([row]),config)

def test_generic_trainer_refuses_unverified_real_data(tmp_path):
    from firecast.models import train_experiments
    with pytest.raises(ValueError,match='readiness report'):
        train_experiments({}, {'synthetic':False}, tmp_path, {})

def test_persistent_nasa_download_strips_auth_on_cross_host_redirect(tmp_path):
    import httpx
    from firecast.earthdata import download_sample_with_client
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1:
            assert request.headers.get('Authorization')=='Bearer TEST_ONLY'
            return httpx.Response(302,headers={'Location':'https://cdn.example.org/science'})
        assert 'Authorization' not in request.headers
        return httpx.Response(200,content=b'\x89HDF\r\n\x1a\nfixture')
    with httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=True) as client:
        p=download_sample_with_client('https://data.lpdaac.earthdatacloud.nasa.gov/science',tmp_path/'x.h5','TEST_ONLY',client)
    assert p.read_bytes().startswith(b'\x89HDF') and len(calls)==2
