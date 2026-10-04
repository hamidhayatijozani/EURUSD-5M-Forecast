from engine.consensus import aggregate

def test_consensus():
    c=aggregate(["UP","UP","DOWN","FLAT"])
    assert c.bullish == .5 and c.bearish == .25 and c.neutral == .25
