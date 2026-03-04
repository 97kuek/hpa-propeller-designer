import os
import numpy as np
from scipy.interpolate import interp1d

def load_airfoil(filepath):
    """
    XFOIL形式の翼型.datファイルを読み込み、numpy配列として返す。
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Airfoil file not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    name = lines[0].strip()
    data = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2:
            try:
                x = float(parts[0])
                y = float(parts[1])
                data.append([x, y])
            except ValueError:
                continue

    return name, np.array(data)

def normalize_airfoil(coords, n_points=100):
    """
    翼型座標を正規化（Cosスペーシングで点群を整える）。
    上下面それぞれを補間して再サンプリングする。

    前縁点は「弧長に基づく曲率最大点」で検出するため、座標が完全に
    ソートされていない翼型でも安定して動作する。
    """
    coords = np.asarray(coords, dtype=float)

    # ──────────────────────────────────────────
    # Step 1: 前縁点を弧長ベースで検出
    # ──────────────────────────────────────────
    # 各点の弧長パラメータを計算
    diffs = np.diff(coords, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg_lengths)])

    # x が最小の点のインデックスを候補とする（従来と同じだが、一意性を保証）
    # x 最小点から最も近い "弧長的な中間点" を前縁として採用
    x_min_idx = np.argmin(coords[:, 0])

    # 前縁候補: x が前縁近傍 (x_min * 1.05 以下) である点のうち、
    # 弧長的に最も "中央" に近い点を前縁とする
    x_min_val = coords[x_min_idx, 0]
    candidate_mask = coords[:, 0] <= x_min_val * 1.05 + 1e-6
    candidate_idxs = np.where(candidate_mask)[0]

    # 候補が1点だけの場合はそのまま採用
    if len(candidate_idxs) == 1:
        le_idx = candidate_idxs[0]
    else:
        # 弧長の中央値に最も近い候補を前縁とする
        arc_mid = arc[-1] * 0.5
        le_idx = candidate_idxs[np.argmin(np.abs(arc[candidate_idxs] - arc_mid))]

    # ──────────────────────────────────────────
    # Step 2: 上面・下面に分割して補間
    # ──────────────────────────────────────────
    # 上面: 後縁から前縁まで（配列の前半），下面: 前縁から後縁まで（配列の後半）
    upper_coords = coords[:le_idx + 1]
    lower_coords = coords[le_idx:]

    # x 昇順にソート（補間のため）
    upper_coords = upper_coords[np.argsort(upper_coords[:, 0])]
    lower_coords = lower_coords[np.argsort(lower_coords[:, 0])]

    # 重複x座標があると interp1d がエラーになるため除去
    _, u_unique = np.unique(upper_coords[:, 0], return_index=True)
    _, l_unique = np.unique(lower_coords[:, 0], return_index=True)
    upper_coords = upper_coords[u_unique]
    lower_coords = lower_coords[l_unique]

    # Cos スペーシングによる共通 x グリッド
    beta  = np.linspace(0, np.pi, n_points)
    x_new = 0.5 * (1 - np.cos(beta))

    # 上面・下面を補間（端点外挿あり）
    upper_interp = interp1d(upper_coords[:, 0], upper_coords[:, 1],
                            kind='linear', fill_value="extrapolate")
    lower_interp = interp1d(lower_coords[:, 0], lower_coords[:, 1],
                            kind='linear', fill_value="extrapolate")

    y_upper = upper_interp(x_new)
    y_lower = lower_interp(x_new)

    # XFOIL形式 (TE上面 -> LE -> TE下面) に再構成
    new_upper = np.column_stack((x_new[::-1], y_upper[::-1]))
    new_lower = np.column_stack((x_new[1:],   y_lower[1:]))

    return np.vstack((new_upper, new_lower))

def blend_airfoils(coords1, coords2, weight):
    """
    2つの正規化された翼型座標を線形補間（ブレンド）する。
    weight: 0.0でcoords1のみ、1.0でcoords2のみ。
    """
    if coords1.shape != coords2.shape:
        raise ValueError("Airfoil coordinates shapes do not match for blending.")
    return (1.0 - weight) * coords1 + weight * coords2

def save_airfoil(filepath, name, coords):
    """
    翼型座標をXFOIL互換の.datフォーマットで保存する。
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"{name}\n")
        f.write("     \n")
        for p in coords:
            f.write(f"  {p[0]:.6f}  {p[1]:.6f}\n")

def get_blended_airfoil(config_airfoils, current_r_R, output_dir="temp_airfoils"):
    """
    設定ファイルの配置定義に基づいて、指定されたr/R位置の翼型を生成して保存する。
    config_airfoils: [{'r_R': 0.1, 'file': '...'}, ...] (r_Rでソート済みであること)
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 完全に定義位置と一致する場合はそのまま返す
    for item in config_airfoils:
        if abs(item['r_R'] - current_r_R) < 1e-6:
            name, coords = load_airfoil(item['file'])
            return item['file'], coords

    # ブレンドする区間を探す
    idx = 0
    while idx < len(config_airfoils) and config_airfoils[idx]['r_R'] < current_r_R:
        idx += 1

    if idx == 0:
        item = config_airfoils[0]
        name, coords = load_airfoil(item['file'])
        return item['file'], coords
    elif idx == len(config_airfoils):
        item = config_airfoils[-1]
        name, coords = load_airfoil(item['file'])
        return item['file'], coords
    else:
        item1 = config_airfoils[idx - 1]
        item2 = config_airfoils[idx]
        
        name1, coords1 = load_airfoil(item1['file'])
        name2, coords2 = load_airfoil(item2['file'])
        
        norm_coords1 = normalize_airfoil(coords1)
        norm_coords2 = normalize_airfoil(coords2)
        
        r_span  = item2['r_R'] - item1['r_R']
        weight  = (current_r_R - item1['r_R']) / r_span
        
        blended_coords = blend_airfoils(norm_coords1, norm_coords2, weight)
        
        new_name     = f"Blended_r{current_r_R:.3f}"
        new_filepath = os.path.join(output_dir, f"{new_name}.dat")
        save_airfoil(new_filepath, new_name, blended_coords)
        
        return new_filepath, blended_coords
