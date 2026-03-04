import csv
import logging
import numpy as np

def calculate_section_properties(coords, chord):
    """
    点群データとして与えられた翼型断面の断面積、重心、断面二次モーメントを
    コード長(chord)でスケールして計算する。
    coords: numpy array of shape (N, 2), ordered along the perimeter (e.g. TE -> LE -> TE)
    """
    # 物理座標にスケール
    x = coords[:, 0] * chord
    y = coords[:, 1] * chord
    
    # グリーン定理（多角形の面積と図心、断面二次モーメントの公式）
    # x_i, y_i と x_{i+1}, y_{i+1} を用いる
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
    # I_x = \int y^2 dA
    # I_y = \int x^2 dA
    I_x_origin = (1.0 / 12.0) * np.sum((y**2 + y*y_next + y_next**2) * cross_prod)
    I_y_origin = (1.0 / 12.0) * np.sum((x**2 + x*x_next + x_next**2) * cross_prod)
    
    # 平行軸の定理により、重心回りの断面二次モーメントへ変換
    I_x = I_x_origin - area * y_c**2
    I_y = I_y_origin - area * x_c**2
    
    # 面積は絶対値で返す (頂点順序による符号反転を防ぐ)
    return abs(area), x_c, y_c, abs(I_x), abs(I_y)

def export_structural_properties(geom_data, airfoils_cfg, R, output_file="structural_properties.csv"):
    """
    設計された全ステーションの翼型について構造特性を計算しCSVに出力する。
    """
    if not geom_data:
        logging.error("No geometry data available for structural export.")
        return None
        
    from core.airfoil_utils import get_blended_airfoil, load_airfoil, normalize_airfoil
    
    data_out = []
    
    for row in geom_data:
        r_R = row['r/R']
        c_R = row['c/R']
        chord = c_R * R
        
        # 必要なステーションの翼型座標を取得 (temp_work にすでにあるはずだが、再取得または再読み込み)
        target_path = f"temp_work/Blended_r{r_R:.3f}.dat"
        try:
            _, coords = load_airfoil(target_path)
            # normalize_airfoil かかっている前提ならそのまま
        except FileNotFoundError:
            # 見つからなければオンデマンド生成
            target_path, coords = get_blended_airfoil(airfoils_cfg, r_R, output_dir="temp_work")
            
        area, xc, yc, I_xx, I_yy = calculate_section_properties(coords, chord)
        
        data_out.append({
            'r/R': r_R,
            'Chord (m)': chord,
            'Area (m^2)': area,
            'Centroid X (m)': xc,
            'Centroid Y (m)': yc,
            'I_xx (m^4)': I_xx,
            'I_yy (m^4)': I_yy
        })
        
    if output_file:
        try:
            with open(output_file, 'w', newline='') as csvfile:
                fieldnames = ['r/R', 'Chord (m)', 'Area (m^2)', 'Centroid X (m)', 'Centroid Y (m)', 'I_xx (m^4)', 'I_yy (m^4)']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for rd in data_out:
                    writer.writerow(rd)
                    
            logging.info(f"Structural properties exported to {output_file}")
        except Exception as e:
            logging.error(f"Failed to export structural properties: {e}")
            
    return data_out
