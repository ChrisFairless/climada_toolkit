from pathlib import Path

import numpy as np
import pytest

from climada.hazard import Hazard
from climada_toolkit.inputs.hazard.aqueduct_river import (
    AQUEDUCT_FUTURE_GCMS,
    build_aqueduct_river_filename,
    create_aqueduct_river_hazard,
    validate_aqueduct_parameters,
)


def _frequencies(monkeypatch, scenario, year, return_periods):
    """Run hazard creation with cached files and raster reading mocked out."""
    captured = {}
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Hazard, "from_raster", lambda **kwargs: captured.update(kwargs))
    create_aqueduct_river_hazard(
        ".", scenario, year, return_periods=return_periods,
        bounding_box=(0, 0, 1, 1),
    )
    return captured["attrs"]


def test_return_periods_returned_ascending():
    _, _, _, rps, _, _ = validate_aqueduct_parameters(
        "historical", 1980, return_periods=[100, 10, 50, 25], country="gmb"
    )
    assert rps == [10, 25, 50, 100]


def test_repeated_return_periods_rejected():
    with pytest.raises(ValueError):
        validate_aqueduct_parameters(
            "historical", 1980, return_periods=[10, 10, 50], country="GMB"
        )


@pytest.mark.parametrize("bad", [["10", "50"], [10.5, 50], "100"])
def test_text_or_non_integer_return_periods_rejected(bad):
    with pytest.raises(ValueError):
        validate_aqueduct_parameters(
            "historical", 1980, return_periods=bad, country="GMB"
        )


def test_event_frequencies_historical(monkeypatch):
    attrs = _frequencies(monkeypatch, "historical", 1980, [100, 10, 50, 25])
    assert attrs["event_name"] == [f"rp{rp}_WATCH_historical_1980" for rp in (10, 25, 50, 100)]
    np.testing.assert_allclose(attrs["frequency"], [6 / 100, 2 / 100, 1 / 100, 1 / 100])
    assert sum(attrs["frequency"]) == pytest.approx(1 / 10)


def test_event_frequencies_future_five_gcms(monkeypatch):
    attrs = _frequencies(monkeypatch, "rcp8p5", 2050, [10, 25, 50, 100])
    freq = np.array(attrs["frequency"]).reshape(4, 5)  # rows: RP ascending, columns: GCM
    np.testing.assert_allclose(freq[:, 0], [6 / 500, 2 / 500, 1 / 500, 1 / 500])
    assert freq.sum() == pytest.approx(1 / 10)


@pytest.mark.parametrize(
    "scenario, year",
    [
        ("historical", 2030),
        ("rcp8p5", 1980),
        ("rcp4p5", 2040),
        ("ssp585", 2050),
        ("rcp8p5", "2050"),
        ("rcp8p5", 2050.0),
    ],
)
def test_invalid_scenario_year_rejected(scenario, year):
    with pytest.raises(ValueError):
        validate_aqueduct_parameters(scenario, year, country="GMB")


@pytest.mark.parametrize("empty", [None, []])
def test_empty_gcms_expand_to_all(empty):
    _, _, historical, _, _, _ = validate_aqueduct_parameters(
        "historical", 1980, gcms=empty, country="GMB"
    )
    _, _, future, _, _, _ = validate_aqueduct_parameters(
        "rcp8p5", 2050, gcms=empty, country="GMB"
    )
    assert historical == ["WATCH"]
    assert future == AQUEDUCT_FUTURE_GCMS


@pytest.mark.parametrize(
    "scenario, year, gcms",
    [
        ("historical", 1980, ["NorESM1-M"]),
        ("rcp8p5", 2050, ["WATCH"]),
        ("rcp8p5", 2050, ["NorESM1-M", "NorESM1-M"]),
    ],
)
def test_invalid_gcms_rejected(scenario, year, gcms):
    with pytest.raises(ValueError):
        validate_aqueduct_parameters(scenario, year, gcms=gcms, country="GMB")


def test_build_filename():
    assert (
        build_aqueduct_river_filename("rcp8p5", 2050, "NorESM1-M", 10)
        == "inunriver_rcp8p5_00000NorESM1-M_2050_rp00010.tif"
    )
