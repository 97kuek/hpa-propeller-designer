"""
visualize_3d.py
===============
XROTORが出力したプロペラ設計ファイル（prop_result_iter*.txt 等）を読み込み、
プロペラのブレード形状を matplotlib で 3D 表示するスタンドアロンスクリプト。

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


# ─────────────────────────────────────────────
# ファイル読み込みユーティリティ
# ─────────────────────────────────────────────

def parse_xrotor_output(filepath: str) -> list[dict]:
    """
    XROTOR の SAVE ファイルから r/R, c/R, beta(deg) を読み取って返す。
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"ファイルが見つかりません: {filepath}")

    data = []
    data_start = False

    with open(filepath, "r") as f:
        for line in f:
            if "r/R" in line and "C/R" in line and ("Beta0deg" in line or "beta" in line.lower()):
                data_start = True
                continue
            if "------" in line or "! " in line:
                continue
            if data_start:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        r_R  = float(parts[0].replace("D", "E"))
                        c_R  = float(parts[1].replace("D", "E"))
                        beta = float(parts[2].replace("D", "E"))
                        data.append({"r/R": r_R, "c/R": c_R, "beta": beta})
                    except ValueError:
                        break  # データ終端

    if not data:
        raise ValueError(f"ファイルからジオメトリデータを読み取れませんでした: {filepath}")

    return data


def load_config(config_path: str) -> dict:
    """config.yaml をロードして辞書で返す。"""
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
# 翼型プロファイル生成（NACA 4 桁系）
# ─────────────────────────────────────────────

def naca4_profile(code: str = "4412", n_pts: int = 100) -> np.ndarray:
    """
    NACA 4桁翼型の座標を返す (shape: [2*n_pts - 1, 2])。
    外部DAT ファイルがない場合の代替として使用。
    戻り値は (x, y) の順で、先端から後縁→先端の上面・下面を結合した形式。
    """
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    t = int(code[2:4]) / 100.0

    x = np.linspace(0, 1, n_pts)
    # 対称翼厚分布
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

    # 上面（後縁→前縁）＋下面（前縁→後縁）で輪郭を構成
    coords = np.vstack([
        np.column_stack([xu[::-1], yu[::-1]]),
        np.column_stack([xl[1:],   yl[1:]])
    ])
    return coords


def get_airfoil_coords(airfoils_cfg: list, r_R: float, n_pts: int = 60) -> np.ndarray:
    """
    config.yaml の airfoils セクションを参照して、r/R に対応する
    翼型座標を返す。DAT ファイルが読めない場合は NACA4412 で代替する。
    翼型は [0,1] の無次元座標系で (x, y) 列。
    """
    # r/R を挟む 2 断面を特定してブレンド比を計算
    sorted_cfg = sorted(airfoils_cfg, key=lambda c: c["r_R"])

    if r_R <= sorted_cfg[0]["r_R"]:
        segments = [(sorted_cfg[0], 1.0), (sorted_cfg[0], 0.0)]
    elif r_R >= sorted_cfg[-1]["r_R"]:
        segments = [(sorted_cfg[-1], 1.0), (sorted_cfg[-1], 0.0)]
    else:
        for i in range(len(sorted_cfg) - 1):
            if sorted_cfg[i]["r_R"] <= r_R <= sorted_cfg[i + 1]["r_R"]:
                t = ((r_R - sorted_cfg[i]["r_R"])
                     / (sorted_cfg[i + 1]["r_R"] - sorted_cfg[i]["r_R"]))
                segments = [(sorted_cfg[i], 1 - t), (sorted_cfg[i + 1], t)]
                break

    def read_dat(path):
        coords = []
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    try:
                        coords.append([float(parts[0]), float(parts[1])])
                    except ValueError:
                        pass
        return np.array(coords) if len(coords) >= 10 else None

    base_dir = os.path.dirname(os.path.abspath(__file__))
    fallback = naca4_profile("4412", n_pts)

    coords_list = []
    weights = []
    for cfg_entry, weight in segments:
        dat_path = os.path.join(base_dir, cfg_entry["file"])
        c = read_dat(dat_path)
        if c is None:
            c = fallback
        # 点数を n_pts に揃える線形補間
        tgt = np.linspace(0, 1, n_pts)
        src = np.linspace(0, 1, len(c))
        cx = np.interp(tgt, src, c[:, 0])
        cy = np.interp(tgt, src, c[:, 1])
        coords_list.append(np.column_stack([cx, cy]))
        weights.append(weight)

    # ブレンド
    blended = sum(w * c for w, c in zip(weights, coords_list))
    return blended


