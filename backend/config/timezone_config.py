import os
import pytz
from datetime import datetime

# --- 时区配置 ---
# 从环境变量读取，默认为 "Asia/Shanghai" (东八区)
# 你可以在 .env 文件或启动命令中设置: export APP_TIMEZONE="America/New_York"
APP_TIMEZONE_NAME = os.getenv("APP_TIMEZONE", "Asia/Shanghai")

# 初始化时区对象
try:
    TZ = pytz.timezone(APP_TIMEZONE_NAME)
except pytz.UnknownTimeZoneError:
    # 如果环境变量配置的时区无效，回退到默认值，防止程序崩溃
    print(f"Warning: Unknown timezone '{APP_TIMEZONE_NAME}', falling back to 'Asia/Shanghai'.")
    TZ = pytz.timezone("Asia/Shanghai")

def get_configured_now():
    """
    获取当前配置时区的时间。
    所有数据库写入和业务逻辑计算都应使用此函数，以确保时区统一。
    """
    return datetime.now(TZ)
