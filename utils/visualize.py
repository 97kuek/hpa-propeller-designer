import matplotlib.pyplot as plt
import matplotlib
import logging
import os
import numpy as np

# 日本語フォントの設定（Windows標準のMS Gothic）
matplotlib.rcParams['font.family'] = 'MS Gothic'
matplotlib.rcParams['axes.unicode_minus'] = False  # マイナス記号の文字化け防止

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


def plot_geometry(geom_data, output_file="prop_design.png", show=True, design_point=None):
    """matplotlibを用いて設計結果をプロットして画像保存する"""
    r_R = [row['r/R'] for row in geom_data]
    c_R = [row['c/R'] for row in geom_data]
    beta = [row['beta'] for row in geom_data]
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    color1 = 'tab:blue'
    ax1.set_xlabel('r/R (無次元半径)')
    ax1.set_ylabel('c/R (弦長比)', color=color1)
    ax1.plot(r_R, c_R, marker='o', color=color1, label='弦長 (c/R)')
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    ax2 = ax1.twinx()
    color2 = 'tab:red'
    ax2.set_ylabel('Beta (ねじり角) [deg]', color=color2)
    ax2.plot(r_R, beta, marker='s', color=color2, label='ねじり角 (Beta)')
    ax2.tick_params(axis='y', labelcolor=color2)

    # No.11: 設計条件をタイトルに追加
    if design_point:
        V   = design_point.get('V', '?')
        RPM = design_point.get('RPM', '?')
        CL  = design_point.get('CL', '?')
        title = f"プロペラ設計 断面形状　V={V} m/s, RPM={RPM}, CL={CL}"
    else:
        title = "プロペラ設計 断面形状"
    plt.title(title, pad=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"Geometry plot saved to {output_file}")
    if show:
        plt.show()
    plt.close()

def plot_performance(perf_data, output_file="prop_performance.png", show=True,
                     design_point=None, propeller=None):
    """
    XROTOR OPER結果(Advance Ratio, Ct, Cq, Efficiency)をグラフ化する。
    """
    if not perf_data:
        logging.warning("No performance data to plot.")
        return
        
    j = [row['J'] for row in perf_data]
    ct = [row['Ct'] for row in perf_data]
    cq = [row['Cq'] * 10 for row in perf_data]  # スケール調整
    eff = [row['Efficiency'] for row in perf_data]
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    ax1.set_xlabel('前進比 (J = V/nD)')
    ax1.set_ylabel('推力係数 (Ct) / トルク係数 (10*Cq)', color='tab:blue')
    ax1.plot(j, ct, marker='o', color='tab:blue', label='推力係数 (Ct)')
    ax1.plot(j, cq, marker='s', color='tab:cyan', label='トルク係数 (10*Cq)')
    ax1.tick_params(axis='y', labelcolor='tab:blue')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    ax2 = ax1.twinx()
    ax2.set_ylabel('推進効率 ($\\eta$)', color='tab:red')
    ax2.plot(j, eff, marker='^', color='tab:red', label='推進効率')
    ax2.tick_params(axis='y', labelcolor='tab:red')

    # No.12: 設計点 J の縦線を追加
    if design_point and propeller:
        V   = design_point.get('V',   7.5)
        RPM = design_point.get('RPM', 120)
        R   = propeller.get('R',      1.0)
        J_des = V / (RPM / 60.0 * 2.0 * R)
        ax1.axvline(x=J_des, color='green', linestyle='--', linewidth=1.5, alpha=0.8,
                    label=f'設計点 J={J_des:.3f}')
    
    # 凡例の結合
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.title("オフデザイン性能 (J - Ct - Cq)", pad=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"Performance plot saved to {output_file}")
    if show:
        plt.show()
    plt.close()

def plot_vrpm_map(V_grid, RPM_grid, Eff_grid, output_file="vrpm_efficiency_map.png", show=True,
                  design_point=None):
    """
    V-RPMマトリクスの効率等高線マップを描画する関数。
    """
    if V_grid is None or Eff_grid is None:
        logging.warning("No V-RPM data to plot.")
        return
        
    fig, ax = plt.subplots(figsize=(10, 8))
    
    levels = np.linspace(0.0, 1.0, 21)
    cp = ax.contourf(V_grid, RPM_grid, Eff_grid, levels=levels, cmap='jet')
    
    contours = ax.contour(V_grid, RPM_grid, Eff_grid, levels=levels, colors='black', linewidths=0.5, alpha=0.5)
    ax.clabel(contours, inline=True, fontsize=8, fmt='%.2f')
    
    cbar = fig.colorbar(cp)
    cbar.set_label('推進効率 ($\\eta$)')
    
    ax.set_xlabel('飛行速度 V (m/s)')
    ax.set_ylabel('プロペラ回転数 (RPM)')
    ax.set_title('V-RPM 効率等高線マップ')
    ax.grid(True, linestyle='--', alpha=0.6)

    # No.10: 設計点★マーカーを追加
    if design_point:
        V_des   = design_point.get('V')
        RPM_des = design_point.get('RPM')
        if V_des is not None and RPM_des is not None:
            ax.plot(V_des, RPM_des,
                    marker='*', markersize=18,
                    color='white', markeredgecolor='black', markeredgewidth=1.2,
                    zorder=10, label=f'設計点 V={V_des}m/s, RPM={RPM_des}')
            ax.legend(loc='upper right', framealpha=0.8)
    
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"V-RPM Efficiency Map saved to {output_file}")
    if show:
        plt.show()
    plt.close()

