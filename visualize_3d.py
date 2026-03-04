"""
visualize_3d.py
===============
XROTORが出力したプロペラ設計ファイル（prop_result_iter*.txt 等）を読み込み、
プロペラのブレード形状を matplotlib で 3D 表示するスタンドアロンスクリプト。

コアロジック（データ読み込み・翼型ブレンド）は core/ モジュールに委譲している。

使い方:
    python visualize_3d.py prop_result_iter2.txt config.yaml
    python visualize_3d.py prop_result_iter2.txt config.yaml --blades 2 --save prop3d.png
"""

import sys
import os
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401（3D axes の登録）
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# Windows 用日本語フォント
matplotlib.rcParams['font.family'] = 'MS Gothic'
matplotlib.rcParams['axes.unicode_minus'] = False

# core/ モジュールを参照できるようにパスを追加
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.xrotor_runner import parse_xrotor_output
from core.airfoil_utils import get_blended_airfoil, load_airfoil
from utils.config import load_config

try:
    from stl import mesh as stl_mesh
    HAS_STL = True
except ImportError:
    HAS_STL = False

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


# ─────────────────────────────────────────────
# NACA 4桁翼型（DATファイルが存在しない場合のフォールバック）
# ─────────────────────────────────────────────

def naca4_profile(code: str = "4412", n_pts: int = 100) -> np.ndarray:
    """
    NACA 4桁翼型の座標を返す（外部DATファイルが読めない場合の代替）。
    戻り値は (x, y) の形式。
    """
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    t = int(code[2:4]) / 100.0

    x = np.linspace(0, 1, n_pts)
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x
                  - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4)

    if p > 0 and m > 0:
        yc_fore = m / p**2 * (2 * p * x - x**2)
        yc_aft  = m / (1 - p)**2 * (1 - 2 * p + 2 * p * x - x**2)
        yc = np.where(x < p, yc_fore, yc_aft)
        dyc_fore = 2 * m / p**2 * (p - x)
        dyc_aft  = 2 * m / (1 - p)**2 * (p - x)
        dyc = np.where(x < p, dyc_fore, dyc_aft)
        theta = np.arctan(dyc)
    else:
        yc    = np.zeros_like(x)
        theta = np.zeros_like(x)

    xu = x  - yt * np.sin(theta)
    yu = yc + yt * np.cos(theta)
    xl = x  + yt * np.sin(theta)
    yl = yc - yt * np.cos(theta)

    coords = np.vstack([
        np.column_stack([xu[::-1], yu[::-1]]),
        np.column_stack([xl[1:],   yl[1:]])
    ])
    return coords


# ─────────────────────────────────────────────
# 翼型プロファイルの取得（core/ モジュールに委譲）
# ─────────────────────────────────────────────

def get_airfoil_coords(airfoils_cfg: list, r_R: float, n_pts: int = 60,
                        work_dir: str = "temp_work") -> np.ndarray:
    """
    config.yaml の airfoils セクションを参照して r/R に対応する翼型座標を返す。
    core.airfoil_utils.get_blended_airfoil に処理を委譲する。
    DATファイルが読めない場合は NACA4412 で代替する。

    Returns
    -------
    numpy.ndarray, shape (N, 2)
        無次元翼型座標 (x, y)
    """
    fallback = naca4_profile("4412", n_pts)

    try:
        # core/ の関数で翼型ブレンドを実行（temp_work に書き出す）
        _, coords = get_blended_airfoil(airfoils_cfg, r_R, output_dir=work_dir)
    except Exception:
        return fallback

    if coords is None or len(coords) == 0:
        return fallback

    # 点数を n_pts に揃える線形補間
    tgt = np.linspace(0, 1, n_pts)
    src = np.linspace(0, 1, len(coords))
    cx = np.interp(tgt, src, coords[:, 0])
    cy = np.interp(tgt, src, coords[:, 1])
    return np.column_stack([cx, cy])


# ─────────────────────────────────────────────
# 3D ブレード形状 生成
# ─────────────────────────────────────────────

