import sys
import os
import shutil
import logging
import argparse
import json
from datetime import datetime
from utils.config import load_config
from utils.visualize import plot_geometry, plot_performance, plot_vrpm_map, export_vrpm_3d_html, plot_structural_properties
from core.design import design_propeller
from core.analysis import run_performance_sweep, run_vrpm_sweep
from core.structure import export_structural_properties

def setup_logging(log_path="designer.log"):
    """ログの設定。log_path 指定ファイルとコンソールの両方に出力。"""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)  # No.6: 明示的に setLevel を設定

    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    root.addHandler(fh)
    root.addHandler(sh)


def write_summary_json(path, prop_name, config, geom_data, perf_data, out_dir, phases_completed):
    """No.14: 全フェーズ完了後に設計サマリーを JSON として出力する。"""
    summary = {
        "generated_at": datetime.now().isoformat(),
        "prop_name": prop_name,
        "design_point": config.get('design_point', {}),
        "propeller": {
            "R": config['propeller'].get('R'),
            "Rhub": config['propeller'].get('Rhub'),
            "B": config['propeller'].get('B'),
        },
        "n_stations": len(geom_data) if geom_data else 0,
        "efficiency_at_design": None,
        "phases_completed": phases_completed,
        "output_dir": out_dir,
        "output_files": sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else [],
    }

    # 設計点付近の効率を perf_data から取得
    if perf_data:
        V   = config['design_point'].get('V',   7.5)
        RPM = config['design_point'].get('RPM', 120)
        R   = config['propeller'].get('R', 1.0)
        # J = V / (n * D) = V / (RPM/60 * 2R)
        J_des = V / (RPM / 60.0 * 2.0 * R)
        closest = min(perf_data, key=lambda x: abs(x['J'] - J_des))
        summary["efficiency_at_design"] = round(closest['Efficiency'], 4)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logging.info(f"Summary JSON saved to {path}")
    except Exception as e:
        logging.warning(f"Failed to write summary JSON: {e}")


