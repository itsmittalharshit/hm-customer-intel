from datetime import date, timedelta

from hmci.churn.snapshots import assign_splits


def test_splits_are_purged():
    step, horizon = 4, 18
    dates = [date(2019, 3, 21) + timedelta(weeks=step * i) for i in range(16)]
    splits = assign_splits(dates, horizon, step)

    by = {name: [d for d, s in splits.items() if s == name] for name in ("train", "val", "test")}
    h = timedelta(weeks=horizon)

    assert len(by["test"]) == 1 and len(by["val"]) == 1 and len(by["train"]) > 0
    assert max(by["train"]) + h <= min(by["val"])   # train labels end before val starts
    assert max(by["val"]) + h <= min(by["test"])    # val labels end before test starts