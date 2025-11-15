#!/usr/bin/env python3
"""
IoTDB PR智能助手 - 命令行界面启动脚本
提供简化的命令行入口点
"""

import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from chat_application import main
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保所有依赖文件都在同一目录下")
    sys.exit(1)

if __name__ == "__main__":
    main()