# ─────────────────────────────────────────────
# 3D ブレード形状 生成
# ─────────────────────────────────────────────

def build_blade_stations(geom_data: list[dict],
                         config: dict,
                         n_pts: int = 60) -> list[np.ndarray]:
    """
    各半径断面の 3D 座標を積み上げた station リストを返す。
    各 station は (n_pts, 3) の ndarray で、列は (X, Y, Z)。
    座標系:
        Z 軸 = ブレード半径方向（外向き）
        X 軸 = コード方向（回転面内）
        Y 軸 = 推力方向
    """
    R           = config["propeller"]["R"]
    airfoils_cfg = config["airfoils"]
    stations    = []

    for row in geom_data:
        r_R      = row["r/R"]
        c_R      = row["c/R"]
        beta_deg = row["beta"]

        c       = c_R * R
        r       = r_R * R
        beta_rad = np.radians(beta_deg)

        coords = get_airfoil_coords(airfoils_cfg, r_R, n_pts)

        # 1/4 コードをピッチ軸に合わせてシフト
        x = (coords[:, 0] - 0.25) * c
        y =  coords[:, 1]         * c

        # ねじり角 beta で回転（コード‐推力平面内）
        X_rot = x * np.cos(beta_rad) - y * np.sin(beta_rad)
        Y_rot = x * np.sin(beta_rad) + y * np.cos(beta_rad)
        Z_rot = np.full_like(x, r)

        stations.append(np.column_stack([X_rot, Y_rot, Z_rot]))

    return stations


def rotate_blade(stations: list[np.ndarray], angle_rad: float) -> list[np.ndarray]:
    """
    ブレード全体をロータ軸（Z 軸）まわりに angle_rad 回転させる。
    ここでは X‐Y 平面で回転し、Z はそのまま。
    """
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    rot = np.array([[cos_a, -sin_a, 0],
                    [sin_a,  cos_a, 0],
                    [0,      0,     1]])
    return [st @ rot.T for st in stations]


# ─────────────────────────────────────────────
# matplotlib による 3D プロット
# ─────────────────────────────────────────────

