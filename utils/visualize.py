import matplotlib.pyplot as plt
import matplotlib
import logging
import os
import numpy as np

# 日本語フォントの設定（Windows標準のMS Gothic）
matplotlib.rcParams['font.family'] = 'MS Gothic'
matplotlib.rcParams['axes.unicode_minus'] = False # マイナス記号の文字化け防止

try:
    from stl import mesh
    HAS_STL = True
except ImportError:
    HAS_STL = False

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from core.airfoil_utils import get_blended_airfoil

def plot_geometry(geom_data, output_file="prop_design.png"):
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
    
    plt.title("プロペラ設計 断面形状", pad=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"Geometry plot saved to {output_file}")
    plt.show()
    plt.close()

def plot_performance(perf_data, output_file="prop_performance.png"):
    """
    XROTOR OPER結果(Advance Ratio, Ct, Cq, Efficiency)をグラフ化する。
    """
    if not perf_data:
        logging.warning("No performance data to plot.")
        return
        
    j = [row['J'] for row in perf_data]
    ct = [row['Ct'] for row in perf_data]
    cq = [row['Cq'] * 10 for row in perf_data] # スケール調整
    eff = [row['Efficiency'] for row in perf_data]
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    ax1.set_xlabel('前進比 (J = V/nD)')
    ax1.set_ylabel('推力係数 (Ct) / トルク係数 (10*Cq)', color='tab:blue')
    ax1.plot(j, ct, marker='o', color='tab:blue', label='推力係数 (Ct)')
    ax1.plot(j, cq, marker='s', color='tab:cyan', label='トルク係数 (10*Cq)')
    ax1.tick_params(axis='y', labelcolor='tab:blue')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    ax2 = ax1.twinx()
    ax2.set_ylabel('推進効率 ($\eta$)', color='tab:red')
    ax2.plot(j, eff, marker='^', color='tab:red', label='推進効率')
    ax2.tick_params(axis='y', labelcolor='tab:red')
    
    # 凡例の結合
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.title("オフデザイン性能 (J - Ct - Cq)", pad=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"Performance plot saved to {output_file}")
    plt.show()
    plt.close()

def plot_vrpm_map(V_grid, RPM_grid, Eff_grid, output_file="vrpm_efficiency_map.png"):
    """
    V-RPMマトリクスの効率等高線マップを描画する関数。
    """
    if V_grid is None or Eff_grid is None:
        logging.warning("No V-RPM data to plot.")
        return
        
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Draw contour
    levels = np.linspace(0.0, 1.0, 21)
    cp = ax.contourf(V_grid, RPM_grid, Eff_grid, levels=levels, cmap='jet')
    
    # Add contour lines for better visibility
    contours = ax.contour(V_grid, RPM_grid, Eff_grid, levels=levels, colors='black', linewidths=0.5, alpha=0.5)
    ax.clabel(contours, inline=True, fontsize=8, fmt='%.2f')
    
    # Add colorbar
    cbar = fig.colorbar(cp)
    cbar.set_label('推進効率 ($\eta$)')
    
    ax.set_xlabel('飛行速度 V (m/s)')
    ax.set_ylabel('プロペラ回転数 (RPM)')
    ax.set_title('V-RPM 効率等高線マップ')
    ax.grid(True, linestyle='--', alpha=0.6)
    
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"V-RPM Efficiency Map saved to {output_file}")
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
    
    # 描画オプションの設定
    fig.update_layout(
        title="Interactive 3D V-RPM Efficiency Surface",
        scene=dict(
            xaxis_title="Flight Velocity V (m/s)",
            yaxis_title="Propeller Speed (RPM)",
            zaxis_title="Efficiency (eta)"
        ),
        margin=dict(l=0, r=0, b=0, t=50) # マージンを詰める
    )
    
    fig.write_html(filename)
    logging.info(f"Interactive 3D V-RPM Map saved to {filename}")

