import csv, json, math, statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import psycopg

DSN='postgresql://postgres:jingbo%40123@127.0.0.1:5432/postgres'
INDICATORS = [
    'sd_gas92_market','cn_gas92_market','east_china_gas92_market','north_china_gas92_market','south_china_gas92_market','central_china_gas92_market','northwest_gas92_market','southwest_gas92_market','northeast_gas92_market',
    'shandong_cdu_utilization_weekly','sd_refining_profit','sales_production_ratio_d1','sales_production_ratio_w1_avg','sales_production_ratio_monthly_avg',
    'brent_active_settlement','brent_change_1d','gas_price_change_1d','gas_price_change_3d'
]

def clip(x,a,b): return max(a,min(b,x))
def f(v):
    try:
        if v is None: return None
        return float(v)
    except Exception: return None

def bucket_score(v, rules):
    if v is None: return 0.0
    for lo, hi, score in rules:
        if lo is not None and v < lo: continue
        if hi is not None and v >= hi: continue
        return float(score)
    return 0.0

def percentile(values, x):
    vals=sorted(v for v in values if v is not None)
    if not vals or x is None: return None
    n=sum(1 for v in vals if v <= x)
    return n/len(vals)*100.0

def inv_pct_score(pct, max_score=40):
    if pct is None: return 0.0
    return clip((50.0-pct)/50.0*max_score, -max_score, max_score)

def quantile(vals, q):
    vals=sorted(vals)
    if not vals: return None
    pos=(len(vals)-1)*q
    lo=math.floor(pos); hi=math.ceil(pos)
    if lo==hi: return vals[lo]
    return vals[lo]*(hi-pos)+vals[hi]*(pos-lo)

def bucket_index(x, defs):
    for i,(label,lo,hi) in enumerate(defs):
        if lo <= x < hi: return i
    return len(defs)-1

def eval_thresholds(rows, score_col, defs, horizon_steps):
    usable=[]
    by_bucket=defaultdict(list)
    for r in rows:
        idx=r.get('idx')
        target_idx=idx+horizon_steps
        if target_idx >= len(rows): continue
        cur=f(r.get('sd_gas92_market')); tgt=f(rows[target_idx].get('sd_gas92_market'))
        s=f(r.get(score_col))
        if cur is None or tgt is None or s is None: continue
        delta=tgt-cur
        bi=bucket_index(s, defs)
        by_bucket[bi].append(delta)
        usable.append((s,delta,bi))
    metrics=[]
    preds=[]
    for s,delta,bi in usable:
        sample=by_bucket[bi]
        if len(sample) < 12:
            # merge adjacent one step
            sample=[]
            for j in [bi-1,bi,bi+1]:
                if 0<=j<len(defs): sample += by_bucket[j]
        pred=quantile(sample,0.5) if sample else 0.0
        preds.append((pred,delta,bi))
    mae=sum(abs(p-d) for p,d,_ in preds)/len(preds) if preds else None
    rmse=math.sqrt(sum((p-d)**2 for p,d,_ in preds)/len(preds)) if preds else None
    bucket_stats=[]
    for i,(label,lo,hi) in enumerate(defs):
        vals=by_bucket[i]
        bucket_stats.append({
            'bucket':label,'range':f'{lo:g}~{hi:g}'.replace('-inf','<= ').replace('inf','>= '),'n':len(vals),
            'p25':round(quantile(vals,.25),2) if vals else None,
            'p50':round(quantile(vals,.5),2) if vals else None,
            'p75':round(quantile(vals,.75),2) if vals else None,
            'up_rate':round(sum(1 for v in vals if v>0)/len(vals),3) if vals else None,
        })
    return {'n':len(preds),'mae':round(mae,2) if mae is not None else None,'rmse':round(rmse,2) if rmse is not None else None,'buckets':bucket_stats}

conn=psycopg.connect(DSN)
cur=conn.cursor()
cur.execute('''
select i.indicator_code, t.dt, avg(t.value_num)::float
from oil_research.fact_market_timeseries t
join oil_research.dim_indicator i on i.indicator_id=t.indicator_id
where i.indicator_code = any(%s) and t.value_num is not null
group by i.indicator_code,t.dt
order by t.dt
''',(INDICATORS,))
by_date=defaultdict(dict)
for code,dt,val in cur.fetchall():
    by_date[dt][code]=float(val)
