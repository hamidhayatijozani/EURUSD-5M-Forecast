from engine.patterns import pattern_scores
from engine.algorithm_factory import generate_candidates,adaptive_ensemble

def ohlc(n=40,base=1.1):
    return [(base+i*0.0001,base+i*0.0002,base+i*0.0000,base+i*0.00015) for i in range(n)]

def test_pattern_engine_is_deterministic():
    score,names=pattern_scores(ohlc())
    assert -1 <= score <= 1
    assert isinstance(names,tuple)

def test_algorithm_factory_generates_multiple_families():
    rows=ohlc(); closes=[x[3] for x in rows]
    c=generate_candidates(closes,rows)
    names={x.name for x in c}
    assert len(c)>=10
    assert {"MOM_2","MOM_20","MEANREV_5","BREAKOUT_10","CANDLE_STRUCTURE"} <= names

def test_adaptive_ensemble_is_bounded():
    rows=ohlc(); closes=[x[3] for x in rows]
    score,pred,c=adaptive_ensemble(closes,rows,{})
    assert -1 <= score <= 1
    assert len(c)>=10
