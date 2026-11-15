"""Publish frozen benchmark evidence and fixed baselines; never select or retune models."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import joblib
import numpy as np
import pandas as pd
from .benchmark_global import load_part,score
from .refit_transfer import refit_parts
from .transfer_models import SeasonalModel
from .release import build_manifest


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(root):
    root=Path(root);outputs=root/'outputs';docs=root/'docs';figures=docs/'figures';figures.mkdir(exist_ok=True)
    core_dir=outputs/'global-transfer-benchmark';refit_dir=outputs/'global-final-refit';data=outputs/'global-transfer-data';fresh=outputs/'global-2026-confirmation-data'
    core=json.loads((core_dir/'benchmark-results.json').read_text());refit=json.loads((refit_dir/'results.json').read_text());manifest=json.loads((data/'dataset-manifest.json').read_text());fresh_manifest=json.loads((fresh/'dataset-manifest.json').read_text())
    global_test=load_part(fresh,'global-test-sealed',fresh_manifest);geo_test=load_part(fresh,'global-geographic-test-sealed',fresh_manifest);local_test=load_part(data,'lebanon-confirmation-sealed',manifest)
    fit_g,cal_g=refit_parts(data,manifest,'global');fit_l,cal_l=refit_parts(data,manifest,'lebanon')
    # Fixed baseline diagnostics from the already predeclared family; no parameter search or selection.
    seasonal_g=SeasonalModel().fit(fit_g);seasonal_l=SeasonalModel().fit(fit_l);baselines={}
    for name,f,model,cal in [('global_2026_temporal',global_test,seasonal_g,cal_g),('global_2026_geographic',geo_test,seasonal_g,cal_g),('lebanon_2026_fixed_fold',local_test,seasonal_l,cal_l)]:
        baselines[name]={'seasonal':score(f,model.predict_proba(f)[:,1],.5,detail=True),
          'calibration_prevalence':score(f,np.full(len(f),cal.y.mean()),.5),'zero_probability':score(f,np.zeros(len(f)),.5)}
    baseline_record={'role':'Post-fit fixed baseline diagnostics only; no model/parameter/threshold selection','fit_end_exclusive':'2025-01-01T00:00:00Z','calibration_year':2025,'results':baselines}
    (refit_dir/'fixed-baselines.json').write_text(json.dumps(baseline_record,indent=2))
    artifact=joblib.load(refit_dir/'selected-research.joblib');chosen=refit['results']['refit_selected_transfer'];primary=chosen['lebanon_2026_fixed_fold']
    evaluation={'synthetic':False,'mode':'retrospective','test':primary,'baseline_test':baselines['lebanon_2026_fixed_fold']['seasonal'],
      'validated_cells':artifact['validated_cells'],'validated_products':artifact['validated_products'],'validated_weather_sources':artifact['validated_weather_sources'],
      'evidence':{
        'compatible_observation_coverage':{'passed':True,'source':'NASA VJ114A1.002 processed eligible-area >=0.8; coverage-conditioned target only'},
        'national_vegetation_grid':{'passed':True,'source':'NASA FIRMS geometry, MCD12Q1.061 and SRTMGL1.003; 124 Lebanese cells'},
        'historical_feature_availability':{'passed':False,'source':'Observed target-day POWER and reprocessed 2010 land cover'},
        'issued_forecast_backtest':{'passed':False,'source':'No multi-year historically issued meteorological forecast archive'},
        'independent_incident_split_review':{'passed':False,'source':'Temporal gaps do not establish independent incident identity'},
        'calibration_review':{'passed':False,'source':'15 Lebanese positive windows, zero detections at frozen threshold and source-transfer uncertainty'},
        'current_sensor_transition_review':{'passed':True,'source':'Separate active NOAA-20 VJ114A1.002 target'},
        'conflict_quality_review':{'passed':True,'source':'User-requested South/El Nabatieh quarantine from 2023-10-07; CDR/OCHA HDX; not comprehensive strike attribution'}}}
    (refit_dir/'release-evaluation.json').write_text(json.dumps(evaluation,indent=2))
    release=build_manifest(refit_dir/'release-evaluation.json',refit_dir/'selected-research.joblib',refit_dir/'release.json')
    audit={}
    for split in ['known-test','confirmation-sealed']:
        f=pd.read_csv(data/('lebanon-'+split+'.csv.gz'),usecols=['conflict_excluded','y_before_conflict_quarantine','y'])
        audit[split]={'quarantined_windows':int(f.conflict_excluded.sum()),'previously_qualified_positive_windows_quarantined':int((f.conflict_excluded&f.y_before_conflict_quarantine.eq(1)).sum()),'remaining_qualified_windows':int(f.y.notna().sum()),'remaining_positive_windows':int(f.y.fillna(0).sum())}
    # Paired month blocks compare the already frozen transfer and local control; never choose a winner here.
    selected_model=artifact['model'];local_artifact=joblib.load(refit_dir/'frozen/refit_matching_local_control.joblib')
    p=selected_model.predict_proba(local_test)[:,1];q=local_artifact['model'].predict_proba(local_test)[:,1]
    from sklearn.metrics import average_precision_score
    group=local_test.prediction_time.dt.strftime('%Y-%m').to_numpy();names=np.unique(group);blocks={n:np.flatnonzero(group==n) for n in names};rng=np.random.default_rng(manifest['config']['seed']);differences=[]
    for _ in range(100):
        idx=np.concatenate([blocks[n] for n in rng.choice(names,len(names),replace=True)]);y=local_test.y.iloc[idx]
        if y.nunique()==2:differences.append(average_precision_score(y,p[idx])-average_precision_score(y,q[idx]))
    paired={'AP_difference_transfer_minus_local':float(average_precision_score(local_test.y,p)-average_precision_score(local_test.y,q)),
      'paired_month_block_95pct':np.quantile(differences,[.025,.975]).tolist(),'resamples':100,'note':'Diagnostic only; 15 positives and 10 months make inference unstable'}
    summary={'generated_at':datetime.now(timezone.utc).isoformat(),'synthetic':False,'mode':'retrospective','production_approved':False,
      'global_scope':{'panels':24,'panel_degrees':[2,2],'training_panels':18,'geographic_holdout_panels':6,'sampling':'Two deterministic outcome-independent days/month; not exhaustive global land'},
      'initial_benchmark':{'validation_candidates':core['candidates_evaluated_on_validation'],'frozen_stage_winners':core['frozen_stage_winners'],'model_architecture_groups':8,'algorithm_types':6,'neural_architectures':3,'filter_sensitivity_models':9,'selection':core['selection']},
      'refit':refit['frozen'],'refit_results':refit['results'],'fixed_baselines':baselines,'paired_comparison':paired,'conflict_audit':audit,
      'conflict_excluded_cells':len(manifest['conflict_excluded_cell_ids']),'source_training':{'rows':manifest['global']['train']['qualified_rows'],'positive_windows':manifest['global']['train']['positive_windows']},
      'lebanon_training':{'rows':manifest['lebanon']['train']['qualified_rows'],'positive_windows':manifest['lebanon']['train']['positive_windows']},
      'uncertainty':refit['selected_uncertainty'],'release':release,
      'provenance_sha256':{'initial_dataset_manifest':sha(data/'dataset-manifest.json'),'initial_selection':sha(core_dir/'selection-frozen.json'),'fresh_global_dataset_manifest':sha(fresh/'dataset-manifest.json'),'refit_frozen':sha(refit_dir/'refit-frozen.json'),'refit_protocol':sha(root/'configs/final-refit-protocol.json')},
      'limitations':refit['limitations']}
    (docs/'global-results.json').write_text(json.dumps(summary,indent=2))
    for source,target in [(core_dir/'benchmark-results.csv',docs/'global-benchmark.csv'),(refit_dir/'results.csv',docs/'global-refit-benchmark.csv'),(core_dir/'benchmark-results.json',docs/'global-benchmark-metrics.json'),(core_dir/'filter-sensitivity/results.json',docs/'global-filter-sensitivity.json'),(refit_dir/'refit-frozen.json',docs/'global-refit-frozen.json'),(refit_dir/'release.json',docs/'global-release.json')]:shutil.copy2(source,target)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon,Rectangle,Patch
    # Compare BEFORE and AFTER for each family selected on validation, not on test outcomes.
    families=sorted({r['family'] for r in core['results'] if r['family']!='legacy_logistic'});fig,axes=plt.subplots(1,2,figsize=(13,5));y=np.arange(len(families))
    rows=[]
    for family in families:
        candidates=[r for r in core['results'] if r['family']==family]
        before=next(r for r in candidates if r['stage']=='global')
        after=max((r for r in candidates if not r['stage'].startswith('lebanon_only')),key=lambda r:(r['lebanon_validation']['pr_auc_average_precision'],-r['lebanon_validation']['brier']))
        rows.append((before,after))
    for ax,domain,title in [(axes[0],'global_temporal','Sampled global 2023–2025'),(axes[1],'lebanon_known_benchmark','Conflict-filtered Lebanese 2023–2025')]:
        ax.barh(y-.18,[a['confirmation'][domain]['pr_auc_average_precision'] for a,b in rows],height=.35,label='Global source before adaptation')
        ax.barh(y+.18,[b['confirmation'][domain]['pr_auc_average_precision'] for a,b in rows],height=.35,label='Transfer stage selected on Lebanese validation')
        ax.set(yticks=y,yticklabels=families,xlabel='Average precision',title=title);ax.legend(fontsize=8)
    fig.suptitle('Frozen candidate comparison; sampled retrospective detections, not operational forecast validation');fig.tight_layout();fig.savefig(figures/'global-before-after.png',dpi=150);plt.close(fig)
    # Newer-data refit, fixed without using confirmation scores.
    display_names={'refit_matching_global_source':'Matching global neural source','refit_selected_transfer':'Fixed global/local ensemble','refit_matching_local_control':'Local neural control','refit_validation_global_winner':'Global validation winner','original_lebanon_logistic':'Original Lebanese logistic'}
    fig,axes=plt.subplots(1,2,figsize=(12,4));labels=list(display_names.values())
    for ax,domain,title in [(axes[0],'global_2026_temporal','New sampled global 2026'),(axes[1],'lebanon_2026_fixed_fold','Lebanese 2026: only 15 positive windows')]:
        values=[refit['results'][key][domain]['pr_auc_average_precision'] for key in display_names]
        ax.barh(labels,values);ax.axvline(baselines[domain]['seasonal']['pr_auc_average_precision'],linestyle='--',color='black',label='Fixed seasonal baseline')
        ax.set(xlabel='Average precision',title=title);ax.legend(fontsize=8)
    fig.suptitle('Fixed 2018–2024 refit / 2025 calibration; Lebanese fold is a repeated comparison');fig.tight_layout();fig.savefig(figures/'global-refit-2026.png',dpi=150);plt.close(fig)
    # Calibration and global forgetting remain visible.
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,domain,title in [(axes[0],'global_2026_temporal','Global 2026 calibration'),(axes[1],'lebanon_2026_fixed_fold','Lebanese 2026 calibration')]:
        limit=0
        for identifier in ['refit_matching_global_source','refit_selected_transfer','refit_matching_local_control']:
            bins=refit['results'][identifier][domain]['quantile_reliability'];x=[b['mean_probability'] for b in bins];obs=[b['observed_fraction'] for b in bins]
            ax.plot(x,obs,'o-',label=display_names[identifier],markersize=3);limit=max([limit,*x,*obs])
        ax.plot([0,limit],[0,limit],'--',color='grey');ax.set(xlabel='Mean prediction',ylabel='Observed detected-fire fraction',title=title);ax.legend(fontsize=7)
    fig.suptitle('Probability calibration is domain-dependent; sparse Lebanese bins are unstable');fig.tight_layout();fig.savefig(figures/'global-calibration.png',dpi=150);plt.close(fig)
    # Explicit global sampling map, using the already acquired NASA map geometry.
    from shapely.geometry import shape,box
    fig,ax=plt.subplots(figsize=(12,5))
    countries=json.loads((root/'data/environment/raw/world_countries.geojson').read_text())
    for feature in countries['features']:
        geometry=shape(feature['geometry']);parts=list(geometry.geoms) if geometry.geom_type=='MultiPolygon' else [geometry]
        for polygon in parts:
            if polygon.geom_type=='Polygon' and not polygon.is_empty:ax.add_patch(Polygon(np.asarray(polygon.exterior.coords),facecolor='#eeeeee',edgecolor='#bbbbbb',linewidth=.3))
    for site in manifest['config']['sites']:
        color='#d55e00' if site['geographic_holdout'] else '#0072b2'
        ax.add_patch(Rectangle((site['west'],site['south']),2,2,facecolor=color,edgecolor=color));ax.plot(site['west']+1,site['south']+1,'o',color=color,markersize=3)
    ax.plot(35.8,33.9,'*',color='black',markersize=8,label='Lebanon');ax.set(xlim=(-180,180),ylim=(-58,70),xlabel='Longitude',ylabel='Latitude',title='24 fixed global panels: a sampled benchmark, not whole-Earth coverage')
    ax.legend(handles=[Patch(color='#0072b2',label='18 source panels'),Patch(color='#d55e00',label='6 geographic holdouts')],loc='lower left');fig.tight_layout();fig.savefig(figures/'global-sampling.png',dpi=150);plt.close(fig)
    # Country-view output with explicit scope suppression.
    risk=refit_dir/'live-research-risk/risk.png'
    if risk.exists():shutil.copy2(risk,figures/'global-transfer-research-forecast.png')
    print(json.dumps({'published':'global-results.json and comparative figures','production_approved':release['approved'],'release_failures':release['failures'],'paired_local_AP_difference':paired['AP_difference_transfer_minus_local']}),flush=True)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');a=p.parse_args();publish(a.root)

if __name__=='__main__':main()
