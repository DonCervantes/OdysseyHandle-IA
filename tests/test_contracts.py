import pytest

from autoguard.config_schema import apply_changes, load_config
from autoguard.contracts import ConfigChange
from autoguard.evaluator.objective import ALPHA, BETA, loss


def test_base_config_loads():
    cfg = load_config("configs/agents/cotizador.yaml")
    assert cfg.base > 0 and "uso" in cfg.factores


def test_apply_changes_and_whitelist():
    cfg = load_config("configs/agents/cotizador.yaml")
    new = apply_changes(cfg, [ConfigChange(op="set", path="factores.uso.categorias.app_transporte", value=1.3)])
    assert new.factores["uso"].categorias["app_transporte"] == 1.3
    new = apply_changes(cfg, [ConfigChange(op="add_rule", value={"id": "r1", "segmento": {"anio_max": 1996}, "multiplicador": 0.9})])
    assert new.reglas[0].id == "r1"
    with pytest.raises(Exception):
        apply_changes(cfg, [ConfigChange(op="add_rule", value={"id": "r2", "segmento": {"genero": "f"}, "multiplicador": 0.9})])


def test_loss_asymmetric():
    assert ALPHA > BETA
    assert loss(100, 110) == pytest.approx(15.0)
    assert loss(110, 100) == pytest.approx(10.0)
