import json
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box
from firecast.global_acquire import tile_at,site_tiles,sample_days
from firecast.global_weather import history_features
from firecast.global_data import split_masks,FEATURES,count_pixels
from firecast.conflict_review import apply_quarantine
from firecast.gridded import SRTM
from firecast.data import grid_id


def test_fixed_date_sampling_does_not_depend_on_fire_outcomes():
    c={'seed':42,'start':'2018-01-01T00:00:00Z','end_exclusive':'2021-01-01T00:00:00Z','days_per_month':2}
    a=sample_days(c);b=sample_days(c)
    assert a.equals(b) and len(a)==72
    assert pd.Series(a.strftime('%Y-%m')).value_counts().eq(2).all()
    assert tile_at(0,0)=='h18v09'
    assert site_tiles({'south':36,'north':38,'west':29,'east':31})==['h20v05']


def test_lagged_history_cannot_see_prediction_or_recent_days():
    dates=pd.date_range('2020-01-01',periods=50)
    f=pd.DataFrame({'date':dates,'weather_point_id':'x','PRECTOTCORR':np.arange(50,dtype=float),'T2M':20.,'WD10M':90.,'WS10M':2.,'RH2M':50.})
    a=history_features(f,3)
    assert a.rain7_mm.iloc[20]==sum(range(10,17))
    f.loc[17:,'PRECTOTCORR']=9999
    b=history_features(f,3)
    assert a.rain7_mm.iloc[20]==b.rain7_mm.iloc[20]
    with pytest.raises(ValueError):history_features(f.drop(index=4),3)


def test_conflict_mask_excludes_whole_overlapping_window_and_preserves_original():
    t=pd.to_datetime(['2023-10-06','2023-10-07','2023-10-07','2023-10-07'],utc=True)
    f=pd.DataFrame({'prediction_time':t,'window_end':t+pd.Timedelta(days=1),'region':['lebanon','lebanon','lebanon','global'],
      'cell_id':[grid_id(33.25,35.25,.1),grid_id(33.25,35.25,.1),grid_id(34.25,35.25,.1),grid_id(33.25,35.25,.1)],'y':[1.,1.,0.,1.],'label_status':['positive','positive','negative','positive']})
    c={'start':'2023-10-07T00:00:00Z','end_exclusive':None,'policy_id':'review','reason':'possible conflict contamination','source_url':'https://data.humdata.org/dataset/cod-ab-lbn'}
    result=apply_quarantine(f,c,box(35.2,33.2,35.3,33.3))
    assert result.conflict_excluded.tolist()==[False,True,False,False]
    assert pd.isna(result.y.iloc[1]) and result.y_before_conflict_quarantine.iloc[1]==1
    assert result.y.iloc[0]==1 and f.y.notna().all()
    assert not {'conflict_excluded','exclusion_policy_id','processed_fraction','fire','y'}&set(FEATURES)


def test_global_sealed_and_geographic_splits_do_not_enter_fit():
    c={'training_end':'2021-01-01T00:00:00Z','calibration_end':'2022-01-01T00:00:00Z','validation_end':'2023-01-01T00:00:00Z','end_exclusive':'2026-01-01T00:00:00Z','embargo_days':7}
    t=pd.to_datetime(['2020-06-01','2021-06-01','2022-06-01','2023-06-01','2020-06-01','2023-06-01'],utc=True)
    f=pd.DataFrame({'prediction_time':t,'window_end':t+pd.Timedelta(days=1),'geographic_holdout':[False]*4+[True,True]})
    parts=split_masks(f,c,'global')
    assert parts['train'].to_numpy().nonzero()[0].tolist()==[0]
    assert parts['test-sealed'].to_numpy().nonzero()[0].tolist()==[3]
    assert parts['geographic-test-sealed'].to_numpy().nonzero()[0].tolist()==[5]
    assert np.column_stack([v for v in parts.values()]).sum(axis=1).max()==1


def test_mask_water_or_nonvegetation_fire_does_not_become_negative():
    m={'eligible':np.array([True,False]),'cell_ids':np.array(['x','x'])}
    result=count_pixels([5,9],[1,1],m,'site','2020-01-01')
    assert result.processed.iloc[0]==1 and result.noneligible_fire.iloc[0]==1


