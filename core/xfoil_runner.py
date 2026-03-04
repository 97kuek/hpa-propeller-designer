import os
import subprocess
import logging

XFOIL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "xfoil.exe")

def run_xfoil_polar(airfoil_file, reynolds, mach, ncrit=9.0, max_iter=200,
                    output_polar_file="polar.txt", alpha_seq=None, timeout=60):
    """
    XFOILを実行して、指定されたレイノルズ数における極曲線(Polar)データを生成する。

    Parameters
    ----------
    timeout : int
        XFOIL プロセスのタイムアウト秒数（デフォルト 60 秒）。
        config.yaml の analysis.xfoil_timeout から取得して渡す。
    """
    if alpha_seq is None:
        alpha_seq = ["ASEQ 0 10 0.5", "ASEQ 0 -5 -0.5"]
        
    polar_path = os.path.abspath(output_polar_file)
    if os.path.exists(polar_path):
        try:
            os.remove(polar_path)
        except OSError:
            pass

    # 実行ディレクトリを翼型ファイルのある場所に設定
    cwd = os.path.dirname(os.path.abspath(airfoil_file))
    base_airfoil = os.path.basename(airfoil_file)
    
    # PACCで指定する出力ファイル名は実行ディレクトリからの相対パスとする
    base_polar = os.path.relpath(polar_path, cwd).replace('\\', '/')

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
    ] + [seq + "\n" for seq in alpha_seq] + [
        "PACC\n",
        "\n",
        "QUIT\n"
    ]

    try:
        process = subprocess.Popen(
            [XFOIL_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(input="".join(commands), timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            logging.error(f"XFOIL process timed out for {base_airfoil}")
            return False
        
        if not os.path.exists(polar_path):
            logging.warning(f"XFOIL polar generation failed for {base_airfoil} at Re={reynolds}")
            return False
            
    except Exception as e:
        logging.error(f"Error running XFOIL: {e}")
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
        
    # XFOILのPolarファイルのデータ部分は区切り線 "------" の次の行から始まる
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