def plot_propeller_3d(geom_data: list[dict],
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

    # 1 枚目のブレード local stations
    stations_ref = build_blade_stations(geom_data, config, n_pts)

    fig = plt.figure(figsize=(12, 10))
    ax  = fig.add_subplot(111, projection="3d")

    colors_face   = ["#4FC3F7", "#80DEEA", "#B2DFDB", "#C8E6C9"]
    colors_edge   = ["#0288D1", "#00838F", "#00695C", "#388E3C"]

    for b in range(B):
        angle = 2.0 * np.pi * b / B
        stations = rotate_blade(stations_ref, angle)

        # ── 断面輪郭線（ワイヤフレーム）
        for st in stations:
            ax.plot(st[:, 0], st[:, 1], st[:, 2],
                    color=colors_edge[b % len(colors_edge)],
                    linewidth=0.7, alpha=0.6)

        # ── 翼面パネル（隣接断面間の四辺形を三角形に分割して描画）
        n_stations = len(stations)
        col = colors_face[b % len(colors_face)]

        polys = []
        for k in range(n_stations - 1):
            s1, s2 = stations[k], stations[k + 1]
            n = len(s1) - 1
            for i in range(n):
                # 四辺形の 2 三角形
                tri1 = [s1[i], s1[i + 1], s2[i]]
                tri2 = [s1[i + 1], s2[i + 1], s2[i]]
                polys.append(tri1)
                polys.append(tri2)

        poly_coll = Poly3DCollection(polys,
                                     facecolor=col, edgecolor="none",
                                     alpha=0.45, linewidth=0)
        ax.add_collection3d(poly_coll)

        # ── 翼端・翼根 断面塗りつぶし
        for st in [stations[0], stations[-1]]:
            verts = [list(zip(st[:, 0], st[:, 1], st[:, 2]))]
            cap = Poly3DCollection(verts,
                                   facecolor=col, edgecolor=colors_edge[b % len(colors_edge)],
                                   alpha=0.6, linewidth=0.5)
            ax.add_collection3d(cap)

    # ── ハブ（簡易円柱）
    R_hub = config["propeller"].get("Rhub", 0.05)
    theta_hub = np.linspace(0, 2 * np.pi, 60)
    z_hub     = np.linspace(-R_hub * 0.5, R_hub * 0.5, 8)
    Th, Zh    = np.meshgrid(theta_hub, z_hub)
    Xh = R_hub * np.cos(Th)
    Yh = R_hub * np.sin(Th)
    ax.plot_surface(Xh, Yh, Zh,
                    color="#607D8B", alpha=0.6, linewidth=0,
                    antialiased=True)

    # ── 軸設定
    R  = config["propeller"]["R"]
    lim = R * 1.05
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim * 0.4, lim * 1.2)

    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.set_zlabel("Z (半径方向) [m]")
    ax.set_title(f"プロペラ 3D 形状: {prop_name}\n"
                 f"R={R:.2f} m, B={B} blades, "
                 f"{len(geom_data)} stations",
                 fontsize=13, pad=14)

    ax.view_init(elev=25, azim=-45)
    ax.set_box_aspect([1, 1, 0.8])

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

def plot_blade_sections(geom_data: list[dict],
                        config: dict,
                        save_path: str | None = None,
                        n_pts: int = 80) -> None:
    """各 r/R 断面の翼型形状（2D）と，弦長・ねじり角の分布を表示する。"""
    R            = config["propeller"]["R"]
    airfoils_cfg = config["airfoils"]
    n            = len(geom_data)

    fig = plt.figure(figsize=(14, 3 + n * 1.8))
    gs  = fig.add_gridspec(n + 1, 3, hspace=0.5, wspace=0.35)

    # ── 上段: 弦長・ねじり角分布
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

    # ── 各断面の翼型形状
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
        "--save", "-s",
        default=None,
        help="3D図の保存先ファイルパス (例: prop3d.png)"
    )
    parser.add_argument(
        "--sections",
        action="store_true",
        help="断面形状の詳細図も表示する"
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="plt.show() を呼ばずバッチ処理に徹する"
    )
    args = parser.parse_args()

    print(f"[情報] 読み込みファイル : {args.prop_file}")
    print(f"[情報] 設定ファイル     : {args.config}")

    geom_data = parse_xrotor_output(args.prop_file)
    print(f"[情報] {len(geom_data)} 断面のデータを読み込みました")
    for row in geom_data:
        print(f"       r/R={row['r/R']:.4f}  c/R={row['c/R']:.4f}  β={row['beta']:.2f}°")

    config = load_config(args.config)

    # 3D プロット
    plot_propeller_3d(
        geom_data, config,
        save_path=args.save,
        show=not args.no_show
    )

    # 断面プロット（オプション）
    if args.sections:
        sec_save = args.save.replace(".png", "_sections.png") if args.save else None
        plot_blade_sections(geom_data, config, save_path=sec_save)


if __name__ == "__main__":
    main()
