# HPA Propeller Design Tool

XFOIL と XROTOR を利用して、人力飛行機 (HPA) 用プロペラの設計・空力計算・構造解析・3Dモデル出力までを一貫して全自動で行うPythonベースの強力なCUI設計ツールです。

## 🌟 主な機能
1. **翼型の自動ブレンド (XFOIL連携)**: 翼根側と翼端側の指定した翼型（.dat）を半径位置 ($r/R$) に応じて滑らかにブレンドし、各ステーションごとの空力極力線（Polarデータ）をXFOILで自動生成します。
2. **設計の最適化 (XROTOR連携)**: XROTORの `DESI` モジュールを使用し、設計点（Velocity, RPM）に対して最適な弦長 ($c/R$) とピッチ角 ($\beta$) の分布を生成します。
3. **オフデザイン性能評価 (J-マップ計算)**: 設計点以外の様々なアドバンスレシオ ($J$) における推力係数($C_T$)、トルク係数($C_Q$)、推進効率($\eta$)の性能曲線を算出します。XROTORが収束しなかった極端な領域もPython側で線形補間し、途切れない堅牢なグラフを描画します。
4. **構造特性の可視化**: 生成された全翼型の断面積(Area)、断面二次モーメント($I_{xx}, I_{yy}$)を解析し、構造設計に必要な強度分布の指標とグラフを出力します。
5. **高度なV-RPM等高線マップ**: 飛行速度($V$)とプロペラ回転数($RPM$)をマトリクス状にスウィープ計算（15x15の225パターン）させ、どこが最も効率的か地形図のように見せる等高線マップおよびインタラクティブな3DSurfaceグラフを出力します。
6. **3Dモデル出力 (.stl & .html)**: 設計されたプロペラのフル3Dモデルを、CAD/3Dプリンタ向けにSTLファイル形式で出力するほか、ブラウザでぐりぐり回して確認できるPlotly形式のインタラクティブ3D HTMLファイルも出力します。

## 🚀 アルゴリズムフローチャート

本プロジェクトの内部では、`main.py` を起点として以下のようなフローで設計データをバケツリレーしています。

```mermaid
graph TD
    A[main.py: 実行開始] --> B(config.yaml 読み込み)
    
    subgraph PHASE 1: 空気力学データの生成
        B --> C[core/design.py: design_propeller]
        C --> D[core/airfoil_utils.py: 翼型ブレンド]
        D --> E{XFOIL Runner}
        E -- Re, Mach, Alpha sweep --> F[temp_work/ 極力線Polarデータ蓄積]
    end
    
    subgraph PHASE 2: プロペラ形状の最適設計
        F --> G{XROTOR Runner: DESI}
        G -- V, RPM, R, B --> H[temp_work/ prop_result.txt 出力]
        H -- 弦長, ピッチ分布パース --> I[Geometry Data取得]
    end
    
    subgraph PHASE 3: 性能評価と可視化
        H --> J{XROTOR Runner: OPER}
        J -- Advance Ratio J スイープ --> K[Performance Data 取得 & NaN補間]
        J -- V, RPM マトリクススイープ --> L[V-RPM Efficiency Grid 取得]
        I --> M[core/structure.py: 断面積, Ixx, Iyy 計算]
    end
    
    subgraph PHASE 4: 結果の出力 (utils/visualize.py)
        I -->|matplotlib| O[prop_design.png]
        K -->|matplotlib| P[prop_performance.png]
        L -->|matplotlib contourf| Q[vrpm_efficiency_map.png]
        L -->|plotly Surface| R[vrpm_3d.html]
        M -->|matplotlib| S[structural_properties.png]
        M --> T[structural_properties.csv]
        I -->|numpy-stl| U[propeller.stl]
    end

    O --> Z((出力ディレクトリ: output/対象名/ に一式保存))
    P --> Z
    Q --> Z
    R --> Z
    S --> Z
    T --> Z
    U --> Z
```

## ⚙️ 実行方法

1. リポジトリ直下の `config.yaml` をテキストエディタで開き、プロペラの設計仕様（半径、ブレード数、設計速度、設計RPMなど）を入力します。使用する翼型の `.dat` ファイルは `airfoils/` ディレクトリの中に配置して指定してください。
2. 必要なPythonモジュールをインストールします。
   ```bash
   pip install -r requirements.txt
   ```
3. プログラムを実行します。引数に設定ファイルを指定してください。
   ```bash
   python main.py config.yaml
   ```
4. ログがターミナルへ流れ、XFOILやXROTORがバックグラウンドで自動的に起動と計算を繰り返します。
5. 成功すると、`output/{プロペラ名}/` のディレクトリ内部にすべての解析結果画像・CSVデータ・STL・HTMLファイルが生成されます。
