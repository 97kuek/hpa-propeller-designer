import os
import subprocess
import re

XROTOR_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "xrotor.exe")

def write_aero_file(filepath, r_R, polar_data, re_ref="1.000E+05", re_exp="-0.2000"):
    """
    XROTORのAERO->READで読み込めるAero Sectionファイル(.txt)を出力する
    """
    if not polar_data:
        raise ValueError("No polar data provided")

    # 極曲線データから代表値を計算/抽出
    cl_max = max([p['CL'] for p in polar_data])
    cl_min = min([p['CL'] for p in polar_data])
    cd_min = min([p['CD'] for p in polar_data])
    
    with open(filepath, 'w') as f:
        f.write(f"Aero data for r/R = {r_R:.3f}\n")
        
        # polar_data からαが0付近の線形領域から実際の揚力傾斜を計算
        linear_region = [p for p in polar_data if -2.0 <= p['alpha'] <= 4.0]
        if len(linear_region) >= 2:
            p1 = linear_region[0]
            p2 = linear_region[-1]
            if p2['alpha'] != p1['alpha']:
                dcl_da = (p2['CL'] - p1['CL']) / ((p2['alpha'] - p1['alpha']) * (3.14159 / 180.0))
            else:
                dcl_da = 0.1 * (180.0 / 3.14159)
        else:
            dcl_da = 0.1 * (180.0 / 3.14159) # デフォルト約2*pi
            
        f.write(f"0.0   {dcl_da:.4f}  {dcl_da*0.5:.4f}  {cl_max:.4f}  {cl_min:.4f}\n")
        
        # CDが最小となるデータポイントからCLを安全に取得
        cl_at_cdmin = min(polar_data, key=lambda x: x['CD'])['CL']
        
        # cdmin, clcdmin, dcd/dcl^2, mcrit
        f.write(f"{cd_min:.5f}   {cl_at_cdmin:.4f}   0.0100   0.8000\n")
        f.write(f"{re_ref}   {re_exp}\n")