dates=sorted(by_date)
# rolling histories
util_values=[]
rows=[]
for dt in dates:
    r={'date':dt}
    r.update(by_date[dt])
    price=f(r.get('sd_gas92_market'))
    if price is None: continue
    util=f(r.get('shandong_cdu_utilization_weekly'))
    util_pct=percentile(util_values, util)
    if util is not None: util_values.append(util)
    # momentum fallback from price if missing
    prev1 = rows[-1]['sd_gas92_market'] if rows else None
    prev3 = rows[-3]['sd_gas92_market'] if len(rows)>=3 else None
    mom1 = f(r.get('gas_price_change_1d'))
    if mom1 is None and prev1 is not None: mom1=price-prev1
    mom3 = f(r.get('gas_price_change_3d'))
    if mom3 is None and prev3 is not None: mom3=price-prev3
    # simplified agent score current formulas
    brent_change=f(r.get('brent_change_1d'))
    crude_raw=bucket_score(brent_change, [(3,None,55),(2,3,42),(1,2,28),(.5,1,14),(-.5,.5,0),(-1,-.5,-14),(-2,-1,-28),(-3,-2,-42),(None,-3,-55)])
    crude_contrib=(crude_raw/65)*0.22
    spreads=[]
    for col in ['east_china_gas92_market','north_china_gas92_market','south_china_gas92_market','central_china_gas92_market','northwest_gas92_market','southwest_gas92_market','northeast_gas92_market']:
        v=f(r.get(col))
        if v is not None: spreads.append(v-price)
    avg_spread=sum(spreads)/len(spreads) if spreads else None
    sd_cn = price - f(r.get('cn_gas92_market')) if f(r.get('cn_gas92_market')) is not None else None
    market_raw=clip((0 if avg_spread is None else clip(avg_spread/120*65,-65,65)) + (0 if sd_cn is None else clip((-sd_cn)/90*20,-20,20)) + (0 if mom3 is None else clip(mom3/80*15,-15,15)), -100,100)
    market_contrib=(market_raw/100)*0.16
    util_change = (util - rows[-1].get('shandong_cdu_utilization_weekly')) if (util is not None and rows and rows[-1].get('shandong_cdu_utilization_weekly') is not None) else None
    profit=f(r.get('sd_refining_profit'))
    supply_raw=clip(inv_pct_score(util_pct,40)+(0 if util_change is None or abs(util_change)<.01 else clip(-util_change/5*12,-12,12))+(0 if profit is None else clip(-profit/600*10,-10,10)), -100,100)
    supply_contrib=(supply_raw/62)*0.20
    ratio=f(r.get('sales_production_ratio_d1')) or f(r.get('sales_production_ratio_w1_avg'))
    ratio_raw=bucket_score(ratio, [(110,None,60),(100,110,36),(95,100,22),(90,95,10),(85,90,0),(70,85,-34),(None,70,-60)])
    demand_raw=clip(ratio_raw, -100,100)
    demand_contrib=(demand_raw/100)*0.18
    # policy/news unknown -> 0 in historical full deterministic simplification
    total_weight=.22+.16+.20+.18+.12+.12
    agent=(crude_contrib+market_contrib+supply_contrib+demand_contrib)/total_weight*100
    # business approximate from current YAML main numeric items
    b_crude=bucket_score(brent_change, [(1.5,None,40),(.5,1.5,20),(-.5,.5,0),(-1.5,-.5,-20),(None,-1.5,-40)])
    b_supply=bucket_score(util, [(None,25,15),(25,45,8),(45,55,0),(55,75,-8),(75,None,-15)])
    b_demand=bucket_score(ratio, [(120,None,30),(105,120,15),(100,105,5),(95,100,0),(85,95,-5),(70,85,-15),(None,70,-30)])
    business=clip(b_crude+b_supply+b_demand, -100,100)
    r['agent_score_points']=agent
    r['business_scorecard_score']=business
    r['idx']=len(rows)
    rows.append(r)

agent_current=[('强空',-math.inf,-15),('偏空',-15,-9),('弱空',-9,-3),('震荡',-3,3),('弱多',3,10),('偏多',10,20),('强多',20,math.inf)]
biz_current=[('强空',-math.inf,-20),('偏空',-20,-12),('弱空',-12,-4),('震荡',-4,4),('弱多',4,10),('偏多',10,18),('强多',18,math.inf)]
agent_quantile=[('强空',-math.inf,-20),('偏空',-20,-10),('弱空',-10,-3),('震荡',-3,3),('弱多',3,10),('偏多',10,25),('强多',25,math.inf)]
biz_quantile=[('强空',-math.inf,-30),('偏空',-30,-15),('弱空',-15,-5),('震荡',-5,5),('弱多',5,15),('偏多',15,30),('强多',30,math.inf)]
summary={'row_count':len(rows),'date_min':str(rows[0]['date']),'date_max':str(rows[-1]['date']),'score_distribution':{},'backtests':{}}
for col in ['agent_score_points','business_scorecard_score']:
    vals=[r[col] for r in rows if r.get(col) is not None]
    summary['score_distribution'][col]={k:round(quantile(vals,q),2) for k,q in {'min':0,'q05':.05,'q10':.1,'q25':.25,'q50':.5,'q75':.75,'q90':.9,'q95':.95,'max':1}.items()}
for horizon,steps in {'D1':1,'D3':3,'W1':5,'M1':20}.items():
    summary['backtests'][horizon]={
        'agent_current':eval_thresholds(rows,'agent_score_points',agent_current,steps),
        'agent_quantile_candidate':eval_thresholds(rows,'agent_score_points',agent_quantile,steps),
        'business_current':eval_thresholds(rows,'business_scorecard_score',biz_current,steps),
        'business_wider_candidate':eval_thresholds(rows,'business_scorecard_score',biz_quantile,steps),
    }
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/score_bucket_full_history_backtest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:summary[k] for k in ['row_count','date_min','date_max','score_distribution']},ensure_ascii=False,indent=2))
for h,v in summary['backtests'].items():
    print(h, {name:{'n':m['n'],'mae':m['mae'],'rmse':m['rmse']} for name,m in v.items()})