def build_blade_stations(geom_data: list, config: dict,
                         n_pts: int = 60, work_dir: str = "temp_work") -> list:
    """
    各半径断面の 3D 座標を積み上げた station リストを返す。

    Parameters
    ----------
    work_dir : str
        翼型ブレンドファイルのキャッシュ先ディレクトリ。
        main.py から 'temp_work' を渡すことでフェース順序に整合性を保つ。

    座標系（右手系）:
        X 軸 = ブレード半径方向（ハブ→翼端）
        Y 軸 = コード方向（回転面内）
        Z 軸 = 推力方向（ロータ軸）
    """
    R            = config["propeller"]["R"]
    airfoils_cfg = config["airfoils"]
    stations     = []

    for row in geom_data:
        r_R      = row["r/R"]
        c_R      = row["c/R"]
        beta_deg = row["beta"]

        c        = c_R * R
        r        = r_R * R
        beta_rad = np.radians(beta_deg)

        coords = get_airfoil_coords(airfoils_cfg, r_R, n_pts, work_dir=work_dir)

        xc = (coords[:, 0] - 0.25) * c
        yc =  coords[:, 1]         * c

        Y_rot = xc * np.cos(beta_rad) - yc * np.sin(beta_rad)
        Z_rot = xc * np.sin(beta_rad) + yc * np.cos(beta_rad)

        station_pts = np.column_stack([np.full_like(xc, r), Y_rot, Z_rot])
        stations.append(station_pts)

    return stations


def rotate_blade(stations: list, angle_rad: float) -> list:
    """ブレード全体をロータ軸（Z 軸）まわりに angle_rad 回転させる。"""
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    rot = np.array([[ cos_a, -sin_a, 0],
                    [ sin_a,  cos_a, 0],
                    [     0,      0, 1]])
    return [st @ rot.T for st in stations]


# ─────────────────────────────────────────────
# STL エクスポート
# ─────────────────────────────────────────────

def export_stl_from_stations(stations: list, filename: str = "propeller.stl", num_blades: int = 2) -> None:
    """station リストから STL ファイルを出力する。numpy-stl が必要。"""
    if not HAS_STL:
        import logging
        logging.warning("numpy-stl is not installed. Skipping STL export.")
        return

    vertices = []
    faces = []

    for k in range(len(stations) - 1):
        s1 = stations[k]
        s2 = stations[k + 1]
        N = len(s1)

        v_start = len(vertices)
        vertices.extend(s1)
        vertices.extend(s2)

        for i in range(N - 1):
            idx_p1 = v_start + i
            idx_p2 = v_start + i + 1
            idx_p3 = v_start + N + i
            idx_p4 = v_start + N + i + 1
            faces.append([idx_p1, idx_p2, idx_p3])
            faces.append([idx_p2, idx_p4, idx_p3])

    vertices = np.array(vertices)
    faces = np.array(faces)

    final_vertices = list(vertices)
    final_faces = list(faces)

    for b in range(1, num_blades):
        angle = 2.0 * np.pi * b / num_blades
        rot = np.array([
            [ np.cos(angle), -np.sin(angle), 0],
            [ np.sin(angle),  np.cos(angle), 0],
            [             0,              0, 1]
        ])
        rot_v = np.dot(vertices, rot.T)
        v_offset = len(final_vertices)
        final_vertices.extend(rot_v)
        final_faces.extend(faces + v_offset)

    final_vertices = np.array(final_vertices)
    final_faces = np.array(final_faces)

    prop_mesh = stl_mesh.Mesh(np.zeros(final_faces.shape[0], dtype=stl_mesh.Mesh.dtype))
    for i, f in enumerate(final_faces):
        for j in range(3):
            prop_mesh.vectors[i][j] = final_vertices[f[j], :]

    prop_mesh.save(filename)
    import logging
    logging.info(f"STL exported to {filename}")


def export_plotly_html_from_stations(stations: list, filename: str = "propeller_3d.html", num_blades: int = 2) -> None:
    """station リストから Plotly インタラクティブ HTML を出力する。plotly が必要。"""
    if not HAS_PLOTLY:
        import logging
        logging.warning("plotly is not installed. Skipping interactive 3D export.")
        return

    fig = go.Figure()

    for b in range(num_blades):
        angle = 2.0 * np.pi * b / num_blades
        cos_a = np.cos(angle)
        sin_a = np.sin(angle)

        X_all, Y_all, Z_all = [], [], []
        max_pts = max(len(s) for s in stations)

        for station in stations:
            x = station[:, 0]
            y = station[:, 1]
            z = station[:, 2]

            X_rot = x * cos_a - y * sin_a
            Y_rot = x * sin_a + y * cos_a

            if len(X_rot) < max_pts:
                pad = max_pts - len(X_rot)
                X_rot = np.pad(X_rot, (0, pad), constant_values=np.nan)
                Y_rot = np.pad(Y_rot, (0, pad), constant_values=np.nan)
                z     = np.pad(z,     (0, pad), constant_values=np.nan)

            X_all.append(X_rot)
            Y_all.append(Y_all)
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
    import logging
    logging.info(f"Interactive 3D geometry saved to {filename}")


