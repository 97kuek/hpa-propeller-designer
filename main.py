import sys
import os
import logging
from utils.config import load_config
from utils.visualize import plot_geometry, plot_performance, export_3d_models, plot_vrpm_map, export_vrpm_3d_html, plot_structural_properties
from core.design import design_propeller
from core.analysis import run_performance_sweep, run_vrpm_sweep
from core.structure import export_structural_properties

def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler("designer.log"),
                            logging.StreamHandler(sys.stdout)
                        ])

def main():
    setup_logging()
    
    if len(sys.argv) < 2:
        logging.error("Usage: python main.py <config.yaml>")
        sys.exit(1)
        
    config_file = sys.argv[1]
    config = load_config(config_file)
    if not config:
        sys.exit(1)
        
    prop_name = config['propeller'].get('name', 'default_prop')
    out_dir = os.path.join("output", prop_name)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # Output paths
    prop_txt = os.path.join(out_dir, "prop_result.txt")
    geom_png = os.path.join(out_dir, "prop_design.png")
    perf_png = os.path.join(out_dir, "prop_performance.png")
    struct_csv = os.path.join(out_dir, "structural_properties.csv")

    # Phase 1 & 2: Propeller Design
    geom_data = design_propeller(config, prop_txt)
    if not geom_data:
        logging.error("Propeller design failed.")
        sys.exit(1)
    
    # Plot Output
    plot_geometry(geom_data, output_file=geom_png)
    
    # Phase 3: Off-design Analysis
    logging.info("\n--- Phase 3: Off-design Performance Analysis ---")
    perf_data = run_performance_sweep(prop_txt, config)
    if perf_data:
        plot_performance(perf_data, output_file=perf_png)
    else:
        logging.warning("Performance analysis failed or returned no data.")
        
    # Phase 3.5: V-RPM Efficiency Map
    logging.info("\n--- Phase 3.5: V-RPM Efficiency Map ---")
    map_png = os.path.join(out_dir, "vrpm_efficiency_map.png")
    v_grid, rpm_grid, eff_grid = run_vrpm_sweep(prop_txt, config)
    if v_grid is not None:
        plot_vrpm_map(v_grid, rpm_grid, eff_grid, output_file=map_png)
    else:
        logging.warning("V-RPM Sweep failed or returned no data.")
    
    # Phase 4: Structural Properties
    logging.info("\n--- Phase 4: Structural Properties Calculation ---")
    struct_png = os.path.join(out_dir, "structural_properties.png")
    struct_data = export_structural_properties(geom_data, config['airfoils'], config['propeller']['R'], output_file=None)
    if struct_data:
        plot_structural_properties(struct_data, output_file=struct_png)

    # Phase 5: 3D Visualization and Export
    # logging.info("\n--- Phase 5: 3D Visualization & Export ---")
    # try:
    #     # Pass the output directory
    #     export_3d_models(geom_data, config, out_dir=out_dir)
    # except Exception as e:
    #     logging.warning(f"3D Export failed: {e}")

    logging.info("All processes complete.")

if __name__ == "__main__":
    main()
