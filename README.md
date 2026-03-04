# Propeller Designer

XFOILとXROTORを利用して、プロペラの設計・空力計算・構造解析・3Dモデル出力までを一貫して全自動で行う設計ツール。

## 組み込まれている理論と設計アルゴリズム

本ツールは以下の5つのフェーズに基づいて、統合的な設計を行う。

### 1. 翼型混合と解析データの取得

#### 1-1. 翼型座標の線形補間

プロペラブレードは根元（ハブ側）から翼端にかけて、構造的要求（高い曲げ剛性）と空力的要求（高い揚抗比 $L/D$）が相反するため、単一翼型では対応できない。
そこで翼根翼型（例: GEMINI）の座標 $\mathbf{P}_\text{root}(x,y)$ と翼端翼型（例: DAE51）の座標 $\mathbf{P}_\text{tip}(x,y)$ を、ブレード無次元半径 $r/R$ を補間パラメータとして線形ブレンドする。

$$
\mathbf{P}(x, r/R) = (1 - \xi)\,\mathbf{P}_\text{root}(x) + \xi\,\mathbf{P}_\text{tip}(x), \quad \xi = \frac{r/R - (r/R)_\text{root}}{1 - (r/R)_\text{root}}
$$

両翼型の座標点数が異なる場合は、一方を弧長パラメータ $s$ で均等再サンプルしてから補間する。
前縁点検出は弧長中点に最も近い x 最小点を採用しており、非整列翼型でも安定して動作する。

#### 1-2. 局所レイノルズ数・マッハ数の推算

各半径位置での設計周速成分と飛行速度成分を合成した**相対流速** $W$ を用いて局所レイノルズ数を計算する。

$$
V_\text{rot} = 2\pi\,n\,r, \quad W = \sqrt{V^2 + V_\text{rot}^2}
$$

$$
Re = \frac{W \, c}{\nu}, \quad Ma = \frac{W}{a}
$$

（$c$: 弦長, $\nu$: 動粘性係数, $a$: 音速）

#### 1-3. XFOILによる極曲線の生成

推算した $(Re, Ma)$ を XFOIL に与え、迎角 $\alpha$ を $-5°$ から $+15°$ まで自動スイープさせ、各断面の **揚力係数 – 抗力係数 ポーラ** $(C_L, C_D)$ を取得する。

揚力傾斜 $dC_L/d\alpha$ は線形域（$-2° \sim +6°$）のデータにNp.polyfit（最小二乗法）を適用して推算し、端点2点依存のバイアスを排除している。

### 2. 最小誘導損失理論（MIL）による最適プロペラ形状の設計

#### 2-1. 作動プロペラの基礎方程式

プロペラは推力 $T$ と吸収トルク $Q$ を持つ。これを無次元化した**推力係数** $C_T$ と**トルク係数** $C_Q$ を定義する。

$$
C_T = \frac{T}{\rho n^2 D^4}, \qquad C_Q = \frac{Q}{\rho n^2 D^5}
$$

プロペラ効率はこれらの比で定義される。

$$
\eta = \frac{C_T \cdot J}{2\pi \cdot C_Q} = \frac{T V}{Q \cdot 2\pi n}
$$

#### 2-2. ベッツの最適ウェイク条件

誘導損失が最小になるプロペラの後流は、剛体螺旋面（スクリュー面）を形成する。
これがベッツの最適条件であり、ウェイク内の誘導軸速度 $w_a$ と誘導回転速度 $w_t$ の比が全半径位置で一定値 $\lambda_w$（**ウェイクヘリックス係数**）を満たすことを要請する。

$$
\tan\phi_w = \frac{V + w_a}{\Omega r - w_t} = \text{const} \equiv \lambda_w
$$

（$\phi_w$: ウェイク螺旋の流入角）

XROTORの `DESI` コマンドはこのアルゴリズムを内部で反復収束させ、最終的な $c(r)$ と $\beta(r)$ の分布を出力する。

### 3. オフデザイン性能解析

#### 3-1. 前進比（アドバンスレシオ）によるパラメータ化

$$
J = \frac{V}{n D} = \frac{V}{2\pi\,\Omega\,R}
$$

#### 3-2. 推力・トルク係数の特性曲線

XROTORの `OPER` モジュールにより $J$ をスイープすると、$(C_T, C_Q, \eta)$ の特性曲線が得られる。
本ツールでは発散した点を NaN として検出し、pandas の線形補間（`interpolate`）でギャップを埋めることで、連続した滑らかな特性曲線を保証する。
さらに効率 $\eta$ を物理的上限の $[0.0, 1.0]$ にクランプすることで、発散点由来の外れ値スパイクを除去している。

#### 3-3. V-RPM 効率マトリクス（並列計算）

飛行速度 $V$ と回転数 $RPM$ を $N\times N$ の格子点で全探索し、各格子点で XROTOR に `VELO`/`RPM` コマンドを入力して効率を取得する。  
計算は `n_workers` 個の XROTOR プロセスに分割して**並列実行**され、デフォルト 4 ワーカーで約 4 倍の高速化が得られる。

### 4. 構造特性（断面積・断面二次モーメント）の解析

#### 4-1. グリーンの定理による断面積の計算

$$
A = \frac{1}{2} \left|\sum_{i=0}^{N-1} (x_i y_{i+1} - x_{i+1} y_i)\right|
$$

#### 4-2. 重心まわりの断面二次モーメント

$$
I_{xx} = I_{xx}^{(0)} - A\,\bar{y}^2, \qquad I_{yy} = I_{yy}^{(0)} - A\,\bar{x}^2
$$

$I_{xx}$ はブレード面外方向（推力方向）の曲げ剛性に、$I_{yy}$ は面内方向（進行方向）の曲げ剛性に対応する。

### 5. 3D モデルの出力

設計済みブレード形状を以下のフォーマットで出力する。

- **PNG** (`prop_3d.png`): Matplotlib 静止画
- **STL** (`propeller.stl`): 3D プリント用メッシュ
- **HTML** (`propeller_3d.html`): Plotly インタラクティブ 3D ビューア

## 環境構築と実行方法

1. リポジトリをダウンロードし、`config.yaml` をエディタで設定して翼型 `.dat` を `airfoils/` に配置。
2. 依存パッケージをインストール:
   ```bash
   pip install -r requirements.txt
   ```
3. 実行:
   ```bash
   python main.py config.yaml
   ```
4. 設計済みファイルから部分再実行（Phase 3 以降のみ）:
   ```bash
   python main.py config.yaml --skip-phase 1,2
   ```
5. ログがターミナルへ流れ、成功すると `output/{プロペラ名}/` に全結果が生成される。

## 設定ファイル (config.yaml) リファレンス

```yaml
propeller:
  name: "sample"     # 出力フォルダ名（パス禁止文字 \ / : * ? " < > | は不可）
  B: 2               # ブレード数
  R: 1.5             # 半径 [m]
  Rhub: 0.1          # ハブ半径 [m]

design_point:
  V: 7.4             # 設計飛行速度 [m/s]
  RPM: 135           # 設計回転数 [rpm]
  target: thrust     # 最適化目標: "power" or "thrust"
  value: 24          # パワー[W] または推力[N] の値
  CL: 0.5            # 設計揚力係数

environment:
  rho: 1.225         # 空気密度 [kg/m^3]
  visc: 1.46e-5      # 動粘性係数 [m^2/s]

analysis:
  n_stations: 5      # 翼素数（動作確認: 5、実設計: 20〜30 推奨）
  ncrit: 9.0         # XFOIL 乱れ指標
  iter: 100          # 粘性計算最大イテレーション
  design_iters: 2    # 設計反復回数
  cleanup_temp: true # 完了後に temp_work/ を削除するか
  xfoil_timeout: 60  # XFOIL タイムアウト秒数
  alpha_seq:
    - "ASEQ 0 10 1.0"
    - "ASEQ 0 -5 -1.0"
  j_sweep:
    j_margin_low: 0.4
    j_margin_high: 0.5
    j_step: 0.05
  vrpm_sweep:
    v_margin: 3.0
    rpm_margin: 40.0
    n_points: 15      # 格子点数（合計 n_points^2 点を解析）
    n_workers: 4      # 並列 XROTOR プロセス数

airfoils:             # r/R の昇順でリスト
  - r_R: 0.1
    file: "airfoils/GEMINI.dat"
  - r_R: 1.0
    file: "airfoils/DAE51.dat"
```

## 出力ファイル一覧

| ファイル名 | 内容 |
|---|---|
| `designer.log` | 実行ログ（コンソール出力と同一）|
| `prop_result.txt` | 最終設計ファイル（XROTOR SAVE形式）|
| `prop_result_iter*.txt` | 反復中間設計ファイル |
| `xrotor_design.log` | XROTOR 設計フェーズの標準出力 |
| `xrotor_analysis.log` | XROTOR 性能解析フェーズの標準出力 |
| `vrpm_sweep.log` | V-RPM スイープの実行ログ |
| `prop_design.png` | 弦長・ねじり角分布グラフ |
| `prop_performance.png` | Ct-Cq-効率 vs J 特性曲線 |
| `vrpm_efficiency_map.png` | V-RPM 効率等高線マップ |
| `vrpm_3d.html` | V-RPM 効率 3D インタラクティブサーフェス |
| `structural_properties.csv` | 断面積・断面二次モーメントのテーブル |
| `structural_properties.png` | 断面構造特性グラフ |
| `prop_3d.png` | プロペラ 3D 静止画 |
| `propeller.stl` | STL メッシュ（3D プリント用）|
| `propeller_3d.html` | Plotly インタラクティブ 3D ビューア |
| `summary.json` | 設計サマリー（設計点・効率・完了フェーズ等）|

## ファイル構成

```
./
├── main.py                  # メインエントリポイント（argparse + --skip-phase 対応）
├── visualize_3d.py          # スタンドアロン 3D 可視化スクリプト
├── config.yaml              # 設計仕様の入力ファイル
├── requirements.txt
├── airfoils/                # 翼型 .dat ファイル格納ディレクトリ
│   ├── GEMINI.dat
│   └── DAE51.dat
├── core/
│   ├── design.py            # Phase 1 & 2: 翼型ブレンド・XROTOR設計
│   ├── analysis.py          # Phase 3: オフデザイン解析・V-RPMスイープ（並列）
│   ├── structure.py         # Phase 4: 断面構造特性の計算
│   ├── airfoil_utils.py     # 翼型ブレンドのユーティリティ
│   ├── xfoil_runner.py      # XFOILサブプロセス制御
│   └── xrotor_runner.py     # XROTORサブプロセス制御
├── utils/
│   ├── config.py            # 設定ファイル読み込み・バリデーション
│   └── visualize.py         # 全グラフ描画・3Dモデル出力
├── tests/
│   ├── test_config.py       # validate_config のユニットテスト
│   ├── test_structure.py    # calculate_section_properties のユニットテスト
│   └── test_airfoil_utils.py # normalize_airfoil / blend_airfoils のユニットテスト
└── output/
    └── {prop_name}/         # 全出力ファイルがここに集約される
```

## テスト実行

```bash
# pytest を使う場合
pip install pytest
pytest tests/ -v

# pytest なしで直接実行する場合
python tests/test_config.py
python tests/test_structure.py
python tests/test_airfoil_utils.py
```
