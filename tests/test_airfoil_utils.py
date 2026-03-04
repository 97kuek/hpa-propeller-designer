"""
tests/test_airfoil_utils.py
----------------------------
core/airfoil_utils.py のユニットテスト。
normalize_airfoil / blend_airfoils の動作確認。
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.airfoil_utils import normalize_airfoil, blend_airfoils


# ─────────────────────────────────────────────
# テスト用: 簡単なひし形翼型 (1×0.1 の薄板上下面)
# ─────────────────────────────────────────────
def _diamond_airfoil(t=0.1, n=50):
    """菱形翼型座標（前縁→上面後縁→後縁→下面→前縁）"""
    x = np.linspace(0, 1, n)
    y_upper = t * (1 - np.abs(2*x - 1))  # 三角形状の上面
    y_lower = -y_upper
    upper = np.column_stack([x[::-1], y_upper[::-1]])  # TE→LE
    lower = np.column_stack([x[1:],   y_lower[1:]])    # LE→TE
    return np.vstack([upper, lower])


# ─────────────────────────────────────────────
# normalize_airfoil のテスト
# ─────────────────────────────────────────────
def test_normalize_output_shape():
    coords = _diamond_airfoil()
    out = normalize_airfoil(coords, n_points=80)
    assert out.shape == (2 * 80 - 1, 2), f"shape={out.shape}"


def test_normalize_x_range():
    """正規化後の x は [0, 1] に収まるはず"""
    coords = _diamond_airfoil()
    out = normalize_airfoil(coords)
    assert out[:, 0].min() >= -1e-9,  "x が負になっている"
    assert out[:, 0].max() <= 1 + 1e-9, "x が 1 を超えている"


def test_normalize_has_leading_edge():
    """正規化後に x ≈ 0 の点（前縁）が存在するはず"""
    coords = _diamond_airfoil()
    out = normalize_airfoil(coords)
    assert np.any(out[:, 0] < 0.01), "前縁点 (x≈0) が見つからない"


def test_normalize_has_trailing_edge():
    """正規化後に x ≈ 1 の点（後縁）が2点以上存在するはず"""
    coords = _diamond_airfoil()
    out = normalize_airfoil(coords)
    te_pts = out[out[:, 0] > 0.99]
    assert len(te_pts) >= 2, f"後縁点が {len(te_pts)} 点しかない"


# ─────────────────────────────────────────────
# blend_airfoils のテスト
# ─────────────────────────────────────────────
def test_blend_weight_zero_returns_first():
    """weight=0 → 第1翼型のみが返る"""
    c1 = normalize_airfoil(_diamond_airfoil(t=0.10))
    c2 = normalize_airfoil(_diamond_airfoil(t=0.20))
    blended = blend_airfoils(c1, c2, weight=0.0)
    assert np.allclose(blended, c1)


def test_blend_weight_one_returns_second():
    """weight=1 → 第2翼型のみが返る"""
    c1 = normalize_airfoil(_diamond_airfoil(t=0.10))
    c2 = normalize_airfoil(_diamond_airfoil(t=0.20))
    blended = blend_airfoils(c1, c2, weight=1.0)
    assert np.allclose(blended, c2)


def test_blend_weight_half_is_midpoint():
    """weight=0.5 → 中間の翼型"""
    c1 = normalize_airfoil(_diamond_airfoil(t=0.10))
    c2 = normalize_airfoil(_diamond_airfoil(t=0.20))
    blended = blend_airfoils(c1, c2, weight=0.5)
    expected = 0.5 * c1 + 0.5 * c2
    assert np.allclose(blended, expected)


def test_blend_shape_mismatch_raises():
    """形状が異なる座標でエラーを返すか"""
    c1 = np.zeros((100, 2))
    c2 = np.zeros((90, 2))
    try:
        blend_airfoils(c1, c2, weight=0.5)
        assert False, "ValueError が発生すべき"
    except ValueError:
        pass


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
