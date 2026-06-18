import platform
platform._wmi_query=lambda *a,**k:['10.0.0','1','Multiprocessor Free','0','0']
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import date
from pathlib import Path
import numpy as np
from app.core.container import get_predictor, get_dataset_service
from app.services.predictors.horizons import resolve_horizon_config, DEFAULT_HORIZONS

p=get_predictor()
ds=get_dataset_service()
as_of=ds.resolve_default_prediction_as_of(date.today())
ctx=ds.build_context(as_of)
frame=ctx.feature_frame.sort_values('date').copy()
# Use current deterministic scoring without live news/events for all historical rows.
summary={'as_of':str(as_of),'frame_rows':int(len(frame)),'date_min':str(frame['date'].min()),'date_max':str(frame['date'].max()),'score_distribution':{},'backtests':{}}

def q(vals, quant):
    vals=[float(v) for v in vals if v==v]
    if not vals: return None
    return round(float(np.quantile(vals, quant)),2)

def bucket_defs(agent=True):
    return p._score_bucket_defs('agent_score' if agent else 'business_scorecard_score')

def hist_for(horizon):
    hc=resolve_horizon_config(horizon)
    work=frame.copy()
    work['target_date']=work['date'].shift(-hc.steps)
    work['target_price']=work['sd_gas92_market'].shift(-hc.steps)
    work['target_delta']=work['target_price']-work['sd_gas92_market']
    hist=work[(work['date'] < as_of) & (work['target_date'] <= as_of)].dropna(subset=['target_delta']).copy()
    scored=p.score_frame_for_backtest(hist, enable_refined_news=True, enable_event_risk=True, horizon=horizon)
    return scored.dropna(subset=['agent_score','business_scorecard_score','target_delta']).copy()

def evaluate(scored, score_col):
    defs=p._score_bucket_defs(score_col)
    pts=scored[score_col].map(lambda v:p._score_points(score_column=score_col, score_value=float(v)))
    scored=scored.copy()
    scored['_points']=pts
    scored['_bucket']=scored['_points'].map(lambda v:p._score_bucket_index(float(v), bucket_defs=defs))
    out=[]
    for i,b in enumerate(defs):
        vals=scored[scored['_bucket']==i]['target_delta'].astype(float).tolist()
        out.append({'bucket':b['label'],'range':b['range_label'],'n':len(vals),'p25':q(vals,.25),'p50':q(vals,.5),'p75':q(vals,.75),'up_rate':round(sum(1 for v in vals if v>0)/len(vals),3) if vals else None})
    return out

for horizon in DEFAULT_HORIZONS:
    scored=hist_for(horizon)
    summary['backtests'][horizon]={
        'n':int(len(scored)),
        'agent_buckets':evaluate(scored,'agent_score'),
        'business_buckets':evaluate(scored,'business_scorecard_score'),
    }
    for col in ['agent_score','business_scorecard_score']:
        pts=[p._score_points(score_column=col, score_value=float(v)) for v in scored[col].dropna().tolist()]
        summary['score_distribution'][f'{horizon}_{col}']={k:q(pts,qq) for k,qq in {'min':0,'q05':.05,'q10':.1,'q25':.25,'q50':.5,'q75':.75,'q90':.9,'q95':.95,'max':1}.items()}

Path('artifacts/score_bucket_system_full_history_backtest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'as_of':summary['as_of'],'rows':summary['frame_rows'],'date_min':summary['date_min'],'date_max':summary['date_max'],'score_distribution':summary['score_distribution']},ensure_ascii=False,indent=2))
for h in DEFAULT_HORIZONS:
    print('\n',h,'n=',summary['backtests'][h]['n'])
    print('agent', summary['backtests'][h]['agent_buckets'])
    print('business', summary['backtests'][h]['business_buckets'])
