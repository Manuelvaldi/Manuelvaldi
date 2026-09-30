import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def world():
    """Instala stubs de pandas_gbq/bigquery/colab y devuelve el 'mundo' que captura las escrituras."""
    from forecast_hardening.dryrun import stubs
    w = stubs.install(pd.Timestamp("2026-09-15 10:00", tz="America/Santiago"))
    return w


@pytest.fixture()
def gate_factory(world):
    import importlib
    import forecast_hardening.publish_gate as pg
    importlib.reload(pg)
    made = []

    def make(mode="stage", **kw):
        g = pg.PublishGate(mode=mode, today="2026-09-15", log=lambda *a, **k: None, **kw).install()
        made.append(g)
        return g

    yield make, pg
    for g in made:
        g.uninstall()
