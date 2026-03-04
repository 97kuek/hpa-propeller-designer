import yaml
import logging

def load_config(filepath):
    """YAML設定ファイルを読み込む"""
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            logging.info(f"Loaded configuration from {filepath}")
            return config
    except Exception as e:
        logging.error(f"Failed to load config file '{filepath}': {e}")
        return None
