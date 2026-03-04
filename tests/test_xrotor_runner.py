"""
tests/test_xrotor_runner.py
----------------------------
core/xrotor_runner.py のユニットテスト。
write_aero_file の出力形式と parse_xrotor_output の解析を検証する。
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.xrotor_runner import write_aero_file, parse_xrotor_output


# ─────────────────────────────────────────────
# write_aero_file のテスト
# ─────────────────────────────────────────────
def _sample_polar():
    """テスト用の簡易 polar データ（線形 CL-alpha）"""
    rows = []
    for alpha in range(-5, 16):
        cl = 0.1 * alpha + 0.3          # 単純な線形モデル
        cd = 0.01 + 0.001 * alpha**2    # 二次モデル
        rows.append({'alpha': float(alpha), 'CL': cl, 'CD': cd})
    return rows


def test_write_aero_file_creates_file():
    """ファイルが生成されること"""
    polar = _sample_polar()
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        path = tmp.name
    try:
        write_aero_file(path, r_R=0.5, polar_data=polar)
        assert os.path.exists(path), "aero ファイルが生成されていない"
    finally:
        os.remove(path)


def test_write_aero_file_encoding():
    """UTF-8 で書かれていること"""
    polar = _sample_polar()
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        path = tmp.name
    try:
        write_aero_file(path, r_R=0.3, polar_data=polar)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'r/R' in content
    finally:
        os.remove(path)


def test_write_aero_file_has_3_lines():
    """XROTOR Aero ファイルはヘッダ含め 4 行構成であること"""
    polar = _sample_polar()
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        path = tmp.name
    try:
        write_aero_file(path, r_R=0.7, polar_data=polar)
        with open(path, 'r', encoding='utf-8') as f:
            lines = [l for l in f.readlines() if l.strip()]
        # header + 3 data lines
        assert len(lines) == 4, f"行数が期待値(4)と異なる: {len(lines)}"
    finally:
        os.remove(path)


def test_write_aero_file_dcl_da_positive():
    """揚力傾斜 (dCl/dα) が正であること"""
    polar = _sample_polar()
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        path = tmp.name
    try:
        write_aero_file(path, r_R=0.5, polar_data=polar)
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # 2行目が "0.0  dcl_da  ..." の形式
        parts = lines[1].split()
        dcl_da = float(parts[1])
        assert dcl_da > 0, f"dcl_da が正でない: {dcl_da}"
    finally:
        os.remove(path)


def test_write_aero_file_no_polar_raises():
    """polar_data が空の場合は ValueError が発生すること"""
    try:
        write_aero_file("/tmp/test_empty.txt", r_R=0.5, polar_data=[])
        assert False, "ValueError が発生すべき"
    except ValueError:
        pass


# ─────────────────────────────────────────────
# parse_xrotor_output のテスト
# ─────────────────────────────────────────────
_XROTOR_SAMPLE = """\
 XROTOR   Version 7.55   (11 Nov 2011)

  ...design parameters...

      r/R      C/R       Beta0deg
!  -------  -------  -----------
  0.21000  0.05000   70.00000
  0.35000  0.07500   60.00000
  0.50000  0.09000   50.00000
  0.75000  0.08000   40.00000
  1.00000  0.06000   30.00000
"""


def test_parse_xrotor_output_reads_stations():
    """サンプル出力から正しく 5 ステーションを読み取れること"""
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False, mode='w', encoding='utf-8') as tmp:
        tmp.write(_XROTOR_SAMPLE)
        path = tmp.name
    try:
        data = parse_xrotor_output(path)
        assert data is not None, "戻り値が None"
        assert len(data) == 5, f"ステーション数が期待値(5)と異なる: {len(data)}"
    finally:
        os.remove(path)


def test_parse_xrotor_output_values():
    """パース値が正確であること"""
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False, mode='w', encoding='utf-8') as tmp:
        tmp.write(_XROTOR_SAMPLE)
        path = tmp.name
    try:
        data = parse_xrotor_output(path)
        assert abs(data[0]['r/R']  - 0.21) < 1e-5
        assert abs(data[0]['c/R']  - 0.05) < 1e-5
        assert abs(data[0]['beta'] - 70.0) < 1e-4
    finally:
        os.remove(path)


def test_parse_xrotor_output_missing_file():
    """ファイルが存在しない場合は None を返すこと"""
    result = parse_xrotor_output("/nonexistent/path/prop.txt")
    assert result is None


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