def test_srtm_southern_western_coordinates(tmp_path):
    import zipfile
    # A flat real-format HGT in the southern/western hemisphere validates sign parsing.
    p=tmp_path/'S13W064.hgt.zip';data=np.full((3601,3601),123,dtype='>i2')
    with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('S13W064.hgt',data.tobytes())
    dem=SRTM([p]);e,s,_,_=dem.sample(np.array([-12.5]),np.array([-63.5]))
    assert e[0]==123 and s[0]==0


def test_neural_fine_tuning_preserves_global_scaler_and_source_weights():
    from firecast.transfer_models import FrameModel,fine_tune_neural,PlattModel
    rng=np.random.default_rng(4);f=pd.DataFrame(rng.normal(size=(200,len(FEATURES))),columns=FEATURES)
    f['y']=(f.temperature_c>0).astype(int)
    source=FrameModel('neural',{'hidden_layer_sizes':(8,4),'max_iter':3,'learning_rate_init':.01}).fit(f)
    original=[w.copy() for w in source.estimator.coefs_];mean=source.scaler.mean_.copy()
    local=f.copy();local['y']=(local.humidity_pct>0).astype(int)
    adapted=fine_tune_neural(source,local,epochs=2,learning_rate=.005)
    assert np.array_equal(source.scaler.mean_,mean) and np.array_equal(adapted.scaler.mean_,mean)
    assert all(np.array_equal(a,b) for a,b in zip(original,source.estimator.coefs_))
    assert adapted.adaptation['coefficient_change_l2']>0
    calibrated=PlattModel(adapted).fit(local)
    p=calibrated.predict_proba(local)
    assert p.shape==(200,2) and np.isfinite(p).all() and np.allclose(p.sum(axis=1),1)


def test_anchored_logistic_changes_local_fit_without_mutating_source():
    from firecast.transfer_models import FrameModel,AnchoredLogistic
    rng=np.random.default_rng(5);f=pd.DataFrame(rng.normal(size=(200,len(FEATURES))),columns=FEATURES);f['y']=(f.temperature_c>0).astype(int)
    source=FrameModel('logistic',{'C':1}).fit(f);original=source.estimator.coef_.copy()
    local=f.copy();local['y']=(local.temperature_c>.5).astype(int)
    model=AnchoredLogistic(source,1).fit(local)
    assert np.array_equal(source.estimator.coef_,original)
    assert np.isfinite(model.predict_proba(local)).all()
    assert not np.allclose(model.predict_proba(local),source.predict_proba(local))


def test_multiple_processing_versions_choose_latest_without_double_counting():
    from firecast.global_acquire import select_daily_versions
    old={'name':'VJ114A1.A2021030.h22v10.002.2022317043641','date':'2021-01-30','url':'https://example.nasa.gov/old'}
    new={'name':'VJ114A1.A2021030.h22v10.002.2023150215551','date':'2021-01-30','url':'https://example.nasa.gov/new'}
    chosen,reviews=select_daily_versions([new,old,old])
    assert chosen==[new] and reviews[0]['other_catalogued_versions']==[old]


def test_confirmation_gate_blocks_reading_labels_before_frozen_artifacts(tmp_path,monkeypatch):
    import firecast.benchmark_global as benchmark
    calls=[]
    monkeypatch.setattr(benchmark,'load_part',lambda *args: calls.append(args[1]) or 'fixture')
    path=tmp_path/'selection-frozen.json'
    with pytest.raises(ValueError,match='frozen selection'):benchmark.open_confirmations(tmp_path,{},path,'absent','strict')
    assert calls==[]
    folder=tmp_path/'frozen';folder.mkdir();artifact=folder/'fixture.bin';artifact.write_bytes(b'fixture bytes only')
    path.write_text(json.dumps({'best_transfer':'model','artifacts':{'model':{'file':'fixture.bin','sha256':benchmark.sha(artifact)}}}))
    frozen=benchmark.sha(path);artifact.write_bytes(b'changed')
    with pytest.raises(ValueError,match='artifact changed'):benchmark.open_confirmations(tmp_path,{},path,frozen,'strict')
    assert calls==[]
    artifact.write_bytes(b'fixture bytes only')
    result=benchmark.open_confirmations(tmp_path,{},path,frozen,'strict')
    assert len(result)==4 and len(calls)==4


