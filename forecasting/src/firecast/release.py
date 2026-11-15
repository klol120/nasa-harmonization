"""Release checks: deployability never substitutes for real operational validation."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

REQUIRED_EVIDENCE=['compatible_observation_coverage','national_vegetation_grid','historical_feature_availability',
 'issued_forecast_backtest','independent_incident_split_review','calibration_review','current_sensor_transition_review']

EXPECTED_CHECKS=set(REQUIRED_EVIDENCE)|{'real_data','operational_forecast_mode','test_sample_size','test_span','better_pr_auc','better_brier','validated_domain'}

def assess_release(evaluation):
    checks={}
    checks['real_data']=evaluation.get('synthetic') is False
    checks['operational_forecast_mode']=evaluation.get('mode')=='archived_forecast'
    for key in REQUIRED_EVIDENCE:
        record=evaluation.get('evidence',{}).get(key,{})
        checks[key]=record.get('passed') is True and bool(record.get('source'))
    test=evaluation.get('test',{});baseline=evaluation.get('baseline_test',{})
    checks['test_sample_size']=test.get('positive_windows',0)>=200
    try:
        checks['test_span']=(datetime.fromisoformat(test['end'].replace('Z','+00:00'))-datetime.fromisoformat(test['start'].replace('Z','+00:00'))).days>=730
    except (KeyError,TypeError,ValueError):checks['test_span']=False
    checks['better_pr_auc']=isinstance(test.get('pr_auc_average_precision'),(int,float)) and isinstance(baseline.get('pr_auc_average_precision'),(int,float)) and test['pr_auc_average_precision']>baseline['pr_auc_average_precision']
    checks['better_brier']=isinstance(test.get('brier'),(int,float)) and isinstance(baseline.get('brier'),(int,float)) and test['brier']<baseline['brier']
    checks['validated_domain']=bool(evaluation.get('validated_cells')) and bool(evaluation.get('validated_products')) and bool(evaluation.get('validated_weather_sources'))
    return {'approved':all(checks.values()),'checks':checks,'failures':[k for k,v in checks.items() if not v],
      'note':'Passing these checks is a minimum research-to-deployment gate, not a guarantee of emergency-warning reliability'}

def build_manifest(evaluation_path,model_path,out):
    evaluation_path=Path(evaluation_path);model_path=Path(model_path)
    evaluation=json.loads(evaluation_path.read_text());result=assess_release(evaluation)
    result.update(model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),evaluation_sha256=hashlib.sha256(evaluation_path.read_bytes()).hexdigest(),
      generated_at=datetime.now(timezone.utc).isoformat(),validated_cells=evaluation.get('validated_cells',[]),
      validated_products=evaluation.get('validated_products',[]),validated_weather_sources=evaluation.get('validated_weather_sources',[]))
    Path(out).write_text(json.dumps(result,indent=2))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evaluation',required=True);p.add_argument('--model',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    result=build_manifest(a.evaluation,a.model,a.out)
    print(json.dumps({'approved':result['approved'],'failures':result['failures']}))
    if not result['approved']:raise SystemExit(2)

if __name__=='__main__':main()