# ─────────────────────────────────────────────
# matplotlib による 3D プロット
# ─────────────────────────────────────────────

def plot_propeller_3d(geom_data: list,
                      config: dict,
                      save_path: str | None = None,
                      n_pts: int = 60,
                      show: bool = True) -> None:
    """
    matplotlib Axes3D でプロペラ形状を 3D 表示する。

    Parameters
    ----------
    geom_data : XROTORパース結果のリスト
    config    : config.yaml の辞書
    save_path : 保存先ファイルパス（None なら保存しない）
    n_pts     : 翼型の輪郭点数
    show      : plt.show() を呼ぶかどうか
    """
    B = config["propeller"].get("B", 2)
    prop_name = config["propeller"].get("name", "Propeller")

    stations_ref = build_blade_stations(geom_data, config, n_pts)

    fig = plt.figure(figsize=(12, 10))
    ax  = fig.add_subplot(111, projection="3d")

    colors_face = ["#4FC3F7", "#80DEEA", "#B2DFDB", "#C8E6C9"]
    colors_edge = ["#0288D1", "#00838F", "#00695C", "#388E3C"]

    for b in range(B):
        angle = 2.0 * np.pi * b / B
        stations = rotate_blade(stations_ref, angle)

        # 断面輪郭線（ワイヤフレーム）
        for st in stations:
            ax.plot(st[:, 0], st[:, 1], st[:, 2],
                    color=colors_edge[b % len(colors_edge)],
                    linewidth=0.7, alpha=0.6)

        # 翼面パネル（隣接断面間の四辺形を三角形に分割して描画）
        n_stations = len(stations)
        col = colors_face[b % len(colors_face)]

        polys = []
        for k in range(n_stations - 1):
            s1, s2 = stations[k], stations[k + 1]
            n = len(s1) - 1
            for i in range(n):
                tri1 = [s1[i], s1[i + 1], s2[i]]
                tri2 = [s1[i + 1], s2[i + 1], s2[i]]
                polys.append(tri1)
                polys.append(tri2)

        poly_coll = Poly3DCollection(polys,
                                     facecolor=col, edgecolor="none",
                                     alpha=0.45, linewidth=0)
        ax.add_collection3d(poly_coll)

        # 翼端・翼根 断面塗りつぶし
        for st in [stations[0], stations[-1]]:
            verts = [list(zip(st[:, 0], st[:, 1], st[:, 2]))]
            cap = Poly3DCollection(verts,
                                   facecolor=col, edgecolor=colors_edge[b % len(colors_edge)],
                                   alpha=0.6, linewidth=0.5)
            ax.add_collection3d(cap)

    # ハブ（簡易円柱）
    R_hub     = config["propeller"].get("Rhub", 0.05)
    theta_hub = np.linspace(0, 2 * np.pi, 60)
    z_hub     = np.linspace(-R_hub * 0.8, R_hub * 0.8, 8)
    Th, Zh    = np.meshgrid(theta_hub, z_hub)
    Xh = R_hub * np.cos(Th)
    Yh = R_hub * np.sin(Th)
    ax.plot_surface(Xh, Yh, Zh,
                    color="#607D8B", alpha=0.7, linewidth=0,
                    antialiased=True)

    R   = config["propeller"]["R"]
    lim = R * 1.05
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim * 0.15, lim * 0.15)

    ax.set_xlabel("X — 半径方向 [m]", labelpad=8)
    ax.set_ylabel("Y — コード方向 [m]", labelpad=8)
    ax.set_zlabel("Z — 推力軸 [m]", labelpad=8)
    ax.set_title(f"プロペラ 3D 形状: {prop_name}\n"
                 f"R={R:.2f} m, B={B} blades, "
                 f"{len(geom_data)} stations",
                 fontsize=13, pad=14)

    ax.view_init(elev=30, azim=20)
    ax.set_box_aspect([1, 1, 0.1])

    fig.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        print(f"[OK] 3D 形状を保存しました → {save_path}")

    if show:
        plt.show()
    plt.close(fig)


# ─────────────────────────────────────────────
# ブレード断面の詳細サブプロット
# ─────────────────────────────────────────────

