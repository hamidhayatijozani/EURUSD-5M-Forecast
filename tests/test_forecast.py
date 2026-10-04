from engine.forecast import forecast
import pytest

def test_requires_history():
    with pytest.raises(ValueError): forecast([1.0]*11)

def test_flat_is_flat_range():
    f=forecast([1.0]*12)
    assert f.direction=="FLAT"
    assert f.regime=="RANGE"

def test_rising_is_up():
    f=forecast([1.1700+i*0.0002 for i in range(12)])
    assert f.direction=="UP"