def test_global_inference_preserves_full_frame_and_flags_conflict_scope():
    from firecast.inference import predict_frame
    class Model:
        def predict_proba(self,frame):
            assert 'prediction_time' in frame and 'region' in frame
            return np.tile([.7,.3],(len(frame),1))
    cid=grid_id(33.25,35.25,.1);t=pd.Timestamp('2026-11-15T00:00:00Z')
    artifact={'model':Model(),'id':'fixture','model_accepts_full_frame':True,'features':['temperature_c'],'bounds':{'temperature_c':[0,40]},'threshold':.2,
      'validated_regions':['sample_site'],'config':{'grid_deg':.1,'horizon_hours':24,'synthetic':False,'mode':'retrospective'},
      'evaluation_exclusions':[{'start':'2023-10-07T00:00:00Z','end_exclusive':None,'cell_ids':[cid]}]}
    row={'cell_id':cid,'lat':33.25,'lon':35.25,'region':'sample_site','temperature_c':20.,'prediction_time':t,'issue_time':t-pd.Timedelta(hours=12),
      'available_at':t-pd.Timedelta(hours=10),'valid_start':t,'valid_end':t+pd.Timedelta(hours=24)}
    research=predict_frame(artifact,pd.DataFrame([row]))[0]
    assert research['probability']==.3 and 'outside_conflict_filtered_evaluation_scope' in research['flags']
    assert 'outside_validated_region' not in research['flags']
    production=predict_frame(artifact,pd.DataFrame([row]),strict_domain=True)[0]
    assert production['probability'] is None


def test_lossless_raw_cache_packing_roundtrip(tmp_path):
    import hashlib
    from firecast.cache_pack import pack,restore
    raw=tmp_path/'raw';raw.mkdir();packed=tmp_path/'packed';contents={}
    for i in range(2):
        name=f'VNP14A1.fixture{i}.h5';value=(b'exact original NASA-container fixture bytes\x00\xff'*100)
        (raw/name).write_bytes(value);(raw/(name+'.manifest.json')).write_text(json.dumps({'sha256':hashlib.sha256(value).hexdigest(),'url':'https://example.nasa.gov/fixture'}));contents[name]=value
    assert pack(raw,packed,target_free=10**18,batch_size=1)==2
    assert not list(raw.glob('*.h5'))
    restore(packed,raw)
    assert all((raw/name).read_bytes()==value for name,value in contents.items())
    archive=next(packed.glob('*.tar.gz'));archive.write_bytes(b'corrupted archive')
    with pytest.raises(ValueError,match='Archive checksum'):restore(packed,raw)


def test_fixed_recipe_refit_does_not_mutate_the_source_or_use_new_calibration_for_fit():
    from firecast.transfer_models import FrameModel,PlattModel,ProbabilityEnsemble
    from firecast.refit_transfer import RecipeRefitter
    rng=np.random.default_rng(8)
    def frame(n,axis):
        f=pd.DataFrame(rng.normal(size=(n,len(FEATURES))),columns=FEATURES);f['y']=(f[axis]>0).astype(int);return f
    g,l,cg,cl=frame(120,'temperature_c'),frame(80,'humidity_pct'),frame(40,'temperature_c'),frame(30,'humidity_pct')
    source=FrameModel('logistic',{'C':1}).fit(g);local=FrameModel('logistic',{'C':1}).fit(l)
    recipe=PlattModel(ProbabilityEnsemble(source,local,.75)).fit(cl);old=source.estimator.coef_.copy()
    newg,newl,newcg,newcl=frame(160,'temperature_c'),frame(100,'humidity_pct'),frame(50,'temperature_c'),frame(35,'humidity_pct')
    refitter=RecipeRefitter(newg,newl,newcg,newcl,{'global_fit':120,'local_fit':80,'global_cal':40,'local_cal':30},42)
    result=refitter.refit(recipe)
    assert result.calibration_rows==35
    assert result.base.global_model.fit_rows==160 and result.base.local_model.fit_rows==100
    assert np.array_equal(source.estimator.coef_,old)
    assert refitter.refit(source) is result.base.global_model


