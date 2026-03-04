"""
tests/test_structure.py
-----------------------
core/structure.py の calculate_section_properties ユニットテスト。
既知の形状（正方形・矩形）の断面積と慣性モーメントを解析値と比較する。
"""
import sys
import os
import math
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.structure import calculate_section_properties


def _rect_coords(w, h):
    """幅 w・高さ h の矩形座標（反時計回り、コード長 1.0 の無次元）"""
    return np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=float)


# ─────────────────────────────────────────────
# 単位正方形 (chord=1.0 → 物理スケール 1 m)
# ─────────────────────────────────────────────
def test_unit_square_area():
    coords = _rect_coords(1.0, 1.0)
    area, _, _, _, _ = calculate_section_properties(coords, chord=1.0)
    assert abs(area - 1.0) < 1e-10, f"area={area}"


def test_unit_square_centroid():
    coords = _rect_coords(1.0, 1.0)
    _, xc, yc, _, _ = calculate_section_properties(coords, chord=1.0)
    assert abs(xc - 0.5) < 1e-10, f"xc={xc}"
    assert abs(yc - 0.5) < 1e-10, f"yc={yc}"


def test_unit_square_Ixx():
    """単位正方形の Ixx = 1/12 ≈ 0.0833"""
    coords = _rect_coords(1.0, 1.0)
    _, _, _, Ixx, _ = calculate_section_properties(coords, chord=1.0)
    assert abs(Ixx - 1.0 / 12.0) < 1e-8, f"Ixx={Ixx}"


def test_unit_square_Iyy():
    """単位正方形の Iyy = 1/12 ≈ 0.0833"""
    coords = _rect_coords(1.0, 1.0)
    _, _, _, _, Iyy = calculate_section_properties(coords, chord=1.0)
    assert abs(Iyy - 1.0 / 12.0) < 1e-8, f"Iyy={Iyy}"


# ─────────────────────────────────────────────
# chord スケーリングの確認（chord=2.0）
# ─────────────────────────────────────────────
def test_chord_scaling_area():
    """chord=2 → 物理断面積 = 無次元 * chord^2"""
    coords = _rect_coords(1.0, 1.0)
    area, _, _, _, _ = calculate_section_properties(coords, chord=2.0)
    # 無次元正方形 1×1, chord=2 → 物理 2×2 → 面積=4
    assert abs(area - 4.0) < 1e-8, f"area={area}"


# ─────────────────────────────────────────────
# 矩形の Ixx = b*h^3/12 (重心まわり)
# ─────────────────────────────────────────────
def test_rectangle_Ixx():
    """幅 w=1, 高さ h=0.1 の矩形。Ixx_centroid = w*h^3/12"""
    w, h, chord = 1.0, 0.1, 1.0
    coords = _rect_coords(w, h)
    _, _, _, Ixx, _ = calculate_section_properties(coords, chord=chord)
    expected = w * h**3 / 12.0
    assert abs(Ixx - expected) < 1e-10, f"Ixx={Ixx}, expected={expected}"


# ─────────────────────────────────────────────
# 単純実行
# ─────────────────────────────────────────────
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
