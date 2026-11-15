"""Predeclared global-to-Lebanon benchmarks; confirmation opens only after freeze."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score,precision_recall_curve
from .models import metrics
from .review import reliability
from .global_data import FEATURES
from .transfer_models import (FrameModel,SeasonalModel,PlattModel,ProbabilityEnsemble,AnchoredLogistic,ScoreTransfer,fine_tune_neural,specifications)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_part(data,name,manifest,policy='strict'):
    domain,part=name.split('-',1);path=Path(data)/(name+'.csv.gz')
    if sha(path)!=manifest[domain][part]['sha256']:raise ValueError('Split file checksum mismatch: '+name)
    cols=list(dict.fromkeys([*FEATURES,'lat','region','continent','cell_id','prediction_time','window_end','y_'+policy,'conflict_excluded']))
    dtype={c:'float32' for c in [*FEATURES,'lat','y_'+policy]};dtype.update({k:'category' for k in ['region','continent','cell_id']})
    f=pd.read_csv(path,usecols=cols,dtype=dtype).rename(columns={'y_'+policy:'y'})
    for c in ['prediction_time','window_end']:f[c]=pd.to_datetime(f[c],utc=True)
    f=f[f.y.notna()].copy()
    if f.empty:raise ValueError('No qualified observations in '+name)
    if part in {'train','calibration','validation'} and f.y.nunique()!=2:raise ValueError('Fit/calibration/validation split needs both classes: '+name)
    if not np.isfinite(f[FEATURES].to_numpy()).all():raise ValueError('Unqualified model features')
    if f.conflict_excluded.any():raise ValueError('Conflict-excluded windows entered modelling')
    return f


def select_threshold(y,p):
    precision,recall,thresholds=precision_recall_curve(y,p)
    f1=2*precision[:-1]*recall[:-1]/np.maximum(precision[:-1]+recall[:-1],1e-15)
    chosen=float(thresholds[int(np.argmax(f1))]);targets={}
    for target in [.05,.10]:
        eligible=np.flatnonzero(precision[:-1]>=target)
        targets[str(target)]=float(thresholds[eligible[np.argmax(recall[eligible])]]) if len(eligible) else None
    return chosen,targets


def score(frame,p,threshold,detail=False):
    result=metrics(frame.y,p,threshold);result['prevalence']=float(frame.y.mean());result['mean_probability']=float(np.mean(p))
    result['start']=str(frame.prediction_time.min());result['end']=str(frame.window_end.max())
    regional={}
    for name,indices in frame.groupby('region',observed=True).indices.items():
        y=frame.y.iloc[indices];regional[str(name)]={'observations':len(indices),'positive_windows':int(y.sum()),'average_precision':float(average_precision_score(y,p[indices])) if y.nunique()==2 else None}
    values=[v['average_precision'] for v in regional.values() if v['average_precision'] is not None]
    result['site_macro_average_precision']=float(np.mean(values)) if values else None
    result['sites_with_defined_average_precision']=len(values)
    if detail:
        result['by_region']=regional;result['quantile_reliability']=reliability(frame.y,p)
        season=((frame.prediction_time.dt.month%12)//3).map({0:'winter',1:'spring',2:'summer',3:'autumn'})
        result['by_season']={str(k):metrics(frame.y.iloc[idx],p[idx],threshold) for k,idx in frame.groupby(season,observed=True).indices.items()}
    return result


def key(result):return (result['pr_auc_average_precision'] if result['pr_auc_average_precision'] is not None else -1,-result['brier'])


def bootstrap(frame,p,seed,n=100):
    groups=frame.prediction_time.dt.strftime('%Y-%m').to_numpy();names=np.unique(groups);rng=np.random.default_rng(seed)
    blocks={name:np.flatnonzero(groups==name) for name in names};scores=[]
    for _ in range(n):
        idx=np.concatenate([blocks[name] for name in rng.choice(names,len(names),replace=True)])
        y=frame.y.iloc[idx]
        if y.nunique()==2:scores.append(average_precision_score(y,p[idx]))
    return {'monthly_block_AP_95pct':np.quantile(scores,[.025,.975]).tolist() if scores else None,'resamples':n,'months':len(names),'note':'Conditional fitted-model interval; source/label uncertainty and incident dependence remain'}


def fit_family(algorithm,params,frame,seed):
    return SeasonalModel().fit(frame) if algorithm=='seasonal' else FrameModel(algorithm,params,seed).fit(frame)


def open_confirmations(data,manifest,selection_path,expected_hash,policy):
    selection_path=Path(selection_path)
    if not selection_path.exists() or sha(selection_path)!=expected_hash:raise ValueError('Confirmation requires an intact frozen selection')
    frozen=json.loads(selection_path.read_text())
    if not frozen.get('artifacts') or frozen.get('best_transfer') not in frozen['artifacts']:raise ValueError('No frozen transfer artifact')
    for record in frozen['artifacts'].values():
        if sha(selection_path.parent/'frozen'/record['file'])!=record['sha256']:raise ValueError('Frozen artifact changed before opening confirmation')
    return {name:load_part(data,part,manifest,policy) for name,part in [('global_temporal','global-test-sealed'),('global_geographic','global-geographic-test-sealed'),('lebanon_known_benchmark','lebanon-known-test'),('lebanon_fresh_confirmation','lebanon-confirmation-sealed')]}


def benchmark(data,out,policy='strict',include_sensitivity=True):
    data=Path(data);out=Path(out);out.mkdir(parents=True,exist_ok=True);models_dir=out/'frozen';models_dir.mkdir(exist_ok=True)
    manifest=json.loads((data/'dataset-manifest.json').read_text());config=manifest['config'];seed=config['seed'];started=time.perf_counter()
    if include_sensitivity and policy=='strict':
        from .filter_sensitivity import fit as fit_sensitivity
        fit_sensitivity(data,out/'filter-sensitivity',manifest,load_part,score,select_threshold)
    train_g=load_part(data,'global-train',manifest,policy);cal_g=load_part(data,'global-calibration',manifest,policy);val_g=load_part(data,'global-validation',manifest,policy)
    train_l=load_part(data,'lebanon-train',manifest,policy);cal_l=load_part(data,'lebanon-calibration',manifest,policy);val_l=load_part(data,'lebanon-validation',manifest,policy)
    if set(train_g.cell_id)&set(train_l.cell_id):raise ValueError('Lebanese cells in global pretraining')
    for a,b in [(train_g,cal_g),(cal_g,val_g),(train_l,cal_l),(cal_l,val_l)]:
        if a.window_end.max()>=b.prediction_time.min():raise ValueError('Temporal split leakage')
    print('Fit data rows/positives',{'global':[len(train_g),int(train_g.y.sum())],'lebanon':[len(train_l),int(train_l.y.sum())]},flush=True)
    all_candidates=[];retained=[];validation_predictions={};artifacts={}
    def assess(model,family,stage,tag,parameters,seconds=0,retain=False):
        pg=model.predict_proba(val_g)[:,1];pl=model.predict_proba(val_l)[:,1]
        tg,_=select_threshold(val_g.y,pg);tl,precision_targets=select_threshold(val_l.y,pl)
        identifier=f'{policy}-{family}-{stage}-{tag}'
        row={'id':identifier,'family':family,'stage':stage,'tag':str(tag),'policy':policy,'parameters':parameters,'fit_seconds':seconds,
          'global_validation':score(val_g,pg,tg),'lebanon_validation':score(val_l,pl,tl),'threshold_global':tg,'threshold_lebanon':tl,'precision_target_thresholds':precision_targets}
        all_candidates.append(row);validation_predictions[identifier]=(pg,pl)
        if retain:keep(model,row)
        return row
    def keep(model,row):
        identifier=row['id'];path=models_dir/(identifier+'.joblib')
        artifact_config=dict(config,label_product='VJ114A1.002 daily 1km; not FIRMS 375m',prediction_scope='Coverage-conditioned retrospective detected occurrence over sampled global panels and Lebanon')
        bounds={c:[float(min(train_g[c].min(),train_l[c].min())),float(max(train_g[c].max(),train_l[c].max()))] for c in FEATURES}
        artifact={'model':model,'id':identifier,'version':identifier+'-'+sha(data/'dataset-manifest.json')[:12],'features':FEATURES,'policy':policy,'config':artifact_config,'threshold':row['threshold_lebanon'],
          'model_accepts_full_frame':True,'bounds':bounds,'bounds_reference':'Union of source and Lebanese fit inputs only',
          'validated_cells':sorted(set(train_g.cell_id)|set(train_l.cell_id)),'validated_regions':sorted(set(train_g.region)|set(train_l.region)),
          'validated_products':['VJ114A1.002'],'validated_weather_sources':['NASA_POWER_HISTORICAL'],
          'evaluation_exclusions':[dict(start=manifest['conflict_policy']['start'],end_exclusive=manifest['conflict_policy']['end_exclusive'],cell_ids=manifest['conflict_excluded_cell_ids'],reason=manifest['conflict_policy']['reason'])],
          'synthetic':False,'mode':'retrospective','source_manifest_sha256':sha(data/'dataset-manifest.json'),'production_approved':False}
        joblib.dump(artifact,path,compress=3);artifacts[identifier]={'file':path.name,'sha256':sha(path)};retained.append(row)
    for family,algorithm,options in specifications():
        source_candidates=[];local_candidates=[]
        for i,params in enumerate(options):
            tick=time.perf_counter();source=fit_family(algorithm,params,train_g,seed)
            row=assess(source,family,'global',i,params,time.perf_counter()-tick);source_candidates.append((source,row))
            tick=time.perf_counter();local=fit_family(algorithm,params,train_l,seed)
            localrow=assess(local,family,'lebanon_only',i,params,time.perf_counter()-tick);local_candidates.append((local,localrow))
            print('Validation candidate',row['id'],'global AP',row['global_validation']['pr_auc_average_precision'],'Lebanon AP',row['lebanon_validation']['pr_auc_average_precision'],flush=True)
        base,source_row=max(source_candidates,key=lambda v:key(v[1]['global_validation']));local,local_row=max(local_candidates,key=lambda v:key(v[1]['lebanon_validation']))
        keep(base,source_row);keep(local,local_row)
        global_cal=PlattModel(base).fit(cal_g);assess(global_cal,family,'global_calibration','sigmoid',{'calibration_data':'global 2021'},retain=True)
        local_cal=PlattModel(base).fit(cal_l);assess(local_cal,family,'lebanon_calibration','sigmoid',{'calibration_data':'Lebanon 2021'},retain=True)
        local_control_cal=PlattModel(local).fit(cal_l);assess(local_control_cal,family,'lebanon_only_calibrated','sigmoid',{'calibration_data':'Lebanon 2021'},retain=True)
        mixtures=[]
        for weight in [.25,.75]:
            model=PlattModel(ProbabilityEnsemble(base,local,weight)).fit(cal_l)
            row=assess(model,family,'ensemble',weight,{'local_weight':weight,'calibration_data':'Lebanon 2021'});mixtures.append((model,row))
        keep(*max(mixtures,key=lambda v:key(v[1]['lebanon_validation'])))
        adapted=[]
        if algorithm=='logistic':
            for strength in [.0001,.01]:
                tick=time.perf_counter();raw=AnchoredLogistic(base,strength).fit(train_l);model=PlattModel(raw).fit(cal_l)
                row=assess(model,family,'local_adaptation',strength,{'method':'global-coefficient anchored local BCE','strength':strength,'optimization':raw.optimization},time.perf_counter()-tick);adapted.append((model,row))
        elif algorithm=='neural':
            for epochs,learning_rate,positive_weight in [(5,.0001,1),(15,.001,1),(10,.0003,10)]:
                tick=time.perf_counter();raw=fine_tune_neural(base,train_l,epochs,learning_rate,positive_weight);model=PlattModel(raw).fit(cal_l)
                row=assess(model,family,'local_adaptation',str(epochs)+'epochs_weight'+str(positive_weight),raw.adaptation,time.perf_counter()-tick);adapted.append((model,row))
        elif algorithm in {'forest','extra_trees','boosting'}:
            tick=time.perf_counter();raw=ScoreTransfer(base,algorithm,source_row['parameters'],seed).fit(train_l);model=PlattModel(raw).fit(cal_l)
            row=assess(model,family,'local_adaptation','source_score',{'method':'Local tree learns from local features plus pretrained global score; global tree weights are unchanged'},time.perf_counter()-tick);adapted.append((model,row))
        if adapted:keep(*max(adapted,key=lambda v:key(v[1]['lebanon_validation'])))
        # Pooling is a control trained from scratch, explicitly distinct from fine-tuning.
        if family in {'logistic','gradient_boosting','neural_64_32'}:
            tick=time.perf_counter();pooled=pd.concat([train_g,train_l],ignore_index=True)
            raw=fit_family(algorithm,source_row['parameters'],pooled,seed);model=PlattModel(raw).fit(cal_l)
            assess(model,family,'pooled','global_and_local',{'parameters':source_row['parameters'],'calibration_data':'Lebanon 2021'},time.perf_counter()-tick,retain=True)
            del pooled
        # Keep only the compact validation metrics; predictions are cheap to recompute.
        validation_predictions.clear()
        (out/'validation-progress.json').write_text(json.dumps({'confirmation_opened':False,'completed_family':family,'candidates':all_candidates,'retained':retained},indent=2,default=str))
        print('Completed family',family,'retained artifacts',len(retained),flush=True)
    # Select solely on validation; control winners remain reported alongside transfer winners.
    best_global=max((r for r in retained if r['stage'] in {'global','global_calibration'}),key=lambda r:key(r['global_validation']))
    best_overall=max(retained,key=lambda r:key(r['lebanon_validation']))
    best_transfer=max((r for r in retained if not r['stage'].startswith('lebanon_only')),key=lambda r:key(r['lebanon_validation']))
    codehash=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()
    selection={'frozen_at':datetime.now(timezone.utc).isoformat(),'policy':policy,'best_global':best_global['id'],'best_lebanon_overall':best_overall['id'],'best_transfer':best_transfer['id'],
      'criterion':config['primary_selection'],'confirmation_opened':False,'artifacts':artifacts,'manifest_sha256':sha(data/'dataset-manifest.json'),'code_sha256':codehash,
      'source_hyperparameters_selected_on':'Global 2022 validation','local_hyperparameters_selected_on':'Lebanon 2022 validation','seed':seed}
    legacy_path=data.parent/'noaa20-real/models/model.joblib'
    if legacy_path.exists():selection['legacy_control_sha256']=sha(legacy_path)
    selection_path=out/'selection-frozen.json';selection_path.write_text(json.dumps(selection,indent=2))
    frozen_hash=sha(selection_path)
    (out/'validation-results.json').write_text(json.dumps(all_candidates,indent=2,default=str))
    print('Selection frozen before confirmation:',best_transfer['id'],flush=True)
    # This is the first point at which reserved outcome files are opened by the trainer.
    tests=open_confirmations(data,manifest,selection_path,frozen_hash,policy)
    results=[];chosen_predictions={}
    for row in retained:
        record=dict(row);record['confirmation']={};artifact=joblib.load(models_dir/artifacts[row['id']]['file']);model=artifact['model']
        if sha(models_dir/artifacts[row['id']]['file'])!=artifacts[row['id']]['sha256']:raise ValueError('Frozen artifact changed')
        for name,frame in tests.items():
            p=model.predict_proba(frame)[:,1];threshold=row['threshold_lebanon'] if name.startswith('lebanon') else row['threshold_global']
            record['confirmation'][name]=score(frame,p,threshold,detail=row['id'] in {best_transfer['id'],best_global['id'],best_overall['id']})
            if name.startswith('lebanon'):
                record['confirmation'][name]['at_threshold_0_5']=metrics(frame.y,p,.5)
                record['confirmation'][name]['at_validation_precision_targets']={k:metrics(frame.y,p,t) if t is not None else None for k,t in row['precision_target_thresholds'].items()}
            if row['id']==best_transfer['id']:chosen_predictions[name]=p
        results.append(record);print('Confirmed frozen candidate',row['id'],flush=True)
    if legacy_path.exists():
        if sha(legacy_path)!=selection['legacy_control_sha256']:raise ValueError('Legacy reference artifact changed')
        legacy=joblib.load(legacy_path);threshold=legacy['threshold']
        record={'id':'legacy-lebanon-environment-logistic','family':'legacy_logistic','stage':'fixed_legacy_control','parameters':{'source_sha256':sha(legacy_path)},'policy':policy,'confirmation':{}}
        for name,frame in [('global_validation',val_g),('lebanon_validation',val_l),*tests.items()]:
            p=legacy['model'].predict_proba(frame[legacy['features']])[:,1]
            s=score(frame,p,threshold)
            if name.endswith('_validation'):record[name]=s
            else:record['confirmation'][name]=s
        results.append(record)
    if sha(selection_path)!=frozen_hash:raise ValueError('Selection changed during confirmation')
    uncertainty={name:bootstrap(tests[name],chosen_predictions[name],seed) for name in ['global_temporal','lebanon_fresh_confirmation']}
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'synthetic':False,'mode':'retrospective','policy':policy,'selection':selection,'selection_file_sha256':frozen_hash,'confirmation_opened_once_after_selection':True,
      'source_manifest_sha256':sha(data/'dataset-manifest.json'),'config':config,'candidates_evaluated_on_validation':len(all_candidates),'frozen_stage_winners':len(retained),
      'results':results,'best_transfer_uncertainty':uncertainty,'fit_and_evaluation_seconds':time.perf_counter()-started,'production_approved':False,
      'limitations':manifest['limitations']+['All tuning and repeated benchmarks use validation; confirmation was opened once after freezing all choices','Global panels are sampled, not the whole planet','Broad southern conflict exclusion does not establish other areas are free of conflict','Universal Lebanon adaptation may reduce global skill; those changes are reported rather than hidden']}
    (out/'benchmark-results.json').write_text(json.dumps(output,indent=2,default=str))
    csv=[]
    for r in results:
        for domain,s in [('global_validation',r['global_validation']),('lebanon_validation',r['lebanon_validation']),*r['confirmation'].items()]:
            csv.append({'id':r['id'],'family':r['family'],'stage':r['stage'],'domain':domain,**{k:s[k] for k in ['observations','positive_windows','pr_auc_average_precision','brier','precision','recall','f1','threshold','prevalence','mean_probability','site_macro_average_precision']}})
    pd.DataFrame(csv).to_csv(out/'benchmark-results.csv',index=False)
    artifact=joblib.load(models_dir/artifacts[best_transfer['id']]['file']);joblib.dump(artifact,out/'best-transfer-research.joblib',compress=3)
    winner=next(r for r in results if r['id']==best_transfer['id'])
    for name in ['global_temporal','lebanon_fresh_confirmation']:
        frame=tests[name];pred=frame[['region','cell_id','prediction_time','window_end','y']].copy();pred['probability']=chosen_predictions[name]
        pred.to_csv(out/(name+'-selected-predictions.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
    (out/'RESEARCH_ONLY.txt').write_text('Observed-weather retrospective, coverage-conditioned satellite detections. Not an approved operational forecasting model. See benchmark-results.json.\n')
    if include_sensitivity and policy=='strict':
        from .filter_sensitivity import evaluate as evaluate_sensitivity
        evaluate_sensitivity(data,out/'filter-sensitivity',manifest,open_confirmations,score)
    print(json.dumps({'best_transfer':best_transfer['id'],'best_overall':best_overall['id'],'validation_candidates':len(all_candidates),'frozen_stage_winners':len(retained),'production_approved':False}),flush=True)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--out',required=True);p.add_argument('--policy',choices=['strict','conservative'],default='strict');a=p.parse_args();benchmark(a.data,a.out,a.policy)

if __name__=='__main__':main()
