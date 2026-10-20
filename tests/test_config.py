from hmci.common.config import ROOT, load_config


def test_config_loads():
    cfg = load_config()
    assert cfg.seed == 42
    assert cfg.paths.raw == ROOT / "data" / "raw"


def test_paths_are_absolute():
    cfg = load_config()
    for p in vars(cfg.paths).values():
        assert p.is_absolute()