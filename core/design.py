import os
import sys
import numpy as np
import logging
import concurrent.futures

# 作成した各モジュールのインポート
from core.airfoil_utils import get_blended_airfoil
from core.xfoil_runner import run_xfoil_polar, read_polar
from core.xrotor_runner import write_aero_file, run_xrotor_design, parse_xrotor_output

def process_station(r_R, R, V, omega, visc, c_guess, geom_data, airfoils_cfg, work_dir, config):
    """XFOILによる各ステーションの並列計算処理"""
    r = r_R * R
    airfoil_path, _ = get_blended_airfoil(airfoils_cfg, r_R, output_dir=work_dir)
    logging.info(f"Station r/R={r_R:.3f}: Blended airfoil -> {os.path.basename(airfoil_path)}")
    
    current_c = c_guess
    if geom_data:
        closest_row = min(geom_data, key=lambda x: abs(x['r/R'] - r_R))
        current_c = closest_row['c/R'] * R
        
    v_local = np.sqrt(V**2 + (r * omega)**2)
    reynolds = int(v_local * current_c / visc)
    mach = v_local / 340.0
    
    polar_path = os.path.join(work_dir, f"polar_r{r_R:.3f}.txt")
    
    logging.info(f"  [r/R={r_R:.3f}] Running XFOIL: Re={reynolds}, M={mach:.3f} ...")
    success = run_xfoil_polar(
        airfoil_path, 
        reynolds, 
        mach, 
        ncrit=config['analysis'].get('ncrit', 9.0),
        max_iter=config['analysis'].get('iter', 200),
        output_polar_file=polar_path,
        alpha_seq=config['analysis'].get('alpha_seq', None)
    )
    
    if success and os.path.exists(polar_path):
        logging.info(f"  [r/R={r_R:.3f}] XFOIL SUCCESS.")
        polar_data = read_polar(polar_path)
        if polar_data:
            aero_path = os.path.join(work_dir, f"aero_r{r_R:.3f}.txt")
            write_aero_file(aero_path, r_R, polar_data, re_ref=f"{reynolds:.1E}")
            return r_R, aero_path
        else:
            logging.error(f"  [r/R={r_R:.3f}] Failed to extract data from polar.")
            return r_R, None
    else:
        logging.error(f"  [r/R={r_R:.3f}] XFOIL FAILED.")
        return r_R, None

def design_propeller(config, final_output="prop_result.txt"):
    """
    設定ファイルに基づいてプロペラの反復設計を行う。
    成功時は (geom_data, a list of dicts) を返し、失敗時は None を返す。
    """
    R = config['propeller']['R']
    Rhub = config['propeller']['Rhub']
    V = config['design_point']['V']
    RPM = config['design_point']['RPM']
    rho = config['environment']['rho']
    visc = config['environment']['visc']
    
    n_stations = config['analysis']['n_stations']
    airfoils_cfg = config['airfoils']
    
    work_dir = "temp_work"
    if not os.path.exists(work_dir):
        os.makedirs(work_dir)
        
    r_R_stations = np.linspace(Rhub/R, 1.0, n_stations)
    
    max_iter = config['analysis'].get('design_iters', 2)
    geom_data = None
    
    for iteration in range(1, max_iter + 1):
        logging.info(f"\n=======================================================")
        logging.info(f"   Design Iteration {iteration} / {max_iter}")
        logging.info(f"=======================================================")
        
        logging.info("\n--- Phase 1: Airfoil Blending & XFOIL Polar Generation ---")
        
        c_guess = 0.1
        rps = RPM / 60.0
        omega = 2.0 * np.pi * rps
        
        aero_files = {}
        
        # マルチプロセスによるXFOILの並列実行
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(
                    process_station,
                    r_R, R, V, omega, visc, c_guess, geom_data, airfoils_cfg, work_dir, config
                ): r_R
                for r_R in r_R_stations
            }
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    r_R_res, aero_path = future.result()
                    if aero_path:
                        aero_files[r_R_res] = aero_path
                    else:
                        logging.error(f"Station {r_R_res:.3f} failed generating polar data.")
                        return None
                except Exception as exc:
                    r_R_err = futures[future]
                    logging.error(f"Station {r_R_err:.3f} generated an exception: {exc}")
                    return None

        logging.info(f"\n--- Phase 2: XROTOR Design Optimization (Iter {iteration}) ---")
        output_prop_file = f"prop_result_iter{iteration}.txt"
        success = run_xrotor_design(config, aero_files, output_file=output_prop_file)
        
        if success:
            logging.info(f"\nDesign Complete for Iteration {iteration}! Result saved to {output_prop_file}")
            geom_data = parse_xrotor_output(output_prop_file)
            if not geom_data:
                logging.error("\nFailed to parse XROTOR output. Cannot proceed to next iteration.")
                return None
                
            if iteration == max_iter:
                logging.info("\nFinal Designed Geometry:")
                logging.info("  r/R     c/R     Beta (deg)")
                logging.info("------------------------------")
                for row in geom_data:
                    logging.info(f"  {row['r/R']:.4f}  {row['c/R']:.4f}  {row['beta']:.2f}")
        else:
            logging.error(f"\nXROTOR Optimization Failed at Iteration {iteration}.")
            return None

    import shutil
    iter_output = f"prop_result_iter{max_iter}.txt"
    if os.path.exists(iter_output):
        shutil.copy(iter_output, final_output)
        
    return geom_data
