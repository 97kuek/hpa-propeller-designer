import yaml
import logging

# config.yaml に必須のキーとサブキーの定義
_REQUIRED_KEYS = {
    'propeller': ['B', 'R', 'Rhub'],
    'design_point': ['V', 'RPM', 'target', 'value', 'CL'],
    'environment': ['rho', 'visc'],
    'analysis': ['n_stations', 'ncrit', 'iter'],
    'airfoils': None,  # list チェックは別途行う
}

def validate_config(config: dict) -> list[str]:
    """
    config 辞書の必須キーを検証し、不足・不正な項目のエラーメッセージリストを返す。
    エラーがなければ空リストを返す。
    """
    errors = []

    for section, keys in _REQUIRED_KEYS.items():
        if section not in config:
            errors.append(f"必須セクション '{section}' が見つかりません。")
            continue

        if keys is None:
            # list 型チェック（airfoils）
            if not isinstance(config[section], list) or len(config[section]) == 0:
                errors.append(f"'{section}' は1件以上のリストである必要があります。")
            else:
                for i, entry in enumerate(config[section]):
                    if 'r_R' not in entry or 'file' not in entry:
                        errors.append(f"airfoils[{i}] に 'r_R' または 'file' キーがありません。")
            continue

        for key in keys:
            if key not in config[section]:
                errors.append(f"'{section}.{key}' が見つかりません。")

    # 数値範囲チェック（簡易）
    if 'propeller' in config:
        p = config['propeller']
        R    = p.get('R', None)
        Rhub = p.get('Rhub', None)
        if R is not None and Rhub is not None and Rhub >= R:
            errors.append(f"Rhub ({Rhub}) は R ({R}) より小さい必要があります。")

        # No.9: propeller.name に使用不可文字が含まれていないかチェック
        name = p.get('name', '')
        invalid_chars = set(r'\/:*?"<>|')
        bad = [c for c in str(name) if c in invalid_chars]
        if bad:
            errors.append(
                f"propeller.name '{name}' に使用できない文字が含まれています: {bad}\n"
                "  (パス禁止文字 \\ / : * ? \" < > | は使えません)"
            )

    if 'design_point' in config:
        d = config['design_point']
        if d.get('V', 0) <= 0:
            errors.append("design_point.V は正の値である必要があります。")
        if d.get('RPM', 0) <= 0:
            errors.append("design_point.RPM は正の値である必要があります。")
        if d.get('target') not in ('power', 'thrust', None):
            errors.append("design_point.target は 'power' または 'thrust' である必要があります。")

    return errors

def load_config(filepath):
    """YAML設定ファイルを読み込み、バリデーションを行って辞書を返す。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logging.info(f"Loaded configuration from {filepath}")
    except Exception as e:
        logging.error(f"Failed to load config file '{filepath}': {e}")
        return None

    errors = validate_config(config)
    if errors:
        logging.error("config.yaml にエラーがあります:")
        for err in errors:
            logging.error(f"  - {err}")
        return None

    return config
