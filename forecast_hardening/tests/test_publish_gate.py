import numpy as np
import pandas as pd
import pytest


def _df(n=30, **extra):
    d = pd.DataFrame({"fecha": pd.date_range("2026-09-01", periods=n), "x": np.arange(n, dtype=float)})
    for k, v in extra.items():
        d[k] = v
    return d


def test_stage_no_escribe_hasta_commit_y_publica_grupos_sanos(world, gate_factory):
    make, pg = gate_factory
    g = make("stage")
    import pandas_gbq
    pandas_gbq.to_gbq(_df(), "kpitos.colocacion_90", project_id="p", if_exists="replace")
    pandas_gbq.to_gbq(_df(), "kpitos.le_colocacion", project_id="p", if_exists="replace")
    assert world.writes == []                       # nada se escribe antes del commit
    g.commit_all()
    assert [w["table"] for w in world.writes] == ["kpitos.colocacion_90", "kpitos.le_colocacion"]


def test_grupo_incompleto_se_retiene_y_no_bloquea_a_los_demas(world, gate_factory):
    make, pg = gate_factory
    g = make("stage")
    import pandas_gbq
    pandas_gbq.to_gbq(_df(), "kpitos.colocacion_90", project_id="p", if_exists="replace")   # falta le_colocacion
    pandas_gbq.to_gbq(_df(), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")  # grupo sano
    with pytest.raises(pg.PublishError):
        g.commit_all()
    assert [w["table"] for w in world.writes] == ["kpitos.entrega_tarjetas"]
    st = {r["group"]: r["status"] for r in g.results}
    assert st["colocaciones"] == "HOLD" and st["tarjetas"] == "OK"


def test_dry_run_no_escribe_nada(world, gate_factory):
    make, pg = gate_factory
    g = make("dry_run")
    import pandas_gbq
    pandas_gbq.to_gbq(_df(), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    g.commit_all()
    assert world.writes == []
    assert g.results[0]["status"] == "OK(dry_run)"


def test_live_bloquea_tabla_vacia_y_duplicados_pero_deja_pasar_la_buena(world, gate_factory):
    make, pg = gate_factory
    g = make("live")
    import pandas_gbq
    pandas_gbq.to_gbq(_df(0), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    pandas_gbq.to_gbq(pd.concat([_df(5), _df(5)]), "kpitos.colocacion_90", project_id="p", if_exists="replace")
    pandas_gbq.to_gbq(_df(), "kpitos.le_colocacion", project_id="p", if_exists="replace")
    assert [w["table"] for w in world.writes] == ["kpitos.le_colocacion"]


def test_infinitos_y_todo_nan_bloquean(world, gate_factory):
    make, pg = gate_factory
    g = make("live")
    import pandas_gbq
    d = _df()
    d.loc[3, "x"] = np.inf
    pandas_gbq.to_gbq(d, "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    assert world.writes == []


def test_deriva_de_esquema_contra_bq_bloquea_y_alinea_tipos(world, gate_factory):
    make, pg = gate_factory
    g = make("stage")
    base = dict(schema={"fecha": "TEMPORAL", "x": "INT", "y": "STRING"}, rows=30)
    g.baseline = lambda table: base
    import pandas_gbq
    # x float "casualmente entero" -> se alinea a INT; y falta -> BLOQUEA
    pandas_gbq.to_gbq(_df(), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    with pytest.raises(pg.PublishError):
        g.commit_all()
    assert world.writes == []
    # con la columna presente: se publica y x queda Int64
    g2 = make("stage")
    g2.baseline = lambda table: base
    pandas_gbq.to_gbq(_df(y="a"), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    g2.commit_all()
    assert str(world.writes[-1]["df"]["x"].dtype) == "Int64"


def test_tipo_incompatible_string_vs_numero_bloquea(world, gate_factory):
    make, pg = gate_factory
    g = make("stage")
    g.baseline = lambda table: dict(schema={"fecha": "TEMPORAL", "x": "STRING"}, rows=30)
    import pandas_gbq
    pandas_gbq.to_gbq(_df(), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    with pytest.raises(pg.PublishError):
        g.commit_all()


def test_colapso_de_filas_bloquea_pero_monitoreo_truncate_no(world, gate_factory):
    make, pg = gate_factory
    g = make("stage")
    g.baseline = lambda table: dict(schema={"fecha": "TEMPORAL", "x": "FLOAT"}, rows=1000)
    import pandas_gbq
    pandas_gbq.to_gbq(_df(10), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    with pytest.raises(pg.PublishError):
        g.commit_all()


def test_duplicada_replace_gana_la_ultima(world, gate_factory):
    make, pg = gate_factory
    g = make("stage")
    import pandas_gbq
    pandas_gbq.to_gbq(_df(3), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    pandas_gbq.to_gbq(_df(7), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")
    g.commit_all()
    assert len(world.writes) == 1 and len(world.writes[0]["df"]) == 7


def test_dml_se_encola_en_orden_con_su_append(world, gate_factory):
    make, pg = gate_factory
    g = make("stage")
    from google.cloud import bigquery
    c = bigquery.Client()
    c.query("DELETE FROM `tenpo-bi-prod.kpitos.captaciones_monitoreo_le` WHERE fecha_ejecucion = '2026-09-15'").result()
    cfg = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_APPEND)
    c.load_table_from_dataframe(_df(), "tenpo-bi-prod.kpitos.captaciones_monitoreo_le", job_config=cfg).result()
    for t in ("forecasting_le_captacion", "forecasting_le_captacion_90d"):
        c.load_table_from_dataframe(_df(), f"tenpo-bi-prod.kpitos.{t}").result()
    assert world.writes == []
    g.commit_all()
    order = [(w["via"], w["table"].split(".")[-1]) for w in world.writes]
    assert order[0][0] == "client.query" and order[1] == ("load_job", "captaciones_monitoreo_le")


def test_cross_check_identidad_gpv_productos_vs_app():
    import forecast_hardening.publish_gate as pg
    g = pg.PublishGate("dry_run", log=lambda *a, **k: None)
    f = pd.date_range("2026-09-01", periods=4).strftime("%Y-%m-%d")
    app = pd.DataFrame({"fecha": f, "gpv": [1e9, 1e9, np.nan, np.nan], "gpv_real_pred": [1e9, 1e9, 5e9, 6e9]})
    prod = pd.DataFrame({"fecha": f, "gpv_real_pred_a": [500, 500, 2500, 3000], "gpv_real_pred_b": [500, 500, 2500, 3000]})
    assert not [i for i in g.cross_checks({"forecasting_gpv_app": app, "forecasting_gpv_productos": prod}) if i["level"] == "BLOCK"]
    prod["gpv_real_pred_b"] = [500, 500, 100, 100]        # días futuros ya no cuadran
    bad = g.cross_checks({"forecasting_gpv_app": app, "forecasting_gpv_productos": prod})
    assert any(i["level"] == "BLOCK" and "productos" in i["msg"] for i in bad)


def test_cross_check_meses_distintos_bloquea():
    import forecast_hardening.publish_gate as pg
    g = pg.PublishGate("dry_run", log=lambda *a, **k: None)
    a = pd.DataFrame({"fecha": pd.date_range("2026-09-01", periods=3), "gpv": [1.0] * 3, "gpv_real_pred": [1.0] * 3})
    b = pd.DataFrame({"fecha": pd.date_range("2026-10-01", periods=3), "ob_large": [1.0] * 3})
    out = g.cross_checks({"forecasting_gpv_app": a, "forecasting_ob_tc": b})
    assert any(i["level"] == "BLOCK" for i in out)


def test_cross_check_mau_vs_subcategorias():
    import forecast_hardening.publish_gate as pg
    g = pg.PublishGate("dry_run", log=lambda *a, **k: None)
    c = pd.DataFrame({"fecha": pd.date_range("2026-09-01", periods=3), "mau_real_pred_app": [100.0] * 3,
                      "mau_real_pred_concurrent": [50.0] * 3, "mau_real_pred_m0": [20.0] * 3,
                      "mau_real_pred_resurrected": [10.0] * 3, "mau_real_pred_late_active": [20.0] * 3})
    assert not any(i["level"] != "INFO" for i in g.cross_checks({"forecasting_categorias": c}))
    c["mau_real_pred_m0"] = 5.0
    assert any(i["level"] == "BLOCK" for i in g.cross_checks({"forecasting_categorias": c}))


def test_compare_with_bq_detecta_cambios_de_valor_y_de_filas(world, gate_factory):
    make, pg = gate_factory
    g = make("dry_run")
    import pandas_gbq
    base = _df(5, y="a")
    world.baseline["entrega_tarjetas"] = base.copy()
    world.baseline["colocacion_90"] = base.copy()
    world.baseline["le_colocacion"] = base.copy()
    pandas_gbq.to_gbq(base.copy(), "kpitos.entrega_tarjetas", project_id="p", if_exists="replace")      # igual
    cambiado = base.copy(); cambiado.loc[2, "x"] += 1.0
    pandas_gbq.to_gbq(cambiado, "kpitos.colocacion_90", project_id="p", if_exists="replace")            # valor distinto
    pandas_gbq.to_gbq(_df(6, y="a"), "kpitos.le_colocacion", project_id="p", if_exists="replace")       # filas distintas
    g.commit_all()
    # el stub responde 'SELECT * FROM `tabla`' con world.baseline
    res = g.compare_with_bq().set_index("tabla")["estado"].to_dict()
    assert res == {"colocacion_90": "DIFIERE", "entrega_tarjetas": "IGUAL", "le_colocacion": "DIFIERE"}
