import os
from app.settings import settings  # 导入配置，获取项目根目录

def ensure_directory(path: str):
    """确保目录存在，不存在则递归创建（支持多层目录）"""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def get_relative_path(absolute_path: str) -> str:
    """
    将绝对路径转换为相对于项目根目录的相对路径（适配路由返回需求）
    :param absolute_path: 文件的绝对路径
    :return: 相对于项目根目录的相对路径
    """
    try:
        # 用项目根目录（settings.ROOT_DIR）作为基准，计算相对路径
        return os.path.relpath(absolute_path, settings.ROOT_DIR)
    except ValueError:
        # 若路径不在项目根目录下（异常情况），返回原绝对路径
        return absolute_path
    except Exception as e:
        print(f"路径转换出错: {str(e)}")
        return absolute_path
