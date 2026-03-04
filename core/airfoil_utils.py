import os
import numpy as np
from scipy.interpolate import interp1d

def load_airfoil(filepath):
    """
    XFOIL形式の翼型.datファイルを読み込み、numpy配列として返す。
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Airfoil file not found: {filepath}")

    with open(filepath, 'r') as f:
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
    翼型座標をX方向に沿って正規化（点群の間隔を整える）。
    上下面それぞれを補間して再サンプリングする。
    ここでは簡単なCosスペーシングを用いて前縁部分を密にする。
    """
    # 前縁(Leading Edge)のインデックスを探す (xが最小の点)
    le_idx = np.argmin(coords[:, 0])
    
    # 上面と下面に分割
    upper_coords = coords[:le_idx+1]
    lower_coords = coords[le_idx:]
    
    # X座標に基づいてソート（左から右へ）
    upper_coords = upper_coords[np.argsort(upper_coords[:, 0])]
    lower_coords = lower_coords[np.argsort(lower_coords[:, 0])]
    
    # xの共通グリッド(Cosスペーシング)
    beta = np.linspace(0, np.pi, n_points)
    x_new = 0.5 * (1 - np.cos(beta))
    
    # 上面と下面を別々に補間
    upper_interp = interp1d(upper_coords[:, 0], upper_coords[:, 1], kind='linear', fill_value="extrapolate")
    lower_interp = interp1d(lower_coords[:, 0], lower_coords[:, 1], kind='linear', fill_value="extrapolate")
    
    y_upper = upper_interp(x_new)
    y_lower = lower_interp(x_new)
    
    # XFOIL形式(Trailing Edge上面 -> Leading Edge -> Trailing Edge下面)に戻す
    new_upper = np.column_stack((x_new[::-1], y_upper[::-1]))
    new_lower = np.column_stack((x_new[1:], y_lower[1:]))
    
    normalized_coords = np.vstack((new_upper, new_lower))
    return normalized_coords

def blend_airfoils(coords1, coords2, weight):
    """
    2つの正規化された翼型座標を線形補間（ブレンド）する。
    weight: 0.0でcoords1のみ、1.0でcoords2のみ。
    """
    if coords1.shape != coords2.shape:
         # 座標の数が違う場合は片方をもう片方に合わせる必要があるが、
         # 事前に normalize_airfoil されていれば同じshapeになるはず
         raise ValueError("Airfoil coordinates shapes do not match for blending.")
         
    blended_coords = (1.0 - weight) * coords1 + weight * coords2
    return blended_coords

def save_airfoil(filepath, name, coords):
    """
    翼型座標をXFOIL互換の.datフォーマットで保存する。
    """
    with open(filepath, 'w') as f:
        f.write(f"{name}\n")
        f.write(" " * 5) # 空白行(XFOILのおまじない的)
        f.write("\n")
        for p in coords:
            f.write(f"  {p[0]:.6f}  {p[1]:.6f}\n")

def get_blended_airfoil(config_airfoils, current_r_R, output_dir="temp_airfoils"):
    """
    設定ファイルの配置定義に基づいて、指定されたr/R位置の翼型を生成して保存する。
    config_airfoils: [{'r_R': 0.1, 'file': '...'}, ...] (r_Rでソート済みであること)
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 完全に定義位置と一致するか確認
    for item in config_airfoils:
        if abs(item['r_R'] - current_r_R) < 1e-6:
            name, coords = load_airfoil(item['file'])
            return item['file'], coords

    # ブレンドする区間を探す
    idx = 0
    while idx < len(config_airfoils) and config_airfoils[idx]['r_R'] < current_r_R:
        idx += 1

    if idx == 0:
        # 最初の定義より内側の場合は最初の翼型を使う
        item = config_airfoils[0]
        name, coords = load_airfoil(item['file'])
        return item['file'], coords
    elif idx == len(config_airfoils):
        # 最後の定義より外側の場合は最後の翼型を使う
        item = config_airfoils[-1]
        name, coords = load_airfoil(item['file'])
        return item['file'], coords
    else:
        # 中間なので補間
        item1 = config_airfoils[idx-1]
        item2 = config_airfoils[idx]
        
        name1, coords1 = load_airfoil(item1['file'])
        name2, coords2 = load_airfoil(item2['file'])
        
        norm_coords1 = normalize_airfoil(coords1)
        norm_coords2 = normalize_airfoil(coords2)
        
        # 線形補間の重み計算
        r_span = item2['r_R'] - item1['r_R']
        weight = (current_r_R - item1['r_R']) / r_span
        
        blended_coords = blend_airfoils(norm_coords1, norm_coords2, weight)
        
        new_name = f"Blended_r{current_r_R:.3f}"
        new_filepath = os.path.join(output_dir, f"{new_name}.dat")
        save_airfoil(new_filepath, new_name, blended_coords)
        
        return new_filepath, blended_coords