def export_vrpm_3d_html(V_grid, RPM_grid, Eff_grid, filename="vrpm_3d.html"):
    """
    V-RPMマトリクスデータをPlotly 3D Surface（地形図）としてHTML出力する。
    """
    if not HAS_PLOTLY:
        logging.warning("plotly is not installed. Skipping interactive 3D V-RPM map export.")
        return
        
    if V_grid is None or Eff_grid is None:
        logging.warning("No V-RPM data to plot in 3D.")
        return
        
    fig = go.Figure(data=[go.Surface(
        x=V_grid, 
        y=RPM_grid, 
        z=Eff_grid, 
        colorscale='Jet',
        colorbar=dict(title='Efficiency (eta)')
    )])
    
    fig.update_layout(
        title="Interactive 3D V-RPM Efficiency Surface",
        scene=dict(
            xaxis_title="Flight Velocity V (m/s)",
            yaxis_title="Propeller Speed (RPM)",
            zaxis_title="Efficiency (eta)"
        ),
        margin=dict(l=0, r=0, b=0, t=50)
    )
    
    fig.write_html(filename)
    logging.info(f"Interactive 3D V-RPM Map saved to {filename}")

def plot_structural_properties(struct_data, output_file="structural_properties.png", show=True):
    """
    各断面のArea, Ixx, Iyyをグラフ化して保存する機能
    """
    if not struct_data:
        logging.warning("No structural data to plot.")
        return
        
    r_R = [row['r/R'] for row in struct_data]
    area = [row['Area (m^2)'] * 1e4 for row in struct_data]  # cm^2 に変換
    ixx = [row['I_xx (m^4)'] * 1e8 for row in struct_data]   # cm^4 に変換
    iyy = [row['I_yy (m^4)'] * 1e8 for row in struct_data]
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    color1 = 'tab:blue'
    ax1.set_xlabel('r/R (無次元半径)')
    ax1.set_ylabel('断面積 [cm^2]', color=color1)
    ax1.plot(r_R, area, marker='o', color=color1, label='断面積', linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    ax2 = ax1.twinx()
    color2 = 'tab:red'
    ax2.set_ylabel('断面二次モーメント Ixx, Iyy [cm^4]', color=color2)
    ax2.plot(r_R, ixx, marker='^', linestyle='-', color=color2, label='I_xx (面内曲げ)')
    ax2.plot(r_R, iyy, marker='s', linestyle='--', color='tab:orange', label='I_yy (面外曲げ)')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
    
    plt.title("ブレード構造特性 分布", pad=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"Structural Properties plot saved to {output_file}")
    if show:
        plt.show()
    plt.close()


# ==========================================
# 3D Visualization and Export (visualize_3d モジュールへ委譲)
# ==========================================

def export_3d_models(geom_data, config, out_dir="."):
    """
    プロペラの3DモデルをSTL形式およびPlotlyインタラクティブHTMLとして出力する。

    実装は visualize_3d モジュールに委譲している。
    STL出力には numpy-stl、HTML出力には plotly が必要。
    """
    # visualize_3d モジュールはプロジェクトルートに配置されているため
    # パスを追加してからインポートする
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from visualize_3d import build_blade_stations, plot_propeller_3d
        from visualize_3d import export_stl_from_stations, export_plotly_html_from_stations
    except ImportError as e:
        logging.warning(f"Could not import visualize_3d: {e}. Skipping 3D export.")
        return

    num_blades = config['propeller'].get('B', 2)
    stations = build_blade_stations(geom_data, config, work_dir="temp_work")

    stl_path = os.path.join(out_dir, "propeller.stl")
    html_path = os.path.join(out_dir, "propeller_3d.html")

    export_stl_from_stations(stations, filename=stl_path, num_blades=num_blades)
    export_plotly_html_from_stations(stations, filename=html_path, num_blades=num_blades)
