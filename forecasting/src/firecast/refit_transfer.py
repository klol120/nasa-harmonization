"""Refit a validation-frozen recipe on newer past data without reading prior test scores."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import time
import joblib
import numpy as np
import pandas as pd
from .benchmark_global import load_part,score,select_threshold,bootstrap
from .global_data import FEATURES,build_global,export_splits
from .transfer_models import FrameModel,SeasonalModel,PlattModel,ProbabilityEnsemble,AnchoredLogistic,ScoreTransfer,fine_tune_neural


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_fresh(config_path,archive,weather,out):
    config=json.loads(Path(config_path).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
    frame=build_global(config,archive,weather);report=export_splits(frame,config,'global',out)
    manifest={'synthetic':False,'mode':'retrospective','config':config,'features':FEATURES,'global':report,'source_archive_sha256':sha(Path(archive)/'archive-report.json'),'weather_sha256':sha(weather),
      'note':'New 2026 global sampled-panel confirmation; no model metrics used to select sites/dates'}
    (out/'dataset-manifest.json').write_text(json.dumps(manifest,indent=2));return manifest


def refit_parts(data,manifest,domain):
    names=['train','calibration','validation','test-sealed' if domain=='global' else 'known-test']
    f=pd.concat([load_part(data,domain+'-'+name,manifest,'strict') for name in names],ignore_index=True)
    a=pd.Timestamp('2025-01-01T00:00:00Z');b=pd.Timestamp('2026-01-01T00:00:00Z');gap=pd.Timedelta(days=manifest['config']['embargo_days'])
    fit=f[f.window_end<a-gap].copy();cal=f[(f.prediction_time>=a+gap)&(f.window_end<b-gap)].copy()
    if fit.empty or cal.empty or fit.y.nunique()!=2 or cal.y.nunique()!=2:raise ValueError('Refit and calibration require both classes')
    if fit.window_end.max()>=cal.prediction_time.min() or cal.window_end.max()>=b:raise ValueError('Refit/calibration temporal leakage')
    if fit.conflict_excluded.any() or cal.conflict_excluded.any():raise ValueError('Conflict quarantine leaked into final fitting')
    return fit,cal


class RecipeRefitter:
    def __init__(self,global_fit,local_fit,global_cal,local_cal,old_counts,seed):
        self.frames={'global':global_fit,'local':local_fit};self.cal={'global':global_cal,'local':local_cal};self.old=old_counts;self.seed=seed;self.memo={}
    def frame_origin(self,model):
        n=model.fit_rows
        if n==self.old['global_fit']:return 'global'
        if n==self.old['local_fit']:return 'local'
        if n==self.old['global_fit']+self.old['local_fit']:return 'pooled'
        raise ValueError('Unknown original training provenance in frozen recipe')
    def refit(self,model):
        if isinstance(model,FrameModel):
            origin=self.frame_origin(model);adapt=getattr(model,'adaptation',None)
            key=(origin,model.algorithm,json.dumps(model.params,sort_keys=True),json.dumps({k:adapt[k] for k in ['epochs','learning_rate','positive_weight']} if adapt else None,sort_keys=True))
            if key in self.memo:return self.memo[key]
            frame=pd.concat([self.frames['global'],self.frames['local']],ignore_index=True) if origin=='pooled' else self.frames[origin]
            base=FrameModel(model.algorithm,model.params,self.seed).fit(frame)
            result=fine_tune_neural(base,self.frames['local'],adapt['epochs'],adapt['learning_rate'],adapt.get('positive_weight',1)) if adapt else base
            self.memo[key]=result;return result
        if isinstance(model,SeasonalModel):
            origin='global' if any(not hemisphere for hemisphere,month in model.rates) else 'local'
            return SeasonalModel().fit(self.frames[origin])
        if isinstance(model,PlattModel):
            if model.calibration_rows==self.old['global_cal']:origin='global'
            elif model.calibration_rows==self.old['local_cal']:origin='local'
            else:raise ValueError('Unknown original calibration provenance')
            return PlattModel(self.refit(model.base)).fit(self.cal[origin])
        if isinstance(model,ProbabilityEnsemble):return ProbabilityEnsemble(self.refit(model.global_model),self.refit(model.local_model),model.local_weight)
        if isinstance(model,AnchoredLogistic):return AnchoredLogistic(self.refit(model.base),model.strength).fit(self.frames['local'])
        if isinstance(model,ScoreTransfer):return ScoreTransfer(self.refit(model.base),model.algorithm,model.params,self.seed).fit(self.frames['local'])
        raise ValueError('Unsupported frozen model recipe')


def run(data,benchmark_dir,fresh_data,protocol_path,out,environment):
    data=Path(data);benchmark_dir=Path(benchmark_dir);fresh_data=Path(fresh_data);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter();protocol=json.loads(Path(protocol_path).read_text());selection_path=benchmark_dir/'selection-frozen.json'
    if sha(selection_path)!=protocol['base_selection_sha256']:raise ValueError('Original validation selection differs from fixed refit protocol')
    selection=json.loads(selection_path.read_text());manifest=json.loads((data/'dataset-manifest.json').read_text());fresh_manifest=json.loads((fresh_data/'dataset-manifest.json').read_text())
    rows=json.loads((benchmark_dir/'validation-results.json').read_text());row_by_id={r['id']:r for r in rows}
    transfer_id=protocol['fixed_transfer_id'];selected_row=row_by_id[transfer_id];family=selected_row['family']
    source_row=next(r for r in rows if r['family']==family and r['stage']=='global' and r['id'] in selection['artifacts'])
    local_row=next(r for r in rows if r['family']==family and r['stage']=='lebanon_only' and r['id'] in selection['artifacts'])
    def old_model(identifier):
        record=selection['artifacts'][identifier];path=benchmark_dir/'frozen'/record['file']
        if sha(path)!=record['sha256']:raise ValueError('Original selected artifact changed')
        return joblib.load(path)
    selected_artifact=old_model(transfer_id)
    fit_g,cal_g=refit_parts(data,manifest,'global');fit_l,cal_l=refit_parts(data,manifest,'lebanon')
    print('Fixed final refit rows/positives',{'global':[len(fit_g),int(fit_g.y.sum())],'lebanon':[len(fit_l),int(fit_l.y.sum())]},flush=True)
    old_counts={'global_fit':manifest['global']['train']['qualified_rows'],'local_fit':manifest['lebanon']['train']['qualified_rows'],
      'global_cal':manifest['global']['calibration']['qualified_rows'],'local_cal':manifest['lebanon']['calibration']['qualified_rows']}
    refitter=RecipeRefitter(fit_g,fit_l,cal_g,cal_l,old_counts,manifest['config']['seed'])
    source=refitter.refit(old_model(source_row['id'])['model']);print('Refitted matching global source',flush=True)
    adapted=refitter.refit(selected_artifact['model']);print('Refitted fixed global/local adaptation',flush=True)
    local=refitter.refit(old_model(local_row['id'])['model']);local_calibrated=PlattModel(local).fit(cal_l)
    global_champion=refitter.refit(old_model(selection['best_global'])['model']);print('Refitted original validation global winner',flush=True)
    models={'refit_matching_global_source':source,'refit_selected_transfer':adapted,'refit_matching_local_control':local,'refit_matching_local_calibrated':local_calibrated,'refit_validation_global_winner':global_champion}
    thresholds={};records={};folder=out/'frozen';folder.mkdir(exist_ok=True)
    for identifier,model in models.items():
        p=model.predict_proba(cal_l)[:,1];threshold,_=select_threshold(cal_l.y,p)
        pg=model.predict_proba(cal_g)[:,1];tg,_=select_threshold(cal_g.y,pg)
        thresholds[identifier]={'calibration_2025_lebanon_F1':threshold,'calibration_2025_global_F1':tg,
          'carried_2022_lebanon_threshold':selected_row['threshold_lebanon'] if identifier=='refit_selected_transfer' else local_row['threshold_lebanon'] if 'local_control' in identifier or 'local_calibrated' in identifier else source_row['threshold_lebanon']}
        artifact=dict(selected_artifact,model=model,id=identifier,version=identifier+'-'+sha(protocol_path)[:12],
          latest_fit={'global_rows':len(fit_g),'global_positive_windows':int(fit_g.y.sum()),'lebanon_rows':len(fit_l),'lebanon_positive_windows':int(fit_l.y.sum()),'fit_end_exclusive':'2025-01-01T00:00:00Z','calibration_year':2025},
          threshold=threshold,production_approved=False,bounds={c:[float(min(fit_g[c].min(),fit_l[c].min())),float(max(fit_g[c].max(),fit_l[c].max()))] for c in FEATURES})
        path=folder/(identifier+'.joblib');joblib.dump(artifact,path,compress=3);records[identifier]={'file':path.name,'sha256':sha(path)}
    frozen={'fixed_recipe_id':transfer_id,'base_selection_sha256':sha(selection_path),'protocol_sha256':sha(protocol_path),'artifacts':records,'thresholds':thresholds,
      'confirmation_metrics_used_for_selection':False,'global_fit_windows':len(fit_g),'local_fit_windows':len(fit_l),'calibration_global_windows':len(cal_g),'calibration_lebanon_windows':len(cal_l),
      'note':'2023-2025 source-site data are fit/calibration data for this refit, not its temporal holdout. New global 2026 is reserved. Lebanese 2026 is a repeated fixed-fold comparison, not newly independent.'}
    frozen_path=out/'refit-frozen.json';frozen_path.write_text(json.dumps(frozen,indent=2));frozen_hash=sha(frozen_path)
    print('Final recipes and thresholds frozen before new global 2026 evaluation',flush=True)
    for record in records.values():
        if sha(folder/record['file'])!=record['sha256']:raise ValueError('Refit artifact changed')
    # Only now open newly acquired global confirmation labels and the repeated Lebanese fold.
    tests={'global_2026_temporal':load_part(fresh_data,'global-test-sealed',fresh_manifest),
      'global_2026_geographic':load_part(fresh_data,'global-geographic-test-sealed',fresh_manifest),
      'lebanon_2026_fixed_fold':load_part(data,'lebanon-confirmation-sealed',manifest)}
    results={};selected_p={}
    for identifier,model in models.items():
        results[identifier]={}
        for domain,frame in tests.items():
            p=model.predict_proba(frame)[:,1];threshold=thresholds[identifier]['calibration_2025_lebanon_F1' if domain.startswith('lebanon') else 'calibration_2025_global_F1']
            result=score(frame,p,threshold,detail=True)
            if domain.startswith('lebanon'):result['at_carried_2022_threshold']=score(frame,p,thresholds[identifier]['carried_2022_lebanon_threshold'])
            results[identifier][domain]=result
            if identifier=='refit_selected_transfer':selected_p[domain]=p
        print('Compared fixed refit',identifier,flush=True)
    legacy=joblib.load(data.parent/'noaa20-real/models/model.joblib');results['original_lebanon_logistic']={}
    for domain,frame in tests.items():results['original_lebanon_logistic'][domain]=score(frame,legacy['model'].predict_proba(frame[legacy['features']])[:,1],legacy['threshold'],detail=True)
    if sha(frozen_path)!=frozen_hash:raise ValueError('Refit choice changed during evaluation')
    uncertainty={name:bootstrap(tests[name],selected_p[name],manifest['config']['seed']) for name in ['global_2026_temporal','lebanon_2026_fixed_fold']}
    report={'synthetic':False,'mode':'retrospective','production_approved':False,'protocol':protocol,'frozen':frozen,'frozen_sha256':frozen_hash,'results':results,'selected_uncertainty':uncertainty,
      'seconds':time.perf_counter()-started,'limitations':manifest['limitations']+['Lebanese 2026 is a repeated pre-fixed comparison after the first benchmark, not a new independent test','The refit uses newer known years; old 2023-2025 temporal data cannot be called held out for this artifact','Historical weather reconstruction is not operational forecast validation']}
    (out/'results.json').write_text(json.dumps(report,indent=2))
    csv=[]
    for identifier,domains in results.items():
        for domain,result in domains.items():csv.append({'model':identifier,'domain':domain,**{k:result[k] for k in ['observations','positive_windows','pr_auc_average_precision','brier','precision','recall','f1','threshold','prevalence','mean_probability','site_macro_average_precision']}})
    pd.DataFrame(csv).to_csv(out/'results.csv',index=False)
    selected=joblib.load(folder/records['refit_selected_transfer']['file']);joblib.dump(selected,out/'selected-research.joblib',compress=3)
    # A separate Lebanese view clips polygons without restricting the generic global artifact.
    national=json.loads((Path(environment)/'lebanon.geojson').read_text())['geometry']
    lebanon_view=dict(selected,analysis_geometry=national,validated_regions=['lebanon'],withhold_evaluation_exclusions=True);joblib.dump(lebanon_view,out/'lebanon-view-research.joblib',compress=3)
    print(json.dumps({'fixed_recipe':transfer_id,'models_compared':len(results),'new_global_confirmation':True,'new_independent_lebanon_confirmation':False,'production_approved':False}),flush=True)
    return report


def freeze_protocol(benchmark_dir,out):
    path=Path(benchmark_dir)/'selection-frozen.json';selection=json.loads(path.read_text())
    protocol={'base_selection_sha256':sha(path),'fixed_transfer_id':selection['best_transfer'],
      'source_and_local_fit_period':'2018 through 2024; fixed geographic and conflict exclusions','calibration_period':'2025',
      'settings':'Reuse validation-selected architecture, mixture and optimizer settings without new search',
      'selection_rule':'No confirmation score selects or changes the refit recipe',
      'confirmation_note':'Reproduction does not make previously viewed 2026 outcomes fresh again',
      'production_approved':False}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists() and json.loads(out.read_text()).get('base_selection_sha256')!=protocol['base_selection_sha256']:
        raise ValueError('Existing protocol belongs to another selection; choose a new output path')
    out.write_text(json.dumps(protocol,indent=2));return protocol


def main():
    if len(sys.argv)>1 and sys.argv[1]=='freeze-protocol':
        p=argparse.ArgumentParser(description='Capture a fixed refit recipe from validation selection without reading confirmation scores')
        p.add_argument('--benchmark',required=True);p.add_argument('--out',required=True);a=p.parse_args(sys.argv[2:]);freeze_protocol(a.benchmark,a.out);return
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['data','benchmark','fresh-data','protocol','out','environment']:p.add_argument('--'+key,required=True)
    a=p.parse_args();run(a.data,a.benchmark,a.fresh_data,a.protocol,a.out,a.environment)

if __name__=='__main__':main()
