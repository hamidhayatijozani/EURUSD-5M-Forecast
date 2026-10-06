"""Experimental market-path engine: PST, cross-asset pulse, regime and scoring."""
from dataclasses import dataclass
from statistics import median

@dataclass(frozen=True)
class Signal:
    name: str
    direction: str
    score: float
    confidence: float
    regime: str
    contradiction: float

def _ret(xs,n): return xs[-1]/xs[-1-n]-1.0
def _sign(x): return 1.0 if x>0 else -1.0 if x<0 else 0.0
def regime(closes):
    if len(closes)<7: return "QUIET"
    v=sum(abs(closes[i]/closes[i-1]-1) for i in range(len(closes)-6,len(closes)))/6
    return "STORM" if v>0.00045 else "QUIET"

def pst_signal(closes):
    if len(closes)<12: raise ValueError("at least 12 closes")
    p=_ret(closes,1); c=(_ret(closes,3)+_ret(closes,6))/2
    signs=[_sign(closes[i]/closes[i-1]-1) for i in range(max(1,len(closes)-6),len(closes))]
    tenacity=sum(signs)/len(signs)
    score=max(-1,min(1,0.45*p/0.0005+0.35*c/0.001+0.20*tenacity))
    direction="UP" if score>0.12 else "DOWN" if score<-0.12 else "FLAT"
    contradiction=max(0,min(1,0.5*abs(_sign(p)-_sign(c))+0.5*(1-abs(tenacity))))
    confidence=max(0,min(0.99,0.5+0.4*abs(score)-0.25*contradiction))
    return Signal("EXP-006",direction,score,confidence,regime(closes),contradiction)

def cross_asset_signal(series):
    req=("EURUSD","GBPUSD","USDJPY","DXY")
    if any(k not in series or len(series[k])<12 for k in req): raise ValueError("all four aligned series need 12 closes")
    votes=[_sign(_ret(series["EURUSD"],3)),_sign(_ret(series["GBPUSD"],3)),-_sign(_ret(series["USDJPY"],3)),-_sign(_ret(series["DXY"],3))]
    pulse=sum(votes)/4
    direction="UP" if pulse>0.25 else "DOWN" if pulse<-0.25 else "FLAT"
    contradictions=sum(1 for v in votes if v and v!=_sign(pulse))/4 if pulse else 0.5
    confidence=max(0,min(0.99,0.5+0.45*abs(pulse)-0.2*contradictions))
    return Signal("EXP-007",direction,pulse,confidence,regime(series["EURUSD"]),contradictions)

def combined(series):
    a=pst_signal(series["EURUSD"]); b=cross_asset_signal(series)
    raw=0.55*a.score+0.45*b.score
    gate=0.75 if a.regime=="STORM" and a.contradiction>0.45 else 1.0
    score=max(-1,min(1,raw*gate))
    direction="UP" if score>0.12 else "DOWN" if score<-0.12 else "FLAT"
    contradiction=min(1,0.5*a.contradiction+0.5*b.contradiction)
    confidence=max(0,min(0.99,0.5+0.42*abs(score)-0.25*contradiction))
    return Signal("COMBINATION",direction,score,confidence,a.regime,contradiction)

def baseline(closes):
    from engine.forecast import forecast
    f=forecast(closes)
    return Signal("BASELINE",f.direction,max(-1,min(1,f.score/0.001)),f.confidence,f.regime,0.0)

def resolve(signal,start,end,friction=0.00002):
    move=end/start-1
    if signal.direction=="FLAT": return -abs(move)*0.15
    return (move if signal.direction=="UP" else -move)-friction

def summarize(rows):
    if not rows: return {"n":0,"hit_rate":0.0,"avg_return":0.0,"median_return":0.0}
    return {"n":len(rows),"hit_rate":sum(x>0 for x in rows)/len(rows),"avg_return":sum(rows)/len(rows),"median_return":median(rows)}
