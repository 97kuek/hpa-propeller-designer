"""
tests/test_analysis.py
-----------------------
core/analysis.py のユニットテスト。
parse_performance_output_from_stdout を模擬 XROTOR 出力でテストする。
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.analysis import parse_performance_output_from_stdout


# ─────────────────────────────────────────────
# 模擬 XROTOR stdout テンプレート
# ─────────────────────────────────────────────
def _make_block(j, ct, cp, eff):
    """1 ADVA 点分の評価ブロックを生成する"""
    return (
        f"Free Tip Potential Formulation Solution\n\n"
        f"   J:  {j:.4f}    RPM: 135.00\n"
        f"   Ct: {ct:.5f}    Cp: {cp:.5f}\n"
        f"   Efficiency :  {eff:.5f}\n\n"
    )


def _make_stdout(points):
    """[(j, ct, cp, eff), ...] からフル stdout を生成"""
    return "".join(_make_block(*p) for p in points)


# ─────────────────────────────────────────────
# 正常ケース
# ─────────────────────────────────────────────
def test_parse_single_point():
    """1点の解析が正しく動作すること"""
    points = [(0.4, 0.08, 0.04, 0.80)]
    stdout = _make_stdout(points)
    data = parse_performance_output_from_stdout(stdout)
    assert len(data) == 1
    assert abs(data[0]['J'] - 0.4) < 1e-3


def test_parse_multiple_points():
    """複数点の解析で J, Ct, Efficiency が正しく返ること"""
    pts = [(0.3, 0.10, 0.05, 0.60), (0.4, 0.08, 0.04, 0.80), (0.5, 0.05, 0.03, 0.83)]
    data = parse_performance_output_from_stdout(_make_stdout(pts))
    assert len(data) == 3
    assert abs(data[1]['J'] - 0.4) < 1e-3
    assert abs(data[1]['Efficiency'] - 0.80) < 1e-3


def test_efficiency_clamped_to_zero():
    """効率が [0, 1] 範囲外の場合は 0.0 に補正されること"""
    pts = [(0.4, 0.08, 0.04, 99.9)]   # 異常値
    data = parse_performance_output_from_stdout(_make_stdout(pts))
    assert len(data) == 1
    assert data[0]['Efficiency'] == 0.0


def test_negative_efficiency_clamped():
    """負の効率は 0.0 に補正されること"""
    pts = [(0.4, 0.08, 0.04, -0.5)]
    data = parse_performance_output_from_stdout(_make_stdout(pts))
    assert data[0]['Efficiency'] == 0.0


def test_empty_stdout():
    """空の stdout は空リストを返すこと"""
    data = parse_performance_output_from_stdout("")
    assert data == []


def test_expected_j_values_interpolation():
    """expected_j_values を渡すと NaN 補間が行われること"""
    import numpy as np
    pts = [(0.3, 0.10, 0.05, 0.60), (0.5, 0.05, 0.03, 0.83)]
    stdout = _make_stdout(pts)
    # J=0.4 の点は存在しないので補間されるはず
    expected = np.array([0.3, 0.4, 0.5])
    data = parse_performance_output_from_stdout(stdout, expected_j_values=expected)
    assert len(data) == 3
    # J=0.4 の効率は 0.6 と 0.83 の中間付近のはず
    eff_04 = data[1]['Efficiency']
    assert 0.6 < eff_04 < 0.83, f"補間値が範囲外: {eff_04}"


def test_abnormal_ct_filtered():
    """|Ct| > 10 の発散点はフィルタされること"""
    pts = [(0.4, 999.9, 0.04, 0.5)]   # 発散した Ct
    data = parse_performance_output_from_stdout(_make_stdout(pts))
    assert len(data) == 0


if __name__ == "__main__":
    tests = [fn for name, fn in list(globals().items()) if name.startswith('test_')]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed.")
