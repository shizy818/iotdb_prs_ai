#!/usr/bin/env python3
"""
聊天应用主程序 - IoTDB PR智能助手
基于向量数据库的智能对话系统，帮助用户搜索和分析PR信息
"""

import sys
import signal
import argparse
from pathlib import Path
from typing import Optional

try:
    from prompt_toolkit import prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.completion import WordCompleter

    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False
    print("⚠️  建议安装prompt_toolkit以获得更好的命令行体验: pip install prompt_toolkit")

from chat_vector_tool import VectorDBTool
from chat_message_handler import ChatMessageHandler
from logger_config import setup_logger

logger = setup_logger(__name__)


class ChatApplication:
    """聊天应用主类"""

    def __init__(self, persist_directory: str = "./chroma_db", debug: bool = False):
        """
        初始化聊天应用

        Args:
            persist_directory: 向量数据库持久化目录
            debug: 是否启用调试模式
        """
        self.persist_directory = persist_directory
        self.debug = debug
        self.vector_tool: Optional[VectorDBTool] = None
        self.message_handler: Optional[ChatMessageHandler] = None
        self.is_running = False

        # 设置prompt_toolkit支持（如果可用）
        self._setup_prompt_toolkit()

        # 设置信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("聊天应用初始化完成")

    def _setup_prompt_toolkit(self) -> None:
        """设置prompt_toolkit支持以改善命令行体验"""
        if not PROMPT_TOOLKIT_AVAILABLE:
            logger.debug("prompt_toolkit不可用，使用基础input()")
            return

        try:
            import os

            # 历史记录文件
            history_file = os.path.expanduser("~/.iotdb_chat_history")
            self.history = FileHistory(history_file)

            # 命令补全
            commands = [
                "help",
                "quit",
                "exit",
                "search",
                "pr",
                "stats",
                "keywords",
                "get_conversation_summary",
            ]
            self.completer = WordCompleter(commands, ignore_case=True)

            logger.debug("prompt_toolkit设置完成，支持历史记录和Tab补全")

        except Exception as e:
            logger.debug(f"prompt_toolkit设置失败: {e}")
            self.history = None
            self.completer = None

    def initialize(self) -> bool:
        """
        初始化应用组件

        Returns:
            是否初始化成功
        """
        try:
            print("🚀 正在启动IoTDB PR智能助手...")

            # 初始化向量数据库工具
            print("📚 初始化向量数据库...")
            self.vector_tool = VectorDBTool(self.persist_directory)

            # 初始化消息处理器
            print("🤖 初始化消息处理器...")
            self.message_handler = ChatMessageHandler(self.vector_tool)

            # 获取数据库统计信息
            stats = self.vector_tool.get_database_stats()
            if stats["success"]:
                total_docs = stats["stats"].get("total_documents", 0)
                print(f"✅ 初始化完成！数据库中有 {total_docs} 个PR分析记录")
            else:
                print("⚠️  初始化完成，但无法获取数据库统计信息")

            return True

        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            logger.error(f"应用初始化失败: {e}")
            return False

    def run(self) -> None:
        """运行聊天应用主循环"""
        if not self.initialize():
            return

        self.is_running = True
        self._print_welcome()

        try:
            while self.is_running:
                # 获取用户输入
                user_input = self._get_user_input()

                if not user_input:
                    continue

                # 处理消息
                response = self.message_handler.process_message(user_input)

                # 显示回复
                self._display_response(response)

                # 检查是否需要退出
                if response.get("intent") == "quit":
                    break

        except KeyboardInterrupt:
            print("\n👋 用户中断，正在退出...")
        except Exception as e:
            print(f"❌ 运行时错误: {e}")
            if self.debug:
                logger.exception("运行时异常详情")
        finally:
            self._cleanup()

    def _get_user_input(self) -> str:
        """获取用户输入"""
        try:
            if PROMPT_TOOLKIT_AVAILABLE and hasattr(self, "history"):
                user_input = prompt(
                    "\n💬 您: ",
                    history=self.history,
                    completer=self.completer,
                    complete_while_typing=True,
                ).strip()
            else:
                user_input = input("\n💬 您: ").strip()
            return user_input
        except (EOFError, KeyboardInterrupt):
            return "quit"

    def _display_response(self, response: dict) -> None:
        """
        显示助手回复

        Args:
            response: 响应对象
        """
        print(f"\n🤖 助手: {response['message']}")

        if self.debug and response.get("metadata"):
            print(f"\n🔧 调试信息: {response['metadata']}")

    def _print_welcome(self) -> None:
        """打印欢迎信息"""
        welcome_message = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                     🤖 IoTDB PR智能助手                                      ║