def test_final_refit_time_filter_never_fits_2026_labels(monkeypatch):
    import firecast.refit_transfer as module
    t=pd.to_datetime(['2024-06-01','2024-06-02','2025-06-01','2025-06-02','2026-06-01','2026-06-02'],utc=True)
    frame=pd.DataFrame({'prediction_time':t,'window_end':t+pd.Timedelta(days=1),'y':[0,1,0,1,0,1],'conflict_excluded':False})
    calls=[]
    def loader(data,name,manifest,policy):
        calls.append(name);return frame.copy() if name.endswith('test-sealed') else frame.iloc[:0].copy()
    monkeypatch.setattr(module,'load_part',loader)
    fit,cal=module.refit_parts('unused',{'config':{'embargo_days':7}},'global')
    assert fit.prediction_time.dt.year.eq(2024).all() and cal.prediction_time.dt.year.eq(2025).all()
    assert len(fit)==len(cal)==2 and not any('2026' in name or 'confirmation' in name for name in calls)


def test_reused_static_cache_cannot_mutate_source_manifests(tmp_path):
    from firecast.global_acquire import save_subset,reuse_static,valid_subset
    source=tmp_path/'source';target=tmp_path/'target'
    (source/'static').mkdir(parents=True);(source/'maps').mkdir()
    (source/'static-report.json').write_text(json.dumps({'complete':True}))
    p=source/'maps/pixels.npz';save_subset(p,{'rows':np.array([1,2])},{'source':'NASA fixture'})
    reuse_static(source,target)
    original=p.read_bytes();copied=target/'maps/pixels.npz'
    assert p.stat().st_ino==copied.stat().st_ino
    assert p.with_suffix('.npz.manifest.json').stat().st_ino!=copied.with_suffix('.npz.manifest.json').stat().st_ino
    save_subset(copied,{'rows':np.array([3,4])},{'source':'new source fixture'})
    assert p.read_bytes()==original and valid_subset(p) and valid_subset(copied)


def test_catalogue_cache_rejects_a_different_requested_source(tmp_path,monkeypatch):
    import firecast.global_acquire as module
    monkeypatch.setattr(module,'fetch',lambda url: b'{"actual": "NASA fixture response"}')
    path=tmp_path/'source.json.gz'
    assert module.cached_json('https://example.nasa.gov/first',path)['actual']=='NASA fixture response'
    with pytest.raises(ValueError,match='Cache URL differs'):module.cached_json('https://example.nasa.gov/other',path)


def test_country_view_withholds_conflict_scope_even_for_research():
    from firecast.inference import predict_frame
    class Model:
        def predict_proba(self,frame):return np.tile([.7,.3],(len(frame),1))
    cid=grid_id(33.25,35.25,.1);t=pd.Timestamp('2026-11-15T00:00:00Z')
    artifact={'model':Model(),'id':'fixture','features':['temperature_c'],'bounds':{'temperature_c':[0,40]},'threshold':.2,'withhold_evaluation_exclusions':True,
      'config':{'grid_deg':.1,'horizon_hours':24,'synthetic':False,'mode':'retrospective'},'evaluation_exclusions':[{'start':'2023-10-07T00:00:00Z','cell_ids':[cid]}]}
    row={'cell_id':cid,'lat':33.25,'lon':35.25,'region':'lebanon','temperature_c':20.,'prediction_time':t,'issue_time':t-pd.Timedelta(hours=12),'available_at':t-pd.Timedelta(hours=10),'valid_start':t,'valid_end':t+pd.Timedelta(hours=24)}
    result=predict_frame(artifact,pd.DataFrame([row]))[0]
    assert result['probability'] is None and 'outside_conflict_filtered_evaluation_scope' in result['flags']


