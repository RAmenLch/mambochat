# backend/models/base_model.py

import uuid
from sqlalchemy.orm import declarative_base

# 声明式模型基类
Base = declarative_base()

def generate_uuid():
    """生成一个UUID字符串"""
    return str(uuid.uuid4())

