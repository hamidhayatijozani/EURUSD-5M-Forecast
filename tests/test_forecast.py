from engine.forecast import forecast

def test_forecast_requires_history():
    try:
        forecast([1.0]*11)
        assert False
    except ValueError:
        pass

def test_flat_series_is_flat():
    f=forecast([1.0]*12)
    assert f.direction=="FLAT"
    assert f.regime=="RANGE"

def test_rising_series_is_up():
    f=forecast([1.1700,1.1702,1.1704,1.1706,1.1708,1.1710,1.1712,1.1714,1.1716,1.1718,1.1720,1.1722])
    assert f.direction=="UP"