def run_xrotor_design(config, aero_files_dict, output_file="prop_design.txt"):
    """
    設定ファイルと各Aeroファイルを用いてXROTOR DESIコマンドを操作する
    """
    
    # 絶対パスを保証
    output_path = os.path.abspath(output_file)
    
    if os.path.exists(output_path):
        os.remove(output_path)

    p_conf = config.get('propeller', {})
    d_conf = config.get('design_point', {})
    
    B = p_conf.get('B', 2)
    R = p_conf.get('R', 1.0)
    Rhub = p_conf.get('Rhub', 0.1)
    
    V = d_conf.get('V', 7.5)
    RPM = d_conf.get('RPM', 120)
    
    target_type = d_conf.get('target', 'power')
    target_value = d_conf.get('value', 200)
    CL = d_conf.get('CL', 0.5)

    # RPMからrps (n) を計算し、Advance ratio (J = V/(nD)) を求める
    rps = RPM / 60.0
    D = 2.0 * R
    J = V / (rps * D)
    
    commands = []
    
    # 1. AERO セクションの定義
    commands.append("AERO\n")
    sorted_r_R = sorted(aero_files_dict.keys())
    for idx, r_r in enumerate(sorted_r_R):
        # パスをXROTOR実行ディレクトリ(cwd)からの相対パスとし、記号を統一
        aero_rel_path = os.path.relpath(aero_files_dict[r_r]).replace('\\', '/')
        if idx == 0:
            # 最初の1つ目はデフォルト(idx=1)を上書き(EDIT->READ)
            commands.append("EDIT\n1\nREAD\n")
            commands.append(f"{aero_rel_path}\n")
            commands.append(f"{r_r:.3f}\n") # r/Rを入力
            commands.append("\n") # EDITメニューを抜ける
        else:
            # 2つ目以降はNEWで作成(EDITメニューに自動移行)してからREAD
            commands.append("NEW\n")
            commands.append("READ\n")
            commands.append(f"{aero_rel_path}\n")
            commands.append(f"{r_r:.3f}\n") # r/Rを入力
            commands.append("\n") # EDITメニューを抜ける
            
    commands.append("\n") # AEROメニュー全体を抜けてトップへ戻る
    
    # 2. ジオメトリ制約 (Hub等)の設定
    # ここでは仮の最小限の操作（必要に応じてNACEやARBIを用いる）
    
    # 3. 設計メニュー
    commands.append("DESI\n")
    commands.append("EDIT\n") # EDITメニューに入り全パラメータを指定
    
    commands.append(f"B {B}\n") # ブレード数
    commands.append(f"RT {R}\n") # 半径
    commands.append(f"RH {Rhub}\n") # ハブ半径
    commands.append(f"RW {Rhub}\n") # ハブウェイク変位ボディ半径(ハブと同じとする)
    commands.append(f"V {V}\n") # フライト速度
    
    if target_type.lower() == 'power':
        commands.append(f"R {RPM}\n") # RPMを指定
        commands.append(f"P {target_value}\n") # パワーを指定(ここで計算が走る場合がある)
    else:
        commands.append(f"R {RPM}\n")
        commands.append(f"T {target_value}\n") # 推力を指定
        
    commands.append(f"CC {CL}\n") # 一定の設計揚力係数を指定

    commands.append("\n") # CC入力後のエンター
    commands.append("\n") # EDITプロンプトから抜けて DESIトップへ
    commands.append("\n") # DESIメニューから抜けて トップメニューへ
    
    # 結果の保存 (トップメニューでSAVE実行)
    # XROTORにはcwdからの相対パスまたは絶対パスを渡す
    cwd = os.path.dirname(os.path.abspath(__file__))
    out_rel = os.path.relpath(output_path, cwd).replace('\\', '/')
    commands.append("SAVE\n")
    commands.append(f"{out_rel}\n")
    commands.append("Y\n") # もし上書き確認が出た場合のため
    commands.append("\n") # 念のため次のプロンプトに戻る
    commands.append("QUIT\n")
    
    try:
        process = subprocess.Popen(
            [XROTOR_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(input="".join(commands), timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            print("Error: XROTOR process timed out.")
            return False
        
        xrotor_log_path = os.path.join(cwd, "..", "xrotor.log")
        with open(xrotor_log_path, "w") as f:
            f.write(stdout)
            
        if not os.path.exists(output_path):
            print("Warning: XROTOR design output failed. output_path does not exist.")
            print(stdout)
            return False
            
    except Exception as e:
        print(f"Error running XROTOR: {e}")
        return False
        
    return True

def parse_xrotor_output(filepath):
    """
    XROTORがSAVEで吐き出した固定ピッチプロペラの定義ファイルを読み取り、
    r/R, c/R, beta(deg) のリストを返す
    """
    if not os.path.exists(filepath):
        return None
        
    data = []
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    data_start = False
    for line in lines:
        if "ERROR" in line or "Error" in line:
            # XROTOR内でエラーが発生している場合
            print(f"XROTOR Output Error: {line.strip()}")
            return None
            
        if "r/R" in line and "C/R" in line and ("Beta0deg" in line or "beta" in line.lower()):
            data_start = True
            continue
        if "------" in line or "! " in line:
            continue
            
        if data_start:
            # Fortran出力は列がくっつく場合があるので、単純なsplit()だとうまくいかない場合がある
            # 幸い今回の出力はスペース区切りが維持されている。
            parts = line.split()
            if len(parts) >= 3:
                try:
                    r_R = float(parts[0].replace('D', 'E'))
                    c_R = float(parts[1].replace('D', 'E'))
                    beta = float(parts[2].replace('D', 'E'))
                    data.append({'r/R': r_R, 'c/R': c_R, 'beta': beta})
                except ValueError:
                    # データの終わり
                    break
    
    return data
