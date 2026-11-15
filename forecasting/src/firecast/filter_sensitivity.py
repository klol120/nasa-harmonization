"""Predeclared conservative-policy controls frozen before primary confirmation opens."""
import hashlib
import json
from pathlib import Path
import joblib
from .transfer_models import FrameModel,SeasonalModel,PlattModel


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fit(data,out,manifest,loader,scorer,threshold_selector):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);folder=out/'frozen';folder.mkdir(exist_ok=True)
    frames={name:loader(data,name,manifest,'conservative') for name in ['global-train','global-calibration','global-validation','lebanon-train','lebanon-calibration','lebanon-validation']}
    results=[];artifacts={};seed=manifest['config']['seed']
    specs=[('seasonal','seasonal',{}),('logistic','logistic',{'C':1.}),('gradient_boosting','boosting',{'max_iter':100,'max_leaf_nodes':15,'l2_regularization':2})]
    for family,algorithm,params in specs:
        source=SeasonalModel().fit(frames['global-train']) if algorithm=='seasonal' else FrameModel(algorithm,params,seed).fit(frames['global-train'])
        local=SeasonalModel().fit(frames['lebanon-train']) if algorithm=='seasonal' else FrameModel(algorithm,params,seed).fit(frames['lebanon-train'])
        calibrated=PlattModel(source).fit(frames['lebanon-calibration'])
        for stage,model in [('global',source),('lebanon_only',local),('lebanon_calibration',calibrated)]:
            row={'id':f'conservative-{family}-{stage}','policy':'conservative','family':family,'stage':stage,'parameters':params}
            for domain in ['global','lebanon']:
                f=frames[domain+'-validation'];p=model.predict_proba(f)[:,1];threshold,_=threshold_selector(f.y,p)
                row[domain+'_validation']=scorer(f,p,threshold);row['threshold_'+domain]=threshold
            path=folder/(row['id']+'.joblib');joblib.dump({'model':model,'mode':'retrospective','synthetic':False,'production_approved':False},path,compress=3)
            artifacts[row['id']]={'file':path.name,'sha256':file_hash(path)};results.append(row)
        print('Conservative sensitivity frozen family',family,flush=True)
    best=max((r for r in results if r['stage']!='lebanon_only'),key=lambda r:(r['lebanon_validation']['pr_auc_average_precision'],-r['lebanon_validation']['brier']))
    selection={'best_transfer':best['id'],'artifacts':artifacts,'policy':'conservative','confirmation_opened':False,'primary_selection':False,'note':'Predeclared sensitivity; these population-changing results never choose the primary filtering policy'}
    (out/'selection-frozen.json').write_text(json.dumps(selection,indent=2));(out/'validation-results.json').write_text(json.dumps(results,indent=2))
    return selection


def evaluate(data,out,manifest,opener,scorer):
    out=Path(out);path=out/'selection-frozen.json';frozen_hash=file_hash(path);selection=json.loads(path.read_text())
    tests=opener(data,manifest,path,frozen_hash,'conservative');results=json.loads((out/'validation-results.json').read_text())
    for row in results:
        model=joblib.load(out/'frozen'/selection['artifacts'][row['id']]['file'])['model'];row['confirmation']={}
        for domain,f in tests.items():
            threshold=row['threshold_lebanon'] if domain.startswith('lebanon') else row['threshold_global']
            row['confirmation'][domain]=scorer(f,model.predict_proba(f)[:,1],threshold)
    report={'primary_policy_selected_here':False,'policy':'conservative','selection_sha256':frozen_hash,'results':results,'note':'Same southern conflict quarantine; different confidence-filter populations. Do not choose a filtering policy by comparing Brier on different targets.'}
    (out/'results.json').write_text(json.dumps(report,indent=2));return report
