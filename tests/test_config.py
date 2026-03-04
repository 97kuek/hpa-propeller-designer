"""
tests/test_config.py
---------------------
utils/config.py (validate_config / load_config) のユニットテスト。
"""
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.config import validate_config


# ─────────────────────────────────────────────
# ヘルパー: 最小限の正常 config を返す
# ─────────────────────────────────────────────
def _valid_config():
    return {
        'propeller': {'B': 2, 'R': 1.5, 'Rhub': 0.1, 'name': 'test_prop'},
        'design_point': {'V': 7.4, 'RPM': 135, 'target': 'thrust', 'value': 24, 'CL': 0.5},
        'environment': {'rho': 1.225, 'visc': 1.46e-5},
        'analysis': {'n_stations': 5, 'ncrit': 9.0, 'iter': 100},
        'airfoils': [{'r_R': 0.1, 'file': 'airfoils/GEMINI.dat'},
                     {'r_R': 1.0, 'file': 'airfoils/DAE51.dat'}],
    }


# ─────────────────────────────────────────────
# 正常ケース
# ─────────────────────────────────────────────
def test_valid_config_returns_no_errors():
    errors = validate_config(_valid_config())
    assert errors == [], f"予期しないエラー: {errors}"


# ─────────────────────────────────────────────
# 必須セクション欠落
# ─────────────────────────────────────────────
def test_missing_propeller_section():
    cfg = _valid_config()
    del cfg['propeller']
    errors = validate_config(cfg)
    assert any('propeller' in e for e in errors), "propeller セクション欠落を検出すべき"


def test_missing_analysis_section():
    cfg = _valid_config()
    del cfg['analysis']
    errors = validate_config(cfg)
    assert any('analysis' in e for e in errors)


# ─────────────────────────────────────────────
# 必須キー欠落
# ─────────────────────────────────────────────
def test_missing_key_in_section():
    cfg = _valid_config()
    del cfg['design_point']['V']
    errors = validate_config(cfg)
    assert any('design_point.V' in e for e in errors)


# ─────────────────────────────────────────────
# 数値範囲
# ─────────────────────────────────────────────
def test_rhub_ge_r_is_error():
    cfg = _valid_config()
    cfg['propeller']['Rhub'] = 2.0  # R=1.5 より大
    errors = validate_config(cfg)
    assert any('Rhub' in e for e in errors)


def test_negative_velocity_is_error():
    cfg = _valid_config()
    cfg['design_point']['V'] = -1.0
    errors = validate_config(cfg)
    assert any('V' in e for e in errors)


# ─────────────────────────────────────────────
# propeller.name の禁止文字チェック
# ─────────────────────────────────────────────
def test_invalid_name_characters():
    cfg = _valid_config()
    cfg['propeller']['name'] = 'bad/name:test'
    errors = validate_config(cfg)
    assert any('name' in e for e in errors), "禁止文字を含む name を検出すべき"


def test_valid_name_with_underscore():
    cfg = _valid_config()
    cfg['propeller']['name'] = 'my_prop_v2'
    errors = validate_config(cfg)
    assert errors == []


# ─────────────────────────────────────────────
# airfoils リストの検証
# ─────────────────────────────────────────────
def test_empty_airfoils_list():
    cfg = _valid_config()
    cfg['airfoils'] = []
    errors = validate_config(cfg)
    assert any('airfoils' in e for e in errors)


def test_airfoils_missing_file_key():
    cfg = _valid_config()
    cfg['airfoils'] = [{'r_R': 0.1}]  # 'file' キー欠落
    errors = validate_config(cfg)
    assert any('file' in e for e in errors)


if __name__ == "__main__":
    # pytest なしでも実行できるシンプルランナー
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
