import os
import paramiko
from pathlib import Path

# 默认将密钥存储在项目 data 目录下
SSH_KEY_DIR = Path("data/ssh_keys")
PRIVATE_KEY_PATH = SSH_KEY_DIR / "id_rsa"


def get_or_create_system_ssh_key() -> tuple[str, str]:
    """
    获取或创建系统的全局 SSH 密钥对。
    返回: (私钥绝对路径, 公钥字符串)
    """
    SSH_KEY_DIR.mkdir(parents=True, exist_ok=True)

    priv_path_str = str(PRIVATE_KEY_PATH.absolute())

    if not PRIVATE_KEY_PATH.exists():
        # 生成 2048 位 RSA 密钥
        key = paramiko.RSAKey.generate(2048)
        key.write_private_key_file(priv_path_str)

    # 读取私钥并导出公钥
    key = paramiko.RSAKey.from_private_key_file(priv_path_str)
    public_key_str = f"{key.get_name()} {key.get_base64()} DeepAgents_System_Key"

    return priv_path_str, public_key_str
