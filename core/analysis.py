import os
import re
import subprocess
import logging
import numpy as np
import pandas as pd
import concurrent.futures

# No.14: tqdm はオプショナル依存（未インストール時も動作する）
try:
    from tqdm import tqdm as _tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    _tqdm = None

XROTOR_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "xrotor.exe")

def run_performance_sweep(prop_file, config, out_dir="."):
    """
    保存されたプロペラ設計ファイルを読み込み、OPERメニューで Advance Ratio (J) をスイープし
    Ct/Cq/効率の特性曲線データを返す。
    """
    if not os.path.exists(prop_file):
        logging.error(f"Propeller file {prop_file} not found for analysis.")
        return None
        
    p_conf = config.get('propeller', {})
    d_conf = config.get('design_point', {})
    
    R   = p_conf.get('R', 1.0)
    RPM = d_conf.get('RPM', 120)
    rps      = RPM / 60.0
    D        = 2.0 * R
    V_design = d_conf.get('V', 7.5)
    J_design = V_design / (rps * D)
    
    a_conf      = config.get('analysis', {})
    j_sweep_cfg = a_conf.get('j_sweep', {})
    j_margin_low  = j_sweep_cfg.get('j_margin_low',  0.4)
    j_margin_high = j_sweep_cfg.get('j_margin_high', 0.5)
    J_inc         = j_sweep_cfg.get('j_step',        0.05)
    
    J_min = max(0.1, J_design - j_margin_low)
    J_max = J_design + j_margin_high
    
    commands = [
        "LOAD\n", f"{prop_file}\n",
        "OPER\n", "ITER\n100\n", f"RPM\n{RPM}\n"
    ]
    
    J_values = np.arange(J_min, J_max + 1e-5, J_inc)
    for j_val in J_values:
        # XROTOR の ADVA は "advance per radian" = V/(Ω·R) = J/π
        # 標準前進比 J = V/(nD) を π で除算して渡す
        adv_val = j_val / np.pi
        commands.append(f"ADVA\n{adv_val}\n")

    commands.extend(["\n", "QUIT\n"])
    
    try:
        process = subprocess.Popen(
            [XROTOR_PATH], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        # No.2: xrotor_timeout を config から取得（デフォルト 60 秒）
        xrotor_timeout = config.get('analysis', {}).get('xrotor_timeout', 60)
        try:
            stdout, _ = process.communicate(input="".join(commands), timeout=xrotor_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, _ = process.communicate()
            logging.error("XROTOR performance sweep timed out.")
            return None

        log_path = os.path.join(out_dir, "xrotor_analysis.log")
        with open(log_path, 'w') as f:
            f.write(stdout)
            
        return parse_performance_output_from_stdout(stdout, J_values)
        
    except Exception as e:
        logging.error(f"Error running XROTOR performance sweep: {e}")
        return None

def parse_performance_output_from_stdout(stdout_text, expected_j_values=None):
    """STDOUTに含まれる評価ブロックから J, Ct, Cp, Efficiency を抽出する"""
    data = []
    blocks = stdout_text.split("Free Tip Potential Formulation Solution")
    
    parsed = {}
    for block in blocks[1:]: 
        try:
            m_j    = re.search(r"J:\s+([0-9.]+)", block)
            m_ctcp = re.search(r"Ct:\s+([\-0-9.]+)\s+Cp:\s+([\-0-9.]+)", block)
            m_eff  = re.search(r"Efficiency\s*:\s+([\-0-9.]+)", block)
            
            if m_j and m_ctcp:
                j_val  = float(m_j.group(1))
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
            
    if expected_j_values is not None:
        for expected_j in expected_j_values:
            key = round(expected_j, 4)
            closest_key = None
            if parsed:
                closest_key = min(parsed.keys(), key=lambda k: abs(k - key))
            if closest_key is not None and abs(closest_key - key) < 0.01:
                data.append(parsed[closest_key])
            else:
                data.append({'J': expected_j, 'Ct': np.nan, 'Cq': np.nan, 'Efficiency': np.nan})
                
        df = pd.DataFrame(data)
        df.interpolate(method='linear', limit_direction='both', inplace=True)
        df.dropna(inplace=True)
        data = df.to_dict('records')
    else:
        data = list(parsed.values())
        
    return data


# ─────────────────────────────────────────────
# No.13: V-RPM スイープ — XROTOR チャンク並列実行用ヘルパー
# ─────────────────────────────────────────────

def _run_vrpm_chunk(xrotor_path, prop_file, chunk_points, timeout=120):
    """
    V-RPM スイープのサブセット（chunk_points）を1つの XROTOR プロセスで実行する。

    Parameters
    ----------
    chunk_points : list of (i, j, V, RPM)
    timeout : int

    Returns
    -------
    list of (i, j, efficiency)
    """
    if not chunk_points:
        return []

    commands = ["LOAD\n", f"{prop_file}\n", "OPER\n", "ITER\n100\n"]
    for _, _, v, rpm in chunk_points:
        commands.extend([f"RPM\n{rpm}\n", f"VELO\n{v}\n"])
    commands.extend(["\n", "QUIT\n"])

    try:
        process = subprocess.Popen(
            [xrotor_path], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            stdout, _ = process.communicate(input="".join(commands), timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, _ = process.communicate()
            return [(i, j, 0.0) for i, j, _, _ in chunk_points]

        blocks = stdout.split("Free Tip Potential Formulation Solution")[1:]
        results = []
        for idx, block in enumerate(blocks):
            if idx < len(chunk_points):
                ci, cj, _, _ = chunk_points[idx]
                m_eff = re.search(r"Efficiency\s*:\s+([\-0-9.]+)", block)
                if m_eff:
                    val = float(m_eff.group(1))
                    results.append((ci, cj, val if 0.0 <= val <= 1.0 else 0.0))
                else:
                    results.append((ci, cj, 0.0))
        return results

    except Exception as e:
        logging.error(f"V-RPM chunk failed: {e}")
        return [(i, j, 0.0) for i, j, _, _ in chunk_points]


def run_vrpm_sweep(prop_file, config, out_dir="."):
    """
    V (Velocity) と RPM の2次元マトリクスでオフデザイン解析を行い、
    効率(Efficiency)の等高線マップ用データを返す。

    No.13: Jスイープとは独立した N チャンクの XROTOR プロセスを並列実行して高速化。
    並列数は config.analysis.vrpm_sweep.n_workers で制御（デフォルト 4）。
    """
    if not os.path.exists(prop_file):
        logging.error(f"Propeller file {prop_file} not found for V-RPM sweep.")
        return None, None, None
        
    d_conf = config.get('design_point', {})
    V_des   = d_conf.get('V',   7.5)
    RPM_des = d_conf.get('RPM', 120)
    
    a_conf     = config.get('analysis', {})
    vrpm_cfg   = a_conf.get('vrpm_sweep', {})
    v_margin   = vrpm_cfg.get('v_margin',   3.0)
    rpm_margin = vrpm_cfg.get('rpm_margin', 40.0)
    n_points   = vrpm_cfg.get('n_points',   15)
    n_workers  = vrpm_cfg.get('n_workers',  4)
    
    v_vals   = np.linspace(max(1.0, V_des   - v_margin),   V_des   + v_margin,   n_points)
    rpm_vals = np.linspace(max(10,  RPM_des - rpm_margin), RPM_des + rpm_margin, n_points)
    
    V_grid, RPM_grid = np.meshgrid(v_vals, rpm_vals)
    Eff_grid = np.zeros_like(V_grid)
    
    # 全格子点リストを生成
    all_points = []
    for i in range(V_grid.shape[0]):
        for j in range(V_grid.shape[1]):
            all_points.append((i, j, V_grid[i, j], RPM_grid[i, j]))
    
    # No.13: チャンク分割して並列実行
    n_workers = max(1, min(n_workers, len(all_points)))
    chunk_size = max(1, len(all_points) // n_workers)
    chunks = [all_points[k:k + chunk_size] for k in range(0, len(all_points), chunk_size)]
    
    logging.info(f"V-RPM sweep: {len(all_points)} points split into {len(chunks)} chunks with {n_workers} workers.")

    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures_list = [
                executor.submit(_run_vrpm_chunk, XROTOR_PATH, prop_file, chunk, 120)
                for chunk in chunks
            ]

            # No.14: tqdm でチャンク単位の進捗を表示
            completed = 0
            desc = f"V-RPM sweep ({len(all_points)} pts)"
            if HAS_TQDM:
                pbar = _tqdm(total=len(all_points), desc=desc, unit="pt", leave=True)
            else:
                pbar = None

            for fut in concurrent.futures.as_completed(futures_list):
                try:
                    results = fut.result()
                    for (i, j, eff) in results:
                        Eff_grid[i, j] = eff
                    completed += len(results)
                    if pbar:
                        pbar.update(len(results))
                    else:
                        logging.info(f"  V-RPM sweep progress: {completed}/{len(all_points)} pts")
                except Exception as e:
                    logging.error(f"V-RPM chunk exception: {e}")

            if pbar:
                pbar.close()

        log_path = os.path.join(out_dir, "vrpm_sweep.log")
        with open(log_path, 'w') as f:
            f.write(f"V-RPM sweep completed: {len(all_points)} points, {n_workers} workers\n")
            
        return V_grid, RPM_grid, Eff_grid
        
    except Exception as e:
        logging.error(f"Error running XROTOR V-RPM sweep: {e}")
        return None, None, None
