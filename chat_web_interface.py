#!/usr/bin/env python3
"""
IoTDB PR智能助手 - Web界面
基于Flask的Web聊天界面
"""

import json
from typing import Dict, Any
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS

from chat_vector_tool import VectorDBTool
from chat_message_handler import ChatMessageHandler
from logger_config import setup_logger

logger = setup_logger(__name__)


class ChatWebInterface:
    """Web界面聊天应用"""

    def __init__(self, persist_directory: str = "./chroma_db"):
        """
        初始化Web界面

        Args:
            persist_directory: 向量数据库持久化目录
        """
        self.app = Flask(__name__)
        CORS(self.app)  # 启用跨域支持

        # 初始化聊天组件
        self.vector_tool = VectorDBTool(persist_directory)
        self.message_handler = ChatMessageHandler(self.vector_tool)

        # 注册路由
        self._register_routes()

        logger.info("Web界面初始化完成")

    def _register_routes(self):
        """注册Flask路由"""

        @self.app.route("/")
        def index():
            """主页"""
            return render_template_string(self._get_html_template())

        @self.app.route("/chat", methods=["POST"])
        def chat():
            """处理聊天消息"""
            try:
                data = request.get_json()
                if not data or "message" not in data:
                    return jsonify({"error": "缺少消息内容"}), 400

                message = data["message"]
                response = self.message_handler.process_message(message)

                return jsonify(response)

            except Exception as e:
                logger.error(f"处理聊天消息时出错: {e}")
                return jsonify({"error": "服务器内部错误", "details": str(e)}), 500

        @self.app.route("/stats")
        def stats():
            """获取数据库统计信息"""
            try:
                result = self.vector_tool.get_database_stats()
                return jsonify(result)
            except Exception as e:
                logger.error(f"获取统计信息时出错: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/health")
        def health():
            """健康检查接口"""
            return jsonify({"status": "healthy", "service": "IoTDB PR智能助手"})

    def _get_html_template(self) -> str:
        """获取HTML模板"""
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IoTDB PR智能助手</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .chat-container {
            width: 90%;
            max-width: 800px;
            height: 80vh;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
            font-size: 1.2em;
            font-weight: bold;
        }

        .chat-messages {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            background-color: #f9f9f9;
        }

        .message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 18px;
            max-width: 70%;
            word-wrap: break-word;
            line-height: 1.4;
        }

        .user-message {
            background: #007bff;
            color: white;
            margin-left: auto;
            text-align: right;
        }

        .assistant-message {
            background: #e9ecef;
            color: #333;
            margin-right: auto;
        }

        .chat-input {
            padding: 20px;
            border-top: 1px solid #ddd;
            display: flex;
            gap: 10px;
        }

        .chat-input input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #ddd;
            border-radius: 25px;
            outline: none;
            font-size: 1em;
            transition: border-color 0.3s;
        }

        .chat-input input:focus {
            border-color: #007bff;
        }

        .chat-input button {
            padding: 12px 24px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1em;
            transition: background-color 0.3s;
        }

        .chat-input button:hover {
            background: #0056b3;
        }

        .chat-input button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        .typing-indicator {
            display: none;
            color: #666;
            font-style: italic;
            padding: 10px;
        }

        .help-panel {
            background: #f0f8ff;
            border-left: 4px solid #007bff;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 5px;
        }

        .help-panel h3 {
            color: #007bff;
            margin-bottom: 10px;
        }

        .help-panel ul {
            margin-left: 20px;
        }

        @media (max-width: 768px) {
            .chat-container {
                width: 95%;
                height: 90vh;
            }

            .message {
                max-width: 85%;
            }
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            🤖 IoTDB PR智能助手 - 基于向量数据库的智能对话系统
        </div>

        <div class="chat-messages" id="chatMessages">
            <div class="help-panel">
                <h3>💡 使用指南</h3>
                <ul>
                    <li><strong>搜索问题：</strong> "搜索JDBC配置问题"</li>
                    <li><strong>查看PR：</strong> "pr 16487"</li>
                    <li><strong>关键词搜索：</strong> "keywords Maven,构建,错误"</li>
                    <li><strong>数据库统计：</strong> "stats"</li>
                    <li><strong>查看帮助：</strong> "help"</li>
                </ul>
                <p>🎯 支持自然语言对话，您可以随时用任何方式提问！</p>
            </div>
        </div>

        <div class="typing-indicator" id="typingIndicator">
            🤖 正在思考中...
        </div>

        <div class="chat-input">
            <input type="text" id="messageInput" placeholder="请输入您的问题..." autocomplete="off">
            <button id="sendButton" onclick="sendMessage()">发送</button>
        </div>
    </div>

    <script>
        const chatMessages = document.getElementById('chatMessages');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const typingIndicator = document.getElementById('typingIndicator');

        // 自动调整聊天消息区域高度
        function scrollToBottom() {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        // 添加消息到聊天界面
        function addMessage(content, isUser = false) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user-message' : 'assistant-message'}`;
            messageDiv.innerHTML = content.replace(/\n/g, '<br>');
            chatMessages.appendChild(messageDiv);
            scrollToBottom();
        }

        // 显示/隐藏打字指示器
        function showTyping(show) {
            typingIndicator.style.display = show ? 'block' : 'none';
            if (show) {
                scrollToBottom();
            }
        }

        // 发送消息
        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;

            // 禁用输入和发送按钮
            messageInput.disabled = true;
            sendButton.disabled = true;

            // 添加用户消息
            addMessage(message, true);
            messageInput.value = '';

            // 显示打字指示器
            showTyping(true);

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message })
                });

                const data = await response.json();

                if (response.ok) {
                    addMessage(data.message);
                } else {
                    addMessage(`❌ 错误: ${data.error || '请求失败'}`);
                }
            } catch (error) {
                addMessage(`❌ 网络错误: ${error.message}`);
            } finally {
                // 恢复输入和发送按钮
                messageInput.disabled = false;
                sendButton.disabled = false;
                showTyping(false);
                messageInput.focus();
            }
        }

        // 处理回车键
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });

        // 页面加载完成后聚焦输入框
        window.addEventListener('load', function() {
            messageInput.focus();
        });
    </script>
</body>
</html>
        """

    def run(self, host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
        """
        运行Web应用

        Args:
            host: 主机地址
            port: 端口号
            debug: 是否启用调试模式
        """
        logger.info(f"启动Web界面服务: http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="IoTDB PR智能助手 - Web界面")
    parser.add_argument(
        "--host", default="0.0.0.0", help="服务器主机地址 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="服务器端口 (默认: 5000)"
    )
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument(
        "--database", default="./chroma_db", help="向量数据库目录 (默认: ./chroma_db)"
    )

    args = parser.parse_args()

    try:
        # 创建并启动Web界面
        web_interface = ChatWebInterface(args.database)
        print(f"🌐 启动IoTDB PR智能助手Web界面")
        print(f"📍 访问地址: http://{args.host}:{args.port}")
        print(f"📁 数据库目录: {args.database}")
        print("按 Ctrl+C 停止服务")

        web_interface.run(host=args.host, port=args.port, debug=args.debug)

    except Exception as e:
        print(f"❌ 启动失败: {e}")
        logger.exception("Web服务启动异常")
        return 1

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
