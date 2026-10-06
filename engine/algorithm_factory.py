"""Algorithm factory and adaptive selector."""
from dataclasses import dataclass
from engine.patterns import deep_candle_score

@dataclass(frozen=True)
class Candidate:
    name:str; score:float; predicted_return:float

def _clip(x): return max(-1.0,min(1.0,x))
def _ret(xs,n): return xs[-1]/xs[-1-n]-1

def generate_candidates(closes,ohlc):
    if len(closes)<30 or len(ohlc)<30: raise ValueError("need 30 closed candles")
    scale=max(sum(x[1]-x[2] for x in ohlc[-20:])/20,1e-9)
    out=[]
    for n in (2,5,10,20):
        r=_ret(closes,n); out.append(Candidate(f"MOM_{n}",_clip(r/scale),r*0.65))
    for n in (5,10,20):
        mean=sum(closes[-n:])/n; r=(mean-closes[-1])/closes[-1]
        out.append(Candidate(f"MEANREV_{n}",_clip((mean-closes[-1])/scale),r*0.65))
    hi=max(x[1] for x in ohlc[-10:-1]); lo=min(x[2] for x in ohlc[-10:-1])
    r=(closes[-1]-(hi+lo)/2)/closes[-1]
    out.append(Candidate("BREAKOUT_10",_clip((closes[-1]-(hi+lo)/2)/scale),r*0.70))
    p,_=deep_candle_score(ohlc); out.append(Candidate("CANDLE_STRUCTURE",p,p*0.0005))
    recent=sum(x[1]-x[2] for x in ohlc[-5:])/5; old=sum(x[1]-x[2] for x in ohlc[-20:])/20
    z=_clip((recent/old-1)*0.5) if old else 0.0
    out.append(Candidate("VOL_REGIME",z,z*0.0005))
    return out

def adaptive_ensemble(closes,ohlc,state):
    candidates=generate_candidates(closes,ohlc); stats=state.setdefault("algorithms",{})
    vals=[]; weights=[]
    for c in candidates:
        st=stats.setdefault(c.name,{"n":0,"mae":0.0005,"bias":0.0})
        w=1.0/(st["mae"]+0.00002); vals.append(c.score*w); weights.append(w)
    score=_clip(sum(vals)/sum(weights)); return score,score*0.0005,candidates

def update_algorithm_stats(state,candidates,actual):
    stats=state.setdefault("algorithms",{})
    for c in candidates:
        st=stats.setdefault(c.name,{"n":0,"mae":0.0005,"bias":0.0})
        err=actual-c.predicted_return; st["n"]+=1
        st["mae"]=0.95*st["mae"]+0.05*abs(err)
        st["bias"]=0.95*st["bias"]+0.05*err
