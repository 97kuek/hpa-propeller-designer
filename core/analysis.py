import os
import subprocess
import logging
import numpy as np

XROTOR_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "xrotor.exe")

def run_performance_sweep(prop_file, config, output_file="prop_performance.txt"):
    """
    保存されたプロペラ設計ファイルを読み込み、OPERメニューでAdvance Ratio (J) をスイープし、
    結果をテキストファイルに出力する。
    """
    if not os.path.exists(prop_file):
        logging.error(f"Propeller file {prop_file} not found for analysis.")
        return None
        
    p_conf = config.get('propeller', {})
    d_conf = config.get('design_point', {})
    
    R = p_conf.get('R', 1.0)
    RPM = d_conf.get('RPM', 120)
    
    rps = RPM / 60.0
    D = 2.0 * R
    
    # 解析用のJスイープ設定 (config等で指定可にしても良いが一旦ハードコード気味で設定)
    # 設計Vから計算される設計Jを中心に前後を解析する
    V_design = d_conf.get('V', 7.5)
    D = 2.0 * R
    V_design = d_conf.get('V', 7.5)
    J_design = V_design / (rps * D)
    
    J_min = max(0.1, J_design - 0.4)
    J_max = J_design + 0.5
    J_inc = 0.05
    
    commands = [
        "LOAD\n",
        f"{prop_file}\n",
        "OPER\n",
        "ITER\n100\n",
        f"RPM\n{RPM}\n"
    ]
    
    # Calculate point by point to ensure robustness and easy parsing
    J_values = np.arange(J_min, J_max + 1e-5, J_inc)
    for j_val in J_values:
        adv_val = j_val / np.pi
        commands.extend([
            f"ADVA\n{adv_val}\n"   # Change advance ratio (triggers evaluation automatically)
        ])
    commands.extend([
        "\n",              # 抜ける
        "QUIT\n"
    ])
    
    try:
        process = subprocess.Popen(
            [XROTOR_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        try:
            stdout, stderr = process.communicate(input="".join(commands), timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            logging.error("XROTOR performance sweep timed out.")
            return None
            
        with open('xrotor_analysis.log', 'w') as f:
            f.write(stdout)
            
        return parse_performance_output_from_stdout(stdout, J_values)
        
    except Exception as e:
        logging.error(f"Error running XROTOR performance sweep: {e}")
        return None

def parse_performance_output_from_stdout(stdout_text, expected_j_values=None):
    """
    STDOUTに含まれる評価ブロックからJ, CT, CP (Ct, Cp), Efficiency を抽出する
    """
    import re
    data = []
    
    blocks = stdout_text.split("Free Tip Potential Formulation Solution")
    
    # Store parsed values
    parsed = {}
    for block in blocks[1:]: 
        try:
            m_j = re.search(r"J:\s+([0-9.]+)", block)
            m_ctcp = re.search(r"Ct:\s+([\-0-9.]+)\s+Cp:\s+([\-0-9.]+)", block)
            m_eff = re.search(r"Efficiency\s*:\s+([\-0-9.]+)", block)
            
            if m_j and m_ctcp:
                j_val = float(m_j.group(1))
                ct_val = float(m_ctcp.group(1))
                cp_val = float(m_ctcp.group(2))
                eff_val = 0.0
                if m_eff:
                    eff_val = float(m_eff.group(1))
                    if not (0.0 <= eff_val <= 1.0):
                        eff_val = 0.0
                
                if abs(ct_val) < 10.0 and abs(cp_val) < 10.0:
                    parsed[round(j_val, 4)] = {'J': j_val, 'Ct': ct_val, 'Cq': cp_val, 'Efficiency': eff_val}
        except Exception:
            pass
            
            
    # Reconstruct continuous array using expected_j_values to detect missing convergences
    if expected_j_values is not None:
        for expected_j in expected_j_values:
            key = round(expected_j, 4)
            # Find closest parsed key to account for float variations
            closest_key = None
            if parsed:
                closest_key = min(parsed.keys(), key=lambda k: abs(k - key))
            
            if closest_key is not None and abs(closest_key - key) < 0.01:
                data.append(parsed[closest_key])
            else:
                # XROTOR failed to converge this point, fill with NaN
                data.append({'J': expected_j, 'Ct': np.nan, 'Cq': np.nan, 'Efficiency': np.nan})
                
        # Interpolate NaNs
        import pandas as pd
        df = pd.DataFrame(data)
        df.interpolate(method='linear', limit_direction='both', inplace=True)
        # Drop persisting nans (e.g if all are nan)
        df.dropna(inplace=True)
        data = df.to_dict('records')
    else:
        # Fallback if expected_j_values not provided
        data = list(parsed.values())
        
    return data

def run_vrpm_sweep(prop_file, config):
    """
    V (Velocity) と RPM の2次元マトリクスでオフデザイン解析を行い、
    効率(Efficiency)の等高線マップ用データを返す。
    Returns: (V_grid, RPM_grid, Eff_grid) as 2D numpy arrays.
    """
    if not os.path.exists(prop_file):
        logging.error(f"Propeller file {prop_file} not found for V-RPM sweep.")
        return None, None, None
        
    p_conf = config.get('propeller', {})
    d_conf = config.get('design_point', {})
    
    R = p_conf.get('R', 1.0)
    V_des = d_conf.get('V', 7.5)
    RPM_des = d_conf.get('RPM', 120)
    
    # Define sweep ranges centered around design point
    v_vals = np.linspace(max(1.0, V_des - 3.0), V_des + 3.0, 15)
    rpm_vals = np.linspace(max(10, RPM_des - 40), RPM_des + 40, 15)
    
    V_grid, RPM_grid = np.meshgrid(v_vals, rpm_vals)
    Eff_grid = np.zeros_like(V_grid)
    
    commands = [
        "LOAD\n",
        f"{prop_file}\n",
        "OPER\n",
        "ITER\n100\n"
    ]
    
    # Store the expected order of computation to map back to grid
    expected_points = []
    
    for i in range(V_grid.shape[0]):
        for j in range(V_grid.shape[1]):
            v = V_grid[i, j]
            rpm = RPM_grid[i, j]
            
            # Change RPM and V (VELO triggers the calculation automatically)
            commands.extend([
                f"RPM\n{rpm}\n",
                f"VELO\n{v}\n"
            ])
            expected_points.append((i, j))
            
    commands.extend([
        "\n",
        "QUIT\n"
    ])
    
    try:
        process = subprocess.Popen(
            [XROTOR_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        try:
            stdout, stderr = process.communicate(input="".join(commands), timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            logging.error("XROTOR V-RPM sweep timed out.")
            return None, None, None
            
        import re
        blocks = stdout.split("Free Tip Potential Formulation Solution")[1:]
        
        # Match expected points with parsed outputs
        # XROTOR outputs solutions in the exact order we input the VELO commands
        for idx, block in enumerate(blocks):
            if idx < len(expected_points):
                i, j = expected_points[idx]
                m_eff = re.search(r"Efficiency\s*:\s+([\-0-9.]+)", block)
                if m_eff:
                    val = float(m_eff.group(1))
                    if 0.0 <= val <= 1.0:
                        Eff_grid[i, j] = val
                    else:
                        Eff_grid[i, j] = 0.0 # Clamp impossible efficiencies
                else:
                    Eff_grid[i, j] = 0.0 # Failed to converge at this point
                    
        return V_grid, RPM_grid, Eff_grid
        
    except Exception as e:
        logging.error(f"Error running XROTOR V-RPM sweep: {e}")
        return None, None, None
