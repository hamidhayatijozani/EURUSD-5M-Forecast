from engine.experiments import pst_signal,cross_asset_signal,combined,resolve
def series(base,step=0.0002,n=30): return [base+i*step for i in range(n)]
def test_pst_direction(): assert pst_signal(series(1.1)).direction=="UP"
def test_cross_asset_alignment():
    assert cross_asset_signal({"EURUSD":series(1.1),"GBPUSD":series(1.2),"USDJPY":series(150,-0.02),"DXY":series(100,-0.02)}).direction=="UP"
def test_combination_exists():
    assert combined({"EURUSD":series(1.1),"GBPUSD":series(1.2),"USDJPY":series(150,-0.02),"DXY":series(100,-0.02)}).name=="COMBINATION"
def test_resolve_pays_friction(): assert resolve(pst_signal(series(1.1)),1.1,1.1005)>0