def plot_structural_properties(struct_data, output_file="structural_properties.png"):
    """
    各断面のArea, Ixx, Iyyをグラフ化して保存する機能
    """
    if not struct_data:
        logging.warning("No structural data to plot.")
        return
        
    r_R = [row['r/R'] for row in struct_data]
    area = [row['Area (m^2)'] * 1e4 for row in struct_data] # Convert to cm^2 for better scale
    ixx = [row['I_xx (m^4)'] * 1e8 for row in struct_data]  # Convert to cm^4
    iyy = [row['I_yy (m^4)'] * 1e8 for row in struct_data]
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    # Area (cm^2)
    color1 = 'tab:blue'
    ax1.set_xlabel('r/R (無次元半径)')
    ax1.set_ylabel('断面積 [cm^2]', color=color1)
    ax1.plot(r_R, area, marker='o', color=color1, label='断面積', linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    # Moment of Inertia (cm^4)
    ax2 = ax1.twinx()
    color2 = 'tab:red'
    ax2.set_ylabel('断面二次モーメント Ixx, Iyy [cm^4]', color=color2)
    ax2.plot(r_R, ixx, marker='^', linestyle='-', color=color2, label='I_xx (面内曲げ)')
    ax2.plot(r_R, iyy, marker='s', linestyle='--', color='tab:orange', label='I_yy (面外曲げ)')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
    
    plt.title("ブレード構造特性 分布", pad=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file, dpi=300)
    logging.info(f"Structural Properties plot saved to {output_file}")
    plt.show()
    plt.close()

# ==========================================
# 3D Visualization and Export Functions
# ==========================================

def generate_propeller_mesh(geom_data, config):
    """
    Generate 3D points for the propeller blade.
    Returns: list of (N, 3) arrays representing the 3D coordinates.
    """
    R = config['propeller']['R']
    airfoils_cfg = config['airfoils']
    
    stations_3d = []
    
    for row in geom_data:
        r_R = row['r/R']
        c_R = row['c/R']
        beta_deg = row['beta']
        
        c = c_R * R
        r = r_R * R
        beta_rad = np.radians(beta_deg)
        
        # Get normalized coordinates
        _, coords_2d = get_blended_airfoil(airfoils_cfg, r_R, output_dir="temp_work")
        
        # Align pitch axis (e.g., quarter-chord x=0.25)
        x = (coords_2d[:, 0] - 0.25) * c
        y = coords_2d[:, 1] * c
        
        # Rotate by beta (twist). Twist is around Z axis outward.
        # X is chordwise (disk plane), Y is thrust direction.
        X_rot = x * np.cos(beta_rad) - y * np.sin(beta_rad)
        Y_rot = x * np.sin(beta_rad) + y * np.cos(beta_rad)
        Z_rot = np.full_like(x, r)
        
        station_pts = np.column_stack((X_rot, Z_rot, Y_rot)) # Swap Y and Z for standard 3D rendering (Z up = thrust)
        stations_3d.append(station_pts)
        
    # Add a hub mesh (extend the first station inwards to r=0 for a closed look)
    if stations_3d:
        root_station = stations_3d[0]
        # Extract the X (chordwise) and Y (thrust) points
        x_root = root_station[:, 0]
        y_root = root_station[:, 2] # we swapped them during creation
        
        # Scale down X and Y slightly to form a closed bullet shape, place at Z=0
        x_hub = x_root * 0.1
        y_hub = y_root * 0.1
        z_hub = np.zeros_like(x_hub)
        
        hub_pts = np.column_stack((x_hub, z_hub, y_hub))
        stations_3d.insert(0, hub_pts)
        
    return stations_3d

def export_stl(stations_3d, filename="propeller.stl", num_blades=2):
    if not HAS_STL:
        logging.warning("numpy-stl is not installed. Skipping STL export.")
        return
        
    # Create triangles between adjacent stations
    vertices = []
    faces = []
    
    vertex_offset = 0
    for k in range(len(stations_3d) - 1):
        s1 = stations_3d[k]
        s2 = stations_3d[k+1]
        N = len(s1)
        
        v_start = len(vertices)
        vertices.extend(s1)
        vertices.extend(s2)
        
        for i in range(N - 1):
            idx_p1 = v_start + i
            idx_p2 = v_start + i + 1
            idx_p3 = v_start + N + i
            idx_p4 = v_start + N + i + 1
            
            # Triangle 1 & 2
            faces.append([idx_p1, idx_p2, idx_p3])
            faces.append([idx_p2, idx_p4, idx_p3])
            
    vertices = np.array(vertices)
    faces = np.array(faces)
    
    # Mirror blades
    final_vertices = list(vertices)
    final_faces = list(faces)
    
    for b in range(1, num_blades):
        angle = 2.0 * np.pi * b / num_blades
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        
        rot_matrix = np.array([
            [cos_a, -sin_a, 0],
            [sin_a,  cos_a, 0],
            [    0,      0, 1]
        ])
        
        rot_vertices = np.dot(vertices, rot_matrix.T)
        v_offset = len(final_vertices)
        
        final_vertices.extend(rot_vertices)
        final_faces.extend(faces + v_offset)
        
    final_vertices = np.array(final_vertices)
    final_faces = np.array(final_faces)

    prop_mesh = mesh.Mesh(np.zeros(final_faces.shape[0], dtype=mesh.Mesh.dtype))
    for i, f in enumerate(final_faces):
        for j in range(3):
            prop_mesh.vectors[i][j] = final_vertices[f[j], :]

    prop_mesh.save(filename)
    logging.info(f"STL exported to {filename}")

def export_plotly_html(stations_3d, filename="propeller_3d.html", num_blades=2):
    if not HAS_PLOTLY:
        logging.warning("plotly is not installed. Skipping interactive 3D export.")
        return
        
    fig = go.Figure()
    
    for b in range(num_blades):
        angle = 2.0 * np.pi * b / num_blades
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)
        
        X_all = []
        Y_all = []
        Z_all = []
        
        max_pts = max(len(s) for s in stations_3d)
        
        for station in stations_3d:
            x = station[:, 0]
            y = station[:, 1]
            z = station[:, 2]
            
            X_rot = x * cos_a - y * sin_a
            Y_rot = x * sin_a + y * cos_a
            
            if len(X_rot) < max_pts:
                pad_size = max_pts - len(X_rot)
                X_rot = np.pad(X_rot, (0, pad_size), constant_values=np.nan)
                Y_rot = np.pad(Y_rot, (0, pad_size), constant_values=np.nan)
                z = np.pad(z, (0, pad_size), constant_values=np.nan)
            
            X_all.append(X_rot)
            Y_all.append(Y_rot)
            Z_all.append(z)
            
        X_all = np.array(X_all)
        Y_all = np.array(Y_all)
        Z_all = np.array(Z_all)
        
        fig.add_trace(go.Surface(x=X_all, y=Y_all, z=Z_all, colorscale='Viridis', showscale=False))
        
    fig.update_layout(
        title="3D Propeller Geometry",
        scene=dict(xaxis_title="X (m)", yaxis_title="Y (m)", zaxis_title="Thrust Axis Z (m)", aspectmode='data')
    )
    
    fig.write_html(filename)
    logging.info(f"Interactive 3D geometry saved to {filename}")

def export_3d_models(geom_data, config, out_dir="."):
    """Main export entry point."""
    stations = generate_propeller_mesh(geom_data, config)
    num_blades = config['propeller'].get('blades', 2)
    export_stl(stations, os.path.join(out_dir, "propeller.stl"), num_blades)
    export_plotly_html(stations, os.path.join(out_dir, "propeller_3d.html"), num_blades)
