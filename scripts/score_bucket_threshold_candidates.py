import platform
platform._wmi_query=lambda *a,**k:['10.0.0','1','Multiprocessor Free','0','0']
import csv, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from datetime import date
from app.core.container import get_predictor, get_dataset_service
from app.services.predictors.horizons import resolve_horizon_config, DEFAULT_HORIZONS

p=get_predictor(); ds=get_dataset_service(); as_of=ds.resolve_default_prediction_as_of(date.today())
ctx=ds.build_context(as_of); frame=ctx.feature_frame.sort_values('date').copy()

def q(vals, quant):
    vals=[float(v) for v in vals if v==v]
    if not vals: return None
    return float(np.quantile(vals, quant)) if vals else None

def make_defs(th):
    labels=['强空','偏空','弱空','震荡','弱多','偏多','强多']
    bounds=[-math.inf,*th,math.inf]
    return [{'label':labels[i],'lower':bounds[i],'upper':bounds[i+1],'range_label':str((bounds[i],bounds[i+1])),'polarity':-1 if i<3 else 0 if i==3 else 1} for i in range(7)]

def bucket_idx(x, defs):
    for i,b in enumerate(defs):
        if b['lower'] <= x < b['upper']: return i
    return 6

def score_points(col, v):
    return p._score_points(score_column=col, score_value=float(v))

def scored_for(horizon):
    hc=resolve_horizon_config(horizon)
    work=frame.copy(); work['target_date']=work['date'].shift(-hc.steps); work['target_price']=work['sd_gas92_market'].shift(-hc.steps); work['target_delta']=work['target_price']-work['sd_gas92_market']
    hist=work[(work['date'] < as_of) & (work['target_date'] <= as_of)].dropna(subset=['target_delta']).copy()
    scored=p.score_frame_for_backtest(hist, enable_refined_news=False, enable_event_risk=False, horizon=horizon)
    return scored.dropna(subset=['agent_score','business_scorecard_score','target_delta']).copy()

def evaluate(scored, col, th):
    defs=make_defs(th)
    rows=[]
    by=[[] for _ in range(7)]
    for _,r in scored.iterrows():
        sp=score_points(col, r[col]); delta=float(r['target_delta']); bi=bucket_idx(sp,defs)
        rows.append((sp,delta,bi)); by[bi].append(delta)
    # prediction using same bucket, merge adjacent if <12
    preds=[]
    for sp,delta,bi in rows:
        sample=list(by[bi])
        if len(sample)<12:
            sample=[]
            for j in [bi-1,bi,bi+1]:
                if 0<=j<7: sample += by[j]
        pred=q(sample,.5) if sample else 0.0
        preds.append((pred,delta))
    mae=sum(abs(a-b) for a,b in preds)/len(preds)
    rmse=math.sqrt(sum((a-b)**2 for a,b in preds)/len(preds))
    stats=[]; penalty=0
    for i,b in enumerate(defs):
        vals=by[i]
        med=q(vals,.5); n=len(vals)
        pol=b['polarity']
        if n>0 and n<12: penalty += (12-n)*5
        # direction penalty only for enough samples
        if n>=12 and pol<0 and med is not None and med>0: penalty += abs(med)*2+50
        if n>=12 and pol>0 and med is not None and med<0: penalty += abs(med)*2+50
        if n>=12 and pol==0 and med is not None and abs(med)>30: penalty += abs(med)
        stats.append({'bucket':b['label'],'range':[b['lower'],b['upper']],'n':n,'p25':None if not vals else round(q(vals,.25),2),'p50':None if not vals else round(med,2),'p75':None if not vals else round(q(vals,.75),2),'up_rate':None if not vals else round(sum(1 for v in vals if v>0)/n,3)})
    return {'mae':round(mae,2),'rmse':round(rmse,2),'penalty':round(penalty,2),'objective':round(mae+penalty,2),'stats':stats}

agent_candidates=[[-20,-12,-5,5,15,25],[-15,-9,-3,3,10,20],[-15,-9,0,15,25,35],[-12,-6,0,18,28,38],[-20,-10,0,20,30,40],[-25,-15,-5,10,25,35]]
biz_candidates=[[-20,-12,-4,4,10,18],[-30,-15,-5,5,15,30],[-20,-10,-1,1,8,15],[-15,-8,-1,1,8,15],[-25,-15,-5,5,10,15]]
result={'as_of':str(as_of),'candidates':{}}
for h in DEFAULT_HORIZONS:
    scored=scored_for(h)
    result['candidates'][h]={'agent':[], 'business':[]}
    for th in agent_candidates:
        result['candidates'][h]['agent'].append({'thresholds':th, **evaluate(scored,'agent_score',th)})
    for th in biz_candidates:
        result['candidates'][h]['business'].append({'thresholds':th, **evaluate(scored,'business_scorecard_score',th)})
    result['candidates'][h]['agent'].sort(key=lambda x:x['objective'])
    result['candidates'][h]['business'].sort(key=lambda x:x['objective'])
Path('artifacts/score_bucket_threshold_candidates.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for h in DEFAULT_HORIZONS:
    print('\n',h)
    print('agent best', result['candidates'][h]['agent'][0]['thresholds'], {k:result['candidates'][h]['agent'][0][k] for k in ['mae','rmse','penalty','objective']})
    print('business best', result['candidates'][h]['business'][0]['thresholds'], {k:result['candidates'][h]['business'][0][k] for k in ['mae','rmse','penalty','objective']})
