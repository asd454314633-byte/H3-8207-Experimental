# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "v28_dialogue_track.py"
spec = importlib.util.spec_from_file_location("v28_dialogue_track", MODULE)
DT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DT)


S02 = ("医生，我爸的手术费我凑齐了。差的八万我卖车了。车不重要。"
       "我爸开了一辈子出租车，我不能让他觉得那车比我值钱。"
       "钱我明天转过去。求您安排最快的手朮。哦对，是手术。")


def test_s02_is_lossless_and_time_budgeted():
    result = DT.split_dialogue(S02, [6, 6, 6, 6])
    assert [s["duration_s"] for s in result["segments"]] == [6, 6, 6, 6]
    assert "".join(s["dialogue"] for s in result["segments"]) == S02
    assert result["integrity"]["MISSING_CHAR"] == 0
    assert result["integrity"]["DUPLICATED_CHAR"] == 0
    assert result["integrity"]["REORDERED_TEXT"] == 0


def test_fallback_character_boundaries_remain_lossless():
    source = "没有句号但必须完整保留"
    result = DT.split_dialogue(source, [1, 1, 1])
    assert "".join(s["dialogue"] for s in result["segments"]) == source
    assert result["integrity"]["passed"] is True


def test_integrity_detects_missing_text():
    receipt = DT.validate_dialogue_track(S02, [S02.replace("天转", "")])
    assert receipt["passed"] is False
    assert receipt["MISSING_CHAR"] == 2
