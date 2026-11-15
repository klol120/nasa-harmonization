"""Read-only inference API. Synthetic/unapproved releases never pass readiness."""
from contextlib import asynccontextmanager
from datetime import datetime,timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import uuid
import joblib
import pandas as pd
from fastapi import FastAPI,HTTPException,Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field
from .inference import predict_frame
from .release import EXPECTED_CHECKS

class ForecastRequest(BaseModel):
    records:list[dict]=Field(min_length=1,max_length=10000)


def load_release(model_path,manifest_path):
    if not model_path or not manifest_path:return None,['model_or_manifest_not_configured']
    try:
        manifest=json.loads(Path(manifest_path).read_text())
        if manifest.get('approved') is not True or not EXPECTED_CHECKS<=set(manifest.get('checks',{})) or any(manifest['checks'][k] is not True for k in EXPECTED_CHECKS):return None,['release_not_approved']
        if hashlib.sha256(Path(model_path).read_bytes()).hexdigest()!=manifest.get('model_sha256'):return None,['model_checksum_mismatch']
        artifact=joblib.load(model_path) # only trusted publisher artifacts mounted read-only
        if artifact['config'].get('synthetic') is not False:return None,['synthetic_model_forbidden']
        if artifact['config'].get('mode')!='archived_forecast':return None,['retrospective_model_forbidden']
        for field in ['validated_cells','validated_products','validated_weather_sources']:
            if not manifest.get(field):return None,['missing_'+field]
            artifact[field]=set(manifest[field])
        return artifact,[]
    except Exception:
        logging.getLogger(__name__).error('release_load_failed')
        return None,['release_load_failed']


def create_app(model_path=None,manifest_path=None,api_key=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.artifact,app.state.failures=load_release(model_path or os.getenv('FIRECAST_MODEL'),manifest_path or os.getenv('FIRECAST_RELEASE'))
        app.state.api_key=api_key or os.getenv('FIRECAST_API_KEY','')
        if not app.state.api_key:app.state.failures.append('api_key_not_configured')
        yield
    app=FastAPI(title='Lebanon detected-fire occurrence',version='0.1.0',lifespan=lifespan)

    @app.get('/healthz')
    def health():return {'status':'live'}

    @app.get('/readyz')
    def ready():
        failures=app.state.failures
        return JSONResponse(status_code=503 if failures else 200,content={'ready':not failures,'failures':failures})

    @app.post('/forecast')
    def forecast(request:ForecastRequest,x_api_key:str=Header(default='')):
        if app.state.failures:raise HTTPException(503,detail='No approved operational model is ready')
        if not hmac.compare_digest(x_api_key,app.state.api_key):raise HTTPException(401,detail='Invalid API key')
        frame=pd.DataFrame(request.records)
        try:
            now=pd.Timestamp(datetime.now(timezone.utc))
            for col in ['issue_time','available_at']:
                values=pd.to_datetime(frame[col],utc=True,errors='raise')
                if values.isna().any() or (values>now).any():raise ValueError('Forecast is not available at server time')
            records=predict_frame(app.state.artifact,frame,strict_domain=True)
        except (ValueError,KeyError,TypeError):raise HTTPException(422,detail='Invalid feature, timestamp or grid contract')
        request_id=str(uuid.uuid4())
        logging.getLogger(__name__).info('forecast request_id=%s rows=%d withheld=%d',request_id,len(records),sum(r['probability'] is None for r in records))
        return {'request_id':request_id,'target':'satellite_detected_vegetation_fire_occurrence','predictions':records}
    return app

app=create_app()
