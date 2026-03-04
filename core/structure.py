import csv
import os
import logging
import numpy as np

def calculate_section_properties(coords, chord):
    """
    翼型断面の断面積、重心、断面二次モーメントをグリーンの定理（Shoelace公式）で計算する。

    .. important::
        本関数は翼型の外形輪郭を **ソリッド（中実）断面** として扱い計算します。
        実際のブレードがスキン（薄板）構造や内部スパー構造を持つ場合、
        ここで得られる断面積や断面二次モーメントは実際の値と大きく異なります。
        構造強度・重量推算を行う際は、実際の断面構成（スキン厚み、スパー配置等）を
        別途考慮してください。

    Parameters
    ----------
    coords : numpy.ndarray, shape (N, 2)
        翼型の輪郭点群。外周に沿って順番に並んでいること（例: TE → LE → TE）。
        座標は無次元（コード長 = 1.0）を想定。
    chord : float
        実弦長 [m]。coords に乗算してスケールする。

    Returns
    -------
    area : float
        断面積 [m^2]（ソリッド断面）
    x_c : float
        重心 X 座標 [m]
    y_c : float
        重心 Y 座標 [m]
    I_x : float
        重心回りの断面二次モーメント（面外方向, I_xx） [m^4]
    I_y : float
        重心回りの断面二次モーメント（面内方向, I_yy） [m^4]
    """
    # 物理座標にスケール
    x = coords[:, 0] * chord
    y = coords[:, 1] * chord
    
    # グリーン定理（Shoelace公式）で面積・図心・断面二次モーメントを算出
    x_next = np.roll(x, -1)
    y_next = np.roll(y, -1)
    
    cross_prod = (x * y_next - x_next * y)
    
    # 面積
    area = 0.5 * np.sum(cross_prod)
    
    if abs(area) < 1e-10:
        return 0, 0, 0, 0, 0
    
    # 重心 (Centroid)
    x_c = (1.0 / (6.0 * area)) * np.sum((x + x_next) * cross_prod)
    y_c = (1.0 / (6.0 * area)) * np.sum((y + y_next) * cross_prod)
    
    # 原点回りの断面二次モーメント
    I_x_origin = (1.0 / 12.0) * np.sum((y**2 + y*y_next + y_next**2) * cross_prod)
    I_y_origin = (1.0 / 12.0) * np.sum((x**2 + x*x_next + x_next**2) * cross_prod)
    
    # 平行軸の定理により、重心回りへ変換
    I_x = I_x_origin - area * y_c**2
    I_y = I_y_origin - area * x_c**2
    
    # 面積は絶対値で返す（頂点順序による符号反転を防ぐ）
    return abs(area), x_c, y_c, abs(I_x), abs(I_y)

def export_structural_properties(geom_data, airfoils_cfg, R, output_file="structural_properties.csv",
                                 work_dir="temp_work"):
    """
    設計された全ステーションの翼型について構造特性を計算しCSVに出力する。

    Parameters
    ----------
    work_dir : str
        ブレンド済み翼型ファイルのキャッシュ先ディレクトリ（デフォルト: 'temp_work'）

    .. note::
        断面積・断面二次モーメントはソリッド断面として計算しています。
        スキン・スパー構造の実際の構造設計には追加の情報が必要です。
    """
    if not geom_data:
        logging.error("No geometry data available for structural export.")
        return None

    logging.warning(
        "Structural properties are computed assuming a SOLID cross-section. "
        "For skin/spar structures, results may significantly differ from reality."
    )
        
    from core.airfoil_utils import get_blended_airfoil, load_airfoil
    
    data_out = []
    
    for row in geom_data:
        r_R = row['r/R']
        c_R = row['c/R']
        chord = c_R * R
        
        target_path = os.path.join(work_dir, f"Blended_r{r_R:.3f}.dat")
        try:
            _, coords = load_airfoil(target_path)
        except FileNotFoundError:
            target_path, coords = get_blended_airfoil(airfoils_cfg, r_R, output_dir=work_dir)
            
        area, xc, yc, I_xx, I_yy = calculate_section_properties(coords, chord)
        
        data_out.append({
            'r/R': r_R,
            'Chord (m)': chord,
            'Area (m^2)': area,
            'Area (cm^2)': area * 1e4,
            'Centroid X (m)': xc,
            'Centroid Y (m)': yc,
            'I_xx (m^4)': I_xx,
            'I_xx (cm^4)': I_xx * 1e8,
            'I_yy (m^4)': I_yy,
            'I_yy (cm^4)': I_yy * 1e8,
        })
        
    if output_file:
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'r/R', 'Chord (m)',
                    'Area (m^2)', 'Area (cm^2)',
                    'Centroid X (m)', 'Centroid Y (m)',
                    'I_xx (m^4)', 'I_xx (cm^4)',
                    'I_yy (m^4)', 'I_yy (cm^4)',
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for rd in data_out:
                    writer.writerow(rd)
                    
            logging.info(f"Structural properties exported to {output_file}")
        except Exception as e:
            logging.error(f"Failed to export structural properties: {e}")
            
    return data_out