║                                                                              ║
║  基于向量数据库的智能对话系统，帮助您搜索和分析IoTDB项目PR信息               ║
║                                                                              ║
║  🎯 主要功能：                                                               ║
║    • 智能搜索PR问题和解决方案                                                 ║
║    • 查看特定PR的详细分析                                                     ║
║    • 关键词检索相关内容                                                       ║
║    • 数据库统计信息查看                                                       ║
║    • 支持自然语言对话                                                         ║
║                                                                              ║
║  💡 使用提示：                                                               ║
║    • 输入 "help" 查看所有可用命令                                             ║
║    • 输入 "quit" 或按 Ctrl+C 退出                                            ║
║    • 支持自然语言提问，例如："搜索JDBC配置相关的问题"                          ║
║    • 使用方向键浏览历史命令                                                   ║
║    • 使用Tab键自动补全命令                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

        """
        print(welcome_message)

    def _signal_handler(self, signum, frame) -> None:
        """信号处理器"""
        print(f"\n📡 收到信号 {signum}，正在安全退出...")
        self.is_running = False
        # 立即退出程序，避免在 input() 处阻塞
        import sys

        sys.exit(0)

    def _cleanup(self) -> None:
        """清理资源"""
        try:
            # 显示会话统计
            if self.message_handler:
                summary = self.message_handler.get_conversation_summary()
                print(f"\n📊 会话统计: {summary['total_messages']} 条消息")
                print(f"   - 用户消息: {summary['user_messages']} 条")
                print(f"   - 助手回复: {summary['assistant_messages']} 条")
                print(f"   - 会话时长: {summary['duration']}")

            print("🧹 清理完成，再见！")

        except Exception as e:
            print(f"⚠️  清理时出现错误: {e}")

    def run_batch_mode(self, query: str) -> None:
        """
        批处理模式 - 执行单个查询并退出

        Args:
            query: 要执行的查询
        """
        if not self.initialize():
            return

        print(f"🔍 执行查询: {query}")

        try:
            response = self.message_handler.process_message(query)
            print(f"\n🤖 回复: {response['message']}")

            if self.debug and response.get("metadata"):
                print(f"\n🔧 调试信息: {response['metadata']}")

        except Exception as e:
            print(f"❌ 查询执行失败: {e}")
            if self.debug:
                logger.exception("查询异常详情")
        finally:
            self._cleanup()

    def run_interactive_mode(self) -> None:
        """交互模式 - 标准聊天对话"""
        self.run()


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="IoTDB PR智能助手 - 基于向量数据库的智能对话系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s                          # 启动交互模式
  %(prog)s -q "JDBC配置问题"         # 批处理模式，执行单个查询
  %(prog)s --debug                  # 启用调试模式
  %(prog)s -d /path/to/db           # 指定数据库目录

支持的命令:
  help                              # 显示帮助信息
  search <查询内容>                  # 搜索相关问题
  pr <PR编号>                      # 获取PR详情
  keywords <关键词1,关键词2>        # 关键词搜索
  stats                             # 数据库统计
  quit                              # 退出应用
        """,
    )

    parser.add_argument(
        "-q", "--query", type=str, help="批处理模式：执行单个查询并退出"
    )

    parser.add_argument(
        "-d",
        "--database",
        type=str,
        default="./chroma_db",
        help="向量数据库存储目录 (默认: ./chroma_db)",
    )

    parser.add_argument(
        "--debug", action="store_true", help="启用调试模式，显示详细错误信息"
    )

    parser.add_argument(
        "--version", action="version", version="IoTDB PR智能助手 v1.0.0"
    )

    return parser


def main() -> None:
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 创建聊天应用实例
    app = ChatApplication(persist_directory=args.database, debug=args.debug)

    try:
        if args.query:
            # 批处理模式
            app.run_batch_mode(args.query)
        else:
            # 交互模式
            app.run_interactive_mode()

    except Exception as e:
        print(f"❌ 应用启动失败: {e}")
        if args.debug:
            logger.exception("应用启动异常详情")
        sys.exit(1)


if __name__ == "__main__":
    main()
