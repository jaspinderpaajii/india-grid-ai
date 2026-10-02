from __future__ import annotations
import io
import os
from pathlib import Path
from typing import Literal
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from backend.grid.data import ROOT
from backend.grid.service import get_service, records

app = FastAPI(title='India Grid AI', version='1.0.0', description='Historical replay of XGBoost India-wide demand forecasts.')
allowed_origins = [origin.strip() for origin in os.getenv('CORS_ORIGINS', '*').split(',') if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=False, allow_methods=['*'], allow_headers=['*'])


def service():
    try:
        return get_service()
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


def validate_horizon(horizon: int):
    if horizon not in (1, 6, 24):
        raise HTTPException(422, 'Forecast horizon must be 1, 6, or 24 hours.')


@app.get('/api/health')
def health():
    s = service()
    return {'status': 'ready', 'model': 'XGBoost', 'mode': 'historical_replay', 'trained_at': s.report['trained_at']}


@app.get('/api/meta')
def meta():
    s = service()
    return {'audit': s.audit, 'replay': s.report['replay'], 'peak_threshold_mw': s.report['peak_threshold_mw'],
            'peak_threshold_note': s.report['peak_threshold_note'], 'trained_at': s.report['trained_at'],
            'weather_note': s.report['weather_note'], 'interval_note': s.report['interval_note']}


@app.get('/api/forecast')
def forecast(origin: str | None = None, horizon: int = Query(24, ge=1, le=24), model: Literal['weather', 'demand_only'] = 'weather'):
    validate_horizon(horizon)
    try:
        return service().forecast(origin, horizon, model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/actuals')
def actuals(origin: str | None = None, horizon: int = Query(24, ge=1, le=24)):
    validate_horizon(horizon)
    try:
        return {'actuals': service().actuals(origin, horizon)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/evaluation')
def evaluation():
    return service().report


@app.get('/api/analytics')
def analytics():
    return service().analytics()


def history_frame(start, end, query):
    try:
        return service().history(start, end, query)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/history')
def history(start: str | None = None, end: str | None = None, query: str = '', page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
    frame = history_frame(start, end, query)
    pages = max(1, (len(frame) + page_size - 1) // page_size)
    page = min(page, pages)
    rows = frame.iloc[(page-1)*page_size:page*page_size]
    return {'rows': records(rows), 'total': len(frame), 'page': page, 'pages': pages, 'page_size': page_size}


@app.get('/api/history.csv')
def export_history(start: str | None = None, end: str | None = None, query: str = ''):
    frame = history_frame(start, end, query).copy()
    frame['unit_note'] = 'Demand source is already in MW; timestamp IST assumed'
    return Response(frame.to_csv(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="india-demand-history.csv"'})


@app.get('/api/forecast.csv')
def export_forecast(origin: str | None = None, horizon: int = Query(24, ge=1, le=24), model: Literal['weather', 'demand_only'] = 'weather'):
    result = forecast(origin, horizon, model)
    rows = pd.DataFrame(result['forecast'])
    rows['issued_at'] = result['origin']
    rows['model'] = model
    rows['unit_note'] = 'Demand source is already in MW'
    return Response(rows.to_csv(index=False), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="india-demand-forecast.csv"'})


@app.get('/{path:path}', include_in_schema=False)
def frontend(path: str):
    if path.startswith('api/'):
        raise HTTPException(404, 'API endpoint not found.')
    root = (ROOT / 'dist').resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(404)
    if target.is_file():
        return FileResponse(target)
    if (root / 'index.html').exists():
        return FileResponse(root / 'index.html')
    raise HTTPException(404, 'Frontend not built. Run npm run build, or npm run dev for development.')
