import os
import subprocess
import shutil

XFOIL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "xfoil.exe")

def run_xfoil_polar(airfoil_file, reynolds, mach, ncrit=9.0, max_iter=200, output_polar_file="polar.txt", alpha_seq=None):
    """
    XFOILを実行して、指定されたレイノルズ数における極曲線(Polar)データを生成する。
    """
    if alpha_seq is None:
        alpha_seq = ["ASEQ 0 10 0.5", "ASEQ 0 -5 -0.5"]
        
    polar_path = os.path.abspath(output_polar_file)
    if os.path.exists(polar_path):
        try:
            os.remove(polar_path)
        except OSError:
            pass

    # 絶対パスをXFOILに渡すと長すぎる場合があるため、相対パスで運用することを推奨
    # 実行ディレクトリをファイルのある場所とする
    cwd = os.path.dirname(os.path.abspath(airfoil_file))
    base_airfoil = os.path.basename(airfoil_file)
    
    # PACCで指定する出力ファイル名は、実行ディレクトリ(cwd)からの相対・直接のファイル名とする
    base_polar = os.path.relpath(polar_path, cwd).replace('\\', '/')

    # コマンドの組み立て
    # PLOP G でグラフィックスを無効化（バックグラウンド実行のため）
    commands = [
        "PLOP\n",
        "G\n",
        "\n",
        f"LOAD {base_airfoil}\n",
        "PANE\n",
        "OPER\n",
        f"Visc {reynolds}\n",
        f"Mach {mach}\n",
        f"Iter {max_iter}\n",
        f"Vpar\n",
        f"N {ncrit}\n",
        "\n",
        "PACC\n",
        f"{base_polar}\n",
        "\n",  # ダンプファイルは不要
        # 迎角スイープ
    ] + [seq + "\n" for seq in alpha_seq] + [
        "PACC\n",
        "\n",
        "QUIT\n"
    ]

    try:
        # XFOILをサブプロセスとして起動
        # stdin=subprocess.PIPE で標準入力からコマンドを流し込む
        process = subprocess.Popen(
            [XFOIL_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True
        )
        
        # コマンド送信と実行完了待ち
        try:
            stdout, stderr = process.communicate(input="".join(commands), timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            print(f"Error: XFOIL process timed out for {base_airfoil}")
            return False
        
        # 実行成功したかの確認
        if not os.path.exists(polar_path):
            print(f"Warning: XFOIL polar generation failed for {base_airfoil} at Re={reynolds}")
            return False
            
    except Exception as e:
        print(f"Error running XFOIL: {e}")
        return False
        
    return True

def read_polar(polar_file):
    """
    XFOILが出力したPolarファイルを読み込み、辞書のリストとして返す。
    形式: [{'alpha': a, 'CL': cl, 'CD': cd, 'CDp': cdp, 'CM': cm, 'Top_Xtr': xtr, 'Bot_Xtr': btr}, ...]
    """
    if not os.path.exists(polar_file):
        return []

    data = []
    with open(polar_file, 'r') as f:
        lines = f.readlines()
        
    # XFOILのPolarファイルのデータ部分は通常13行目以降から始まる
    # 区切り線 "------" の次の行からデータとして読み取る
    data_start = False
    for line in lines:
        if "------" in line:
            data_start = True
            continue
            
        if data_start:
            parts = line.split()
            if len(parts) >= 7:
                try:
                    row = {
                        'alpha': float(parts[0]),
                        'CL': float(parts[1]),
                        'CD': float(parts[2]),
                        'CDp': float(parts[3]),
                        'CM': float(parts[4]),
                        'Top_Xtr': float(parts[5]),
                        'Bot_Xtr': float(parts[6]),
                    }
                    data.append(row)
                except ValueError:
                    pass
    return data