def main():
    # No.12: argparse で CLI 引数を受け付ける
    parser = argparse.ArgumentParser(
        description="Propeller Designer — XFOIL/XROTOR を用いた自動プロペラ設計ツール"
    )
    parser.add_argument(
        "config",
        help="設計設定ファイルのパス (例: config.yaml)"
    )
    parser.add_argument(
        "--skip-phase",
        type=str, default="",
        metavar="PHASES",
        help=(
            "スキップするフェーズ番号をカンマ区切りで指定 (例: --skip-phase 1,2)。\n"
            "1,2=設計, 3=性能解析, 3.5=V-RPMマップ, 4=構造解析, 5=3Dモデル出力"
        )
    )
    args = parser.parse_args()

    # スキップフェーズを集合にパース
    skip_phases: set = set()
    for token in args.skip_phase.split(','):
        t = token.strip()
        if t:
            try:
                skip_phases.add(float(t))
            except ValueError:
                print(f"[警告] 不正なフェーズ番号: '{t}' → 無視します")

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    prop_name = config['propeller'].get('name', 'default_prop')
    out_dir   = os.path.join("output", prop_name)
    os.makedirs(out_dir, exist_ok=True)

    log_path = os.path.join(out_dir, "designer.log")
    setup_logging(log_path)
    logging.info(f"Output directory: {out_dir}")
    if skip_phases:
        logging.info(f"Skipping phases: {sorted(skip_phases)}")

    # 出力パスの定義
    prop_txt   = os.path.join(out_dir, "prop_result.txt")
    geom_png   = os.path.join(out_dir, "prop_design.png")
    perf_png   = os.path.join(out_dir, "prop_performance.png")
    struct_csv = os.path.join(out_dir, "structural_properties.csv")

    geom_data  = None
    perf_data  = None
    phases_completed = []

    # Phase 1 & 2: Propeller Design
    if not (1 in skip_phases or 2 in skip_phases):
        logging.info("\n--- Phase 1 & 2: Propeller Design ---")
        geom_data = design_propeller(config, prop_txt)
        if not geom_data:
            logging.error("Propeller design failed.")
            sys.exit(1)
        # No.11: 設計条件をタイトルに含める
        plot_geometry(geom_data, output_file=geom_png, show=False,
                      design_point=config.get('design_point'))
        phases_completed.append("design")
    else:
        # No.12: スキップ時は既存ファイルから読み込み
        logging.info("Phase 1 & 2 skipped. Loading existing design file...")
        if os.path.exists(prop_txt):
            from core.xrotor_runner import parse_xrotor_output
            geom_data = parse_xrotor_output(prop_txt)
            if geom_data:
                logging.info(f"  Loaded {len(geom_data)} stations from {prop_txt}")
            else:
                logging.error(f"Cannot read existing design file: {prop_txt}")
                sys.exit(1)
        else:
            logging.error(f"Phase 1&2 skipped but {prop_txt} not found. Run without --skip-phase first.")
            sys.exit(1)

    # Phase 3: Off-design Analysis
    if 3 not in skip_phases:
        logging.info("\n--- Phase 3: Off-design Performance Analysis ---")
        perf_data = run_performance_sweep(prop_txt, config, out_dir=out_dir)
        if perf_data:
            # No.12: 設計点 J の縦線を追加
            plot_performance(perf_data, output_file=perf_png, show=False,
                             design_point=config.get('design_point'),
                             propeller=config.get('propeller'))
            phases_completed.append("performance")
        else:
            logging.warning("Performance analysis failed or returned no data.")
    else:
        logging.info("Phase 3 skipped.")

    # Phase 3.5: V-RPM Efficiency Map
    if 3.5 not in skip_phases:
        logging.info("\n--- Phase 3.5: V-RPM Efficiency Map ---")
        map_png  = os.path.join(out_dir, "vrpm_efficiency_map.png")
        map_html = os.path.join(out_dir, "vrpm_3d.html")
        v_grid, rpm_grid, eff_grid = run_vrpm_sweep(prop_txt, config, out_dir=out_dir)
        if v_grid is not None:
            # No.10: 設計点★マーカーを追加
            plot_vrpm_map(v_grid, rpm_grid, eff_grid, output_file=map_png, show=False,
                          design_point=config.get('design_point'))
            export_vrpm_3d_html(v_grid, rpm_grid, eff_grid, filename=map_html)
            phases_completed.append("vrpm_map")
        else:
            logging.warning("V-RPM Sweep failed or returned no data.")
    else:
        logging.info("Phase 3.5 skipped.")

    # Phase 4: Structural Properties
    if 4 not in skip_phases:
        logging.info("\n--- Phase 4: Structural Properties Calculation ---")
        struct_png = os.path.join(out_dir, "structural_properties.png")
        struct_data = export_structural_properties(
            geom_data, config['airfoils'], config['propeller']['R'],
            output_file=struct_csv, work_dir="temp_work"
        )
        if struct_data:
            plot_structural_properties(struct_data, output_file=struct_png, show=False)
            phases_completed.append("structural")
    else:
        logging.info("Phase 4 skipped.")

    # Phase 5: 3D Visualization and Export
    if 5 not in skip_phases:
        logging.info("\n--- Phase 5: 3D Visualization & Export ---")
        p5_ok = []  # 完了済みサブフェーズリスト
        try:
            from visualize_3d import build_blade_stations, plot_propeller_3d
            from visualize_3d import export_stl_from_stations, export_plotly_html_from_stations
            num_blades = config['propeller'].get('B', 2)
            stations   = build_blade_stations(geom_data, config, work_dir="temp_work")

            png_3d = os.path.join(out_dir, "prop_3d.png")
            try:
                plot_propeller_3d(geom_data, config, save_path=png_3d, show=False)
                p5_ok.append("3d_png")
            except Exception as e:
                logging.warning(f"3D PNG 生成失敗: {e}")

            stl_path = os.path.join(out_dir, "propeller.stl")
            try:
                export_stl_from_stations(stations, filename=stl_path, num_blades=num_blades)
                p5_ok.append("stl")
            except Exception as e:
                logging.warning(f"STL 出力失敗: {e}")

            html_path = os.path.join(out_dir, "propeller_3d.html")
            try:
                export_plotly_html_from_stations(stations, filename=html_path, num_blades=num_blades)
                p5_ok.append("html")
            except Exception as e:
                logging.warning(f"Plotly HTML 出力失敗 (plotly 未インストールの可能性): {e}")

            # No.6: 少なくとも1つ完了されたら 3d_export とマーク
            if p5_ok:
                phases_completed.append("3d_export")
            logging.info(f"Phase 5 完了: {', '.join(p5_ok) if p5_ok else 'なし'}")

        except Exception as e:
            logging.warning(f"Phase 5 (3D出力) 全体が失敗: {e}")
    else:
        logging.info("Phase 5 skipped.")

    # No.5: Phase 5 終了後に temp_work クリーンアップ
    if config['analysis'].get('cleanup_temp', True):
        work_dir = "temp_work"
        if os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir)
                logging.info(f"Cleaned up temporary directory: {work_dir}")
            except Exception as e:
                logging.warning(f"Could not remove temp directory '{work_dir}': {e}")

    # No.7: 全フェーズ実行後のサマリーログ
    logging.info("\n" + "=" * 60)
    logging.info("DESIGN SUMMARY")
    logging.info(f"  Propeller  : {prop_name}")
    logging.info(f"  Stations   : {len(geom_data) if geom_data else 'N/A'}")
    logging.info(f"  Completed  : {', '.join(phases_completed) if phases_completed else 'none'}")
    logging.info(f"  Output dir : {out_dir}")
    logging.info("=" * 60)

    # No.14: サマリー JSON を出力
    summary_json = os.path.join(out_dir, "summary.json")
    write_summary_json(summary_json, prop_name, config, geom_data, perf_data, out_dir, phases_completed)

    logging.info("All processes complete.")


if __name__ == "__main__":
    main()