@pytest.mark.parametrize('case',['complete','future_availability','missing_rain'])
def test_transfer_forecast_history_availability_and_completeness(tmp_path,monkeypatch,case):
    import firecast.transfer_forecast as module
    t=pd.Timestamp('2026-11-15T00:00:00Z');end=t-pd.Timedelta(days=3);start=end-pd.Timedelta(days=30)
    row={'prediction_time':t,'history_end':end,'history_available_at':t-pd.Timedelta(hours=12),'weather_point_id':'fixture','weather_lat':33.25,'weather_lon':35.25,
      'lat':33.25,'lon':35.25,'temperature_c':20.,'humidity_pct':50.,'precip_mm':0.,'wind_u_ms':1.,'wind_v_ms':1.,'rain7_mm':0.,'vegetation_fraction':.6,'elevation_m':100.,'slope_deg':1.,'aspect_sin':0.,'aspect_cos':1.}
    path=tmp_path/'input.csv';pd.DataFrame([row]).to_csv(path,index=False)
    keys=[d.strftime('%Y%m%d') for d in pd.date_range(start,periods=30)]
    def payload(url,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        available=t+pd.Timedelta(hours=1) if case=='future_availability' else t-pd.Timedelta(hours=12)
        path.with_suffix(path.suffix+'.manifest.json').write_text(json.dumps({'downloaded_at':str(available)}))
        rain=dict.fromkeys(keys,1.)
        if case=='missing_rain':rain.pop(keys[-1])
        return {'header':{'time_standard':'UTC','fill_value':-999},'properties':{'parameter':{'PRECTOTCORR':rain,'T2M':dict.fromkeys(keys,20.)}}}
    monkeypatch.setattr(module,'cached_json',payload)
    if case=='complete':
        result=module.augment(path,tmp_path/'out')
        assert result.rain7_mm.iloc[0]==7 and result.rain30_mm.iloc[0]==30 and result.temperature7_c.iloc[0]==20
    else:
        with pytest.raises(ValueError):module.augment(path,tmp_path/'out')
        assert not (tmp_path/'out/forecast-features.csv').exists()


def test_fire_with_incompatible_land_qa_never_manufactures_a_negative():
    from firecast.gridded import label_counts
    mapping={'eligible':np.ones(10,dtype=bool),'cell_ids':np.repeat('fixture',10)}
    counts=count_pixels([5]*9+[9],[2]*9+[0],mapping,'site','2020-01-01')
    counts['processed_fraction']=counts.processed/10
    status,y=label_counts(counts,[False],'strict',.8)
    assert counts.processed_fraction.iloc[0]==.9 and counts.noneligible_fire.iloc[0]==1
    assert status.tolist()==['excluded'] and np.isnan(y[0])


def test_refit_protocol_captures_validation_selection_and_rejects_replacement(tmp_path):
    from firecast.refit_transfer import freeze_protocol
    source=tmp_path/'benchmark';source.mkdir();selection=source/'selection-frozen.json'
    selection.write_text(json.dumps({'best_transfer':'fixed-from-validation'}));out=tmp_path/'protocol.json'
    result=freeze_protocol(source,out)
    assert result['fixed_transfer_id']=='fixed-from-validation'
    selection.write_text(json.dumps({'best_transfer':'another-selection'}))
    with pytest.raises(ValueError,match='another selection'):freeze_protocol(source,out)
    assert json.loads(out.read_text())['fixed_transfer_id']=='fixed-from-validation'


def test_global_daily_adapter_rejects_incompatible_horizon_before_reading_data():
    from firecast.global_data import build_global
    with pytest.raises(ValueError,match='24-hour horizon'):build_global({'horizon_hours':12},'unused','unused')


def test_global_and_lebanese_training_cannot_mix_grid_resolutions(tmp_path):
    from firecast.global_data import build_lebanon
    (tmp_path/'static-report.json').write_text(json.dumps({'config':{'grid_deg':.1,'horizon_hours':24}}))
    with pytest.raises(ValueError,match='grid/horizon must match'):
        build_lebanon({'grid_deg':.05,'horizon_hours':24},tmp_path,'unused','unused','unused')


def test_history_rejects_a_future_looking_negative_lag():
    with pytest.raises(ValueError,match='nonnegative'):history_features(pd.DataFrame(),-1)