def plot_blade_sections(geom_data: list,
                        config: dict,
                        save_path: str | None = None,
                        n_pts: int = 80) -> None:
    """各 r/R 断面の翼型形状（2D）と，弦長・ねじり角の分布を表示する。"""
    R            = config["propeller"]["R"]
    airfoils_cfg = config["airfoils"]
    n            = len(geom_data)

    fig = plt.figure(figsize=(14, 3 + n * 1.8))
    gs  = fig.add_gridspec(n + 1, 3, hspace=0.5, wspace=0.35)

    r_R_vals  = [d["r/R"]  for d in geom_data]
    c_R_vals  = [d["c/R"]  for d in geom_data]
    beta_vals = [d["beta"] for d in geom_data]
    c_vals    = [c * R for c in c_R_vals]

    ax_c    = fig.add_subplot(gs[0, 0])
    ax_beta = fig.add_subplot(gs[0, 1])

    ax_c.plot(r_R_vals, c_vals, "o-", color="#1565C0", linewidth=2)
    ax_c.set_xlabel("r/R")
    ax_c.set_ylabel("弦長 c [m]")
    ax_c.set_title("弦長分布")
    ax_c.grid(True, linestyle="--", alpha=0.5)

    ax_beta.plot(r_R_vals, beta_vals, "s-", color="#B71C1C", linewidth=2)
    ax_beta.set_xlabel("r/R")
    ax_beta.set_ylabel("ねじり角 β [deg]")
    ax_beta.set_title("ねじり角分布")
    ax_beta.grid(True, linestyle="--", alpha=0.5)

    cmap = plt.cm.coolwarm
    r_arr = np.array(r_R_vals)

    for i, row in enumerate(geom_data):
        ax = fig.add_subplot(gs[i + 1, :])
        coords = get_airfoil_coords(airfoils_cfg, row["r/R"], n_pts)
        color  = cmap((row["r/R"] - r_arr.min()) / max(r_arr.max() - r_arr.min(), 1e-6))

        ax.fill(coords[:, 0], coords[:, 1], color=color, alpha=0.4)
        ax.plot(coords[:, 0], coords[:, 1], color=color, linewidth=1.5)
        ax.axhline(0, color="grey", linewidth=0.4, linestyle="--")
        ax.set_aspect("equal")
        ax.set_title(f"r/R={row['r/R']:.3f}  c={row['c/R']*R:.4f} m  β={row['beta']:.1f}°",
                     fontsize=9)
        ax.axis("off")

    fig.suptitle("ブレード断面形状 詳細", fontsize=14, y=1.01)

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"[OK] 断面図を保存しました → {save_path}")

    plt.show()
    plt.close(fig)


# ─────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="XROTORのプロペラ設計ファイルを3D表示するスクリプト"
    )
    parser.add_argument(
        "prop_file",
        nargs="?",
        default="prop_result_iter2.txt",
        help="XROTOR SAVEファイルのパス (デフォルト: prop_result_iter2.txt)"
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="config.yaml",
        help="設定ファイルのパス (デフォルト: config.yaml)"
    )
    parser.add_argument(
        "--blades", "-b",
        type=int, default=None,
        help="ブレード枕数の上書き（未指定時は config.yaml の propeller.B を使用）"
    )
    parser.add_argument(
        "--save", "-s",
        default=None,
        help="3D図の保存先ファイルパス (例: prop3d.png)"
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="plt.show() を呼ばずバッチ処理に徹する"
    )
    parser.add_argument(
        "--sections",
        action="store_true",
        help="断面形状の詳細図も表示する"
    )
    args = parser.parse_args()

    print(f"[情報] 読み込みファイル : {args.prop_file}")
    print(f"[情報] 設定ファイル     : {args.config}")

    geom_data = parse_xrotor_output(args.prop_file)
    print(f"[情報] {len(geom_data)} 断面のデータを読み込みました")
    for row in geom_data:
        print(f"       r/R={row['r/R']:.4f}  c/R={row['c/R']:.4f}  β={row['beta']:.2f}°")

    config = load_config(args.config)

    # No.10: --blades が指定された場合は config の B を上書きする
    if args.blades is not None:
        config["propeller"]["B"] = args.blades
        print(f"[情報] ブレード枕数をコマンドライン型引数で上書き: B={args.blades}")

    plot_propeller_3d(
        geom_data, config,
        save_path=args.save,
        show=not args.no_show
    )

    if args.sections:
        sec_save = args.save.replace(".png", "_sections.png") if args.save else None
        plot_blade_sections(geom_data, config, save_path=sec_save)


if __name__ == "__main__":
    main()
