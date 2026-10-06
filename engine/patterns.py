"""Deep closed-candle feature and pattern engine.

No future bars are read. Patterns are descriptive hypotheses; predictive value must be earned by the live resolver.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Candle:
    o: float; h: float; l: float; c: float

def _clip(x): return max(-1.0,min(1.0,x))
def _sgn(x): return 1 if x>0 else -1 if x<0 else 0
def candles(ohlc): return [Candle(*x) for x in ohlc]

def features(ohlc):
    cs=candles(ohlc)
    if len(cs)<20: raise ValueError("at least 20 closed OHLC candles")
    out=[]
    for x in cs:
        rng=max(x.h-x.l,1e-12); body=x.c-x.o
        out.append({"body":body/rng,"upper":(x.h-max(x.o,x.c))/rng,
                    "lower":(min(x.o,x.c)-x.l)/rng,"range":rng,
                    "close_pos":(x.c-x.l)/rng})
    return out

def pattern_scores(ohlc):
    f=features(ohlc); a=f[-1]
    score=0.0; names=[]
    ca,cp=candles(ohlc[-1:])[0],candles(ohlc[-2:])[0]
    if a["lower"]>0.55 and a["body"]<0.30:
        score += 0.35 if a["close_pos"]>0.55 else -0.10; names.append("HAMMER")
    if a["upper"]>0.55 and a["body"]<0.30:
        score -= 0.35 if a["close_pos"]<0.45 else 0.10; names.append("SHOOTING_STAR")
    if ca.c>ca.o and cp.c<cp.o and ca.o<=cp.c and ca.c>=cp.o:
        score+=0.45; names.append("BULLISH_ENGULFING")
    if ca.c<ca.o and cp.c>cp.o and ca.o>=cp.c and ca.c<=cp.o:
        score-=0.45; names.append("BEARISH_ENGULFING")
    if ca.h<=cp.h and ca.l>=cp.l:
        names.append("INSIDE_BAR"); score += 0.10*_sgn(ca.c-ca.o)
    if ca.h>=cp.h and ca.l<=cp.l:
        names.append("OUTSIDE_BAR"); score += 0.12*_sgn(ca.c-ca.o)
    last3=candles(ohlc[-3:])
    if all(x.c>x.o for x in last3): score+=0.25; names.append("THREE_BULL")
    if all(x.c<x.o for x in last3): score-=0.25; names.append("THREE_BEAR")
    recent=[x["range"] for x in f[-6:]]
    base=sum(recent[:-1])/5
    if recent[-1]>base*1.8: score += 0.12*_sgn(ca.c-ca.o); names.append("RANGE_EXPANSION")
    if recent[-1]<base*0.55: names.append("RANGE_COMPRESSION")
    return _clip(score),tuple(names)

def structure_score(ohlc):
    cs=candles(ohlc); closes=[x.c for x in cs]
    def ret(n): return closes[-1]/closes[-1-n]-1
    scale=max(sum(x.h-x.l for x in cs[-20:])/20,1e-9)
    raw=0.45*ret(1)/scale+0.35*ret(3)/(scale*1.5)+0.20*ret(8)/(scale*3)
    return _clip(raw)

def deep_candle_score(ohlc):
    p,names=pattern_scores(ohlc); s=structure_score(ohlc)
    return _clip(0.42*p+0.58*s),names
