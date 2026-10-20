"""Download the H&M competition CSVs into data/raw (skips files already there)."""
import zipfile

from kaggle.api.kaggle_api_extended import KaggleApi

from hmci.common.config import load_config


def main() -> None:
    cfg = load_config()
    cfg.paths.make_dirs()

    api = KaggleApi()
    api.authenticate()  # reads ~/.kaggle/kaggle.json

    competition = cfg.raw["kaggle"]["competition"]
    for name in cfg.raw["kaggle"]["files"]:
        target = cfg.paths.raw / name
        if target.exists():
            print(f"skip  {name} (already downloaded)")
            continue

        print(f"get   {name}")
        api.competition_download_file(competition, name, path=cfg.paths.raw, quiet=False)

        # large files arrive zipped as <name>.zip
        zipped = cfg.paths.raw / f"{name}.zip"
        if zipped.exists():
            with zipfile.ZipFile(zipped) as z:
                z.extractall(cfg.paths.raw)
            zipped.unlink()

    print("done")


if __name__ == "__main__":
    main()