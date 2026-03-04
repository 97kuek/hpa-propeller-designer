"""
conftest.py
-----------
pytest が任意の場所から呼ばれても core/ utils/ を import できるよう
プロジェクトルートを sys.path に追加する。
"""
import sys
import os

# このファイルは tests/ に置かれているので、親 = プロジェクトルート
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
