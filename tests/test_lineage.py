"""Repositorios temporales, sin red y sin modificar el repo del proyecto."""
import json

import pytest
from git import Repo

from autoguard.config_schema import CotizadorConfig
from autoguard.rsi.lineage import ConfigRepo


def test_commit_revert_exact_and_history(tmp_path):
    lineage = ConfigRepo(tmp_path / "run")
    cfg = CotizadorConfig(base=9000, factores={}, prompt_estrategia="SIMULADO: hipótesis á")
    initial = lineage.init(cfg)
    initial_bytes = (lineage.path / "config.yaml").read_bytes()
    message = json.dumps(dict(patch_id="p1", tipo="ajuste_factor", hipotesis="sesgo",
                              metrics={"loss": 0.12}))
    changed = lineage.commit(cfg.model_copy(update={"base": 8000}), message)
    assert lineage.current()[0].base == 8000
    assert Repo(lineage.path).commit(changed).message.strip() == message
    restored = lineage.revert_to(initial, "p1 retirado")
    assert restored not in (initial, changed)
    assert (lineage.path / "config.yaml").read_bytes() == initial_bytes
    assert lineage.current() == (cfg, restored)
    history = ConfigRepo(lineage.path).history()
    assert [v.git_sha for v in history] == [restored, changed, initial]
    assert [v.estado for v in history] == ["campeon", "retirado", "retirado"]
    assert history[0].parent_id == history[1].id
    assert history[1].metrics == {"loss": 0.12}
    assert history[-1].parent_id is None


def test_refuses_project_repo_or_existing_files(tmp_path):
    Repo.init(tmp_path)
    lineage = ConfigRepo(tmp_path)
    with pytest.raises(ValueError):
        lineage.init(CotizadorConfig(base=1, factores={}))
    with pytest.raises(FileNotFoundError):
        lineage.commit(CotizadorConfig(base=1, factores={}), "patch")


def test_dirty_repo_and_bad_revision_preserve_head(tmp_path):
    lineage = ConfigRepo(tmp_path / "run")
    cfg = CotizadorConfig(base=1, factores={})
    head = lineage.init(cfg)
    with pytest.raises(Exception):
        lineage.revert_to("missing-revision")
    (lineage.path / "unrelated").write_text("do not commit")
    with pytest.raises(ValueError):
        lineage.commit(cfg, "patch")
    with pytest.raises(ValueError):
        lineage.revert_to(head)
    assert lineage.current()[1] == head
    assert len(lineage.history()) == 1


def test_no_change_patch_still_records_version(tmp_path):
    lineage = ConfigRepo(tmp_path / "run")
    cfg = CotizadorConfig(base=1, factores={})
    first = lineage.init(cfg)
    second = lineage.commit(cfg, "patch_id=p2 tipo=cambio_prompt hipotesis=control metrics={}")
    assert first != second
    assert len(lineage.history()) == 2
