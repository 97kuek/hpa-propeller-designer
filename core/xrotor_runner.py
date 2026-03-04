import os
import subprocess
import re
import logging
import numpy as np

XROTOR_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "xrotor.exe")

# No.9: 起動時に実行ファイルの存在を確認
if not os.path.exists(XROTOR_PATH):
    import logging as _log
    _log.warning(f"XROTOR executable not found: {XROTOR_PATH}\n"
                 "  XROTOR が見つかりません。run_xrotor_design() はすべて失敗します。")

def write_aero_file(filepath, r_R, polar_data, re_ref="1.000E+05", re_exp="-0.2000"):
    """
    XROTORのAERO->READで読み込めるAero Sectionファイル(.txt)を出力する

    揚力傾斜 (dCl/dα) は線形領域 (-2°〜4°) のデータに対して
    最小二乗フィット（np.polyfit）を用いて算出する。
    """
    if not polar_data:
        raise ValueError("No polar data provided")

    cl_max  = max(p['CL'] for p in polar_data)
    cl_min  = min(p['CL'] for p in polar_data)
    cd_min  = min(p['CD'] for p in polar_data)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Aero data for r/R = {r_R:.3f}\n")
        
        # 線形揚力域でのデータを取得し、最小二乗フィットで揚力傾斜を推算
        linear_region = [p for p in polar_data if -2.0 <= p['alpha'] <= 6.0]
        if len(linear_region) >= 3:
            alphas = np.array([p['alpha'] for p in linear_region]) * (np.pi / 180.0)  # rad
            cls    = np.array([p['CL']    for p in linear_region])
            # 1次多項式フィット（傾きが揚力傾斜 dCl/dα [1/rad]）
            coeffs = np.polyfit(alphas, cls, 1)
            dcl_da = coeffs[0]
        elif len(linear_region) >= 2:
            # データが少ない場合は両端の2点から推算
            p1, p2 = linear_region[0], linear_region[-1]
            if p2['alpha'] != p1['alpha']:
                dcl_da = (p2['CL'] - p1['CL']) / ((p2['alpha'] - p1['alpha']) * (np.pi / 180.0))
            else:
                dcl_da = 2.0 * np.pi  # デフォルト（薄翼理論値）
        else:
            dcl_da = 2.0 * np.pi  # デフォルト（薄翼理論値）
            
        f.write(f"0.0   {dcl_da:.4f}  {dcl_da*0.5:.4f}  {cl_max:.4f}  {cl_min:.4f}\n")
        
        cl_at_cdmin = min(polar_data, key=lambda x: x['CD'])['CL']
        f.write(f"{cd_min:.5f}   {cl_at_cdmin:.4f}   0.0100   0.8000\n")
        f.write(f"{re_ref}   {re_exp}\n")

def run_xrotor_design(config, aero_files_dict, output_file="prop_design.txt", log_dir="."):
    """
    設定ファイルと各Aeroファイルを用いてXROTOR DESIコマンドを操作する

    Parameters
    ----------
    log_dir : str
        xrotor_design.log の出力先ディレクトリ・デフォルト: カレントディレクトリ
    """
    output_path = os.path.abspath(output_file)
    
    if os.path.exists(output_path):
        os.remove(output_path)

    p_conf = config.get('propeller', {})
    d_conf = config.get('design_point', {})
    
    B    = p_conf.get('B',    2)
    R    = p_conf.get('R',    1.0)
    Rhub = p_conf.get('Rhub', 0.1)
    V    = d_conf.get('V',    7.5)
    RPM  = d_conf.get('RPM',  120)
    
    target_type  = d_conf.get('target', 'power')
    target_value = d_conf.get('value',  200)
    CL           = d_conf.get('CL',     0.5)

    commands = []
    
    # AERO セクションの定義
    commands.append("AERO\n")
    sorted_r_R = sorted(aero_files_dict.keys())
    for idx, r_r in enumerate(sorted_r_R):
        aero_rel_path = os.path.relpath(aero_files_dict[r_r]).replace('\\', '/')
        if idx == 0:
            commands.append("EDIT\n1\nREAD\n")
            commands.append(f"{aero_rel_path}\n")
            commands.append(f"{r_r:.3f}\n")
            commands.append("\n")
        else:
            commands.append("NEW\n")
            commands.append("READ\n")
            commands.append(f"{aero_rel_path}\n")
            commands.append(f"{r_r:.3f}\n")
            commands.append("\n")
            
    commands.append("\n")
    
    # 設計メニュー
    commands.append("DESI\n")
    commands.append("EDIT\n")
    commands.append(f"B {B}\n")
    commands.append(f"RT {R}\n")
    commands.append(f"RH {Rhub}\n")
    commands.append(f"RW {Rhub}\n")
    commands.append(f"V {V}\n")
    # No.7: 空気密度を config から設定（高度・環境対応）
    rho = config.get('environment', {}).get('rho', 1.225)
    commands.append(f"RHO {rho}\n")
    
    if target_type.lower() == 'power':
        commands.append(f"R {RPM}\n")
        commands.append(f"P {target_value}\n")
    else:
        commands.append(f"R {RPM}\n")
        commands.append(f"T {target_value}\n")
        
    commands.append(f"CC {CL}\n")
    commands.append("\n")
    commands.append("\n")
    commands.append("\n")
    
    cwd     = os.path.dirname(os.path.abspath(__file__))
    out_rel = os.path.relpath(output_path, cwd).replace('\\', '/')
    commands.append("SAVE\n")
    commands.append(f"{out_rel}\n")
    commands.append("Y\n")
    commands.append("\n")
    commands.append("QUIT\n")
    
    try:
        process = subprocess.Popen(
            [XROTOR_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(input="".join(commands), timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            logging.error("XROTOR design process timed out.")
            return False
        
        xrotor_log_path = os.path.join(log_dir, "xrotor_design.log")
        with open(xrotor_log_path, "w") as f:
            f.write(stdout)
            
        if not os.path.exists(output_path):
            logging.error("XROTOR design output failed. output_path does not exist.")
            logging.debug(stdout)
            return False
            
    except Exception as e:
        logging.error(f"Error running XROTOR: {e}")
        return False
        
    return True

def parse_xrotor_output(filepath):
    """
    XROTORがSAVEで吐き出した固定ピッチプロペラの定義ファイルを読み取り、
    r/R, c/R, beta(deg) のリストを返す
    """
    if not os.path.exists(filepath):
        return None
        
    data = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
        
    data_start = False
    for line in lines:
        if "ERROR" in line or "Error" in line:
            logging.error(f"XROTOR Output Error: {line.strip()}")
            return None
            
        if "r/R" in line and "C/R" in line and ("Beta0deg" in line or "beta" in line.lower()):
            data_start = True
            continue
        if "------" in line or "! " in line:
            continue
            
        if data_start:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    r_R  = float(parts[0].replace('D', 'E'))
                    c_R  = float(parts[1].replace('D', 'E'))
                    beta = float(parts[2].replace('D', 'E'))
                    data.append({'r/R': r_R, 'c/R': c_R, 'beta': beta})
                except ValueError:
                    break
    
    return data
