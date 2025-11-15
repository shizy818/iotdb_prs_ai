#!/usr/bin/env python3
"""
聊天消息处理器 - 理解用户意图并调用相应的工具
负责解析用户输入，识别意图，并生成合适的回复
"""

import re
import json
from typing import Dict, List, Optional, Tuple, Any

from chat_vector_tool import VectorDBTool
from logger_config import setup_logger

logger = setup_logger(__name__)


class ChatMessageHandler:
    """聊天消息处理器，负责理解用户意图和生成回复"""

    def __init__(self, vector_tool: VectorDBTool):
        """
        初始化消息处理器

        Args:
            vector_tool: 向量数据库工具实例
        """
        self.vector_tool = vector_tool
        self.conversation_history = []

        # 意图模式定义
        self.intent_patterns = {
            "search": [
                r"搜索(.+)",
                r"查找(.+)",
                r"search\s+(.+)",
                r"找.*?问题",
                r"有没有.*?相关",
                r"关于(.+)",
            ],
            "get_pr": [
                r"pr\s*(\d+)",
                r"PR\s*(\d+)",
                r"pull\s+request\s+(\d+)",
                r"获取.*?(\d+)",
                r"查看.*?(\d+)",
            ],
            "keywords": [
                r"关键词\s*(.+)",
                r"keywords?\s*(.+)",
                r"包含(.+?)的关键词",
                r"用关键词(.+?)搜索",
            ],
            "stats": [
                r"统计",
                r"stats?",
                r"数据库信息",
                r"有多少.*?PR",
                r"总数",
            ],
            "help": [
                r"帮助",
                r"help",
                r"怎么用",
                r"命令",
                r"功能",
            ],
            "quit": [
                r"退出",
                r"quit",
                r"bye",
                r"再见",
                r"结束",
            ],
        }

        logger.info("消息处理器已初始化")

    def process_message(self, message: str) -> Dict[str, Any]:
        """
        处理用户消息

        Args:
            message: 用户输入的消息

        Returns:
            包含回复和元数据的字典
        """
        try:
            message = message.strip()
            if not message:
                return self._create_response("", "empty_message", "请输入您的问题")

            # 记录到对话历史
            self.conversation_history.append(
                {
                    "type": "user",
                    "message": message,
                    "timestamp": self._get_current_time(),
                }
            )

            # 识别用户意图
            intent, entities = self._recognize_intent(message)

            # 根据意图执行相应操作
            if intent == "search":
                response = self._handle_search_intent(entities)
            elif intent == "get_pr":
                response = self._handle_get_pr_intent(entities)
            elif intent == "keywords":
                response = self._handle_keywords_intent(entities)
            elif intent == "stats":
                response = self._handle_stats_intent()
            elif intent == "help":
                response = self._handle_help_intent()
            elif intent == "quit":
                response = self._handle_quit_intent()
            else:
                response = self._handle_fallback_intent(message)

            # 记录回复到对话历史
            self.conversation_history.append(
                {
                    "type": "assistant",
                    "message": response["message"],
                    "intent": intent,
                    "timestamp": self._get_current_time(),
                }
            )

            return response

        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            return self._create_response(
                "error", "system_error", f"处理消息时出现错误: {str(e)}"
            )

    def _recognize_intent(self, message: str) -> Tuple[str, Dict]:
        """
        识别用户意图

        Args:
            message: 用户消息

        Returns:
            (意图名称, 实体字典)
        """
        message_lower = message.lower()

        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, message_lower, re.IGNORECASE)
                if match:
                    entities = {}
                    if match.groups():
                        # 根据不同的意图提取实体
                        if intent == "search":
                            entities["query"] = match.group(1).strip()
                        elif intent == "get_pr":
                            entities["pr_number"] = int(match.group(1))
                        elif intent == "keywords":
                            entities["keywords"] = [
                                k.strip() for k in match.group(1).split(",")
                            ]
                        elif intent == "add":
                            entities["pr_number"] = int(match.group(1))
                            entities["title"] = match.group(2).strip()
                            entities["analysis"] = match.group(3).strip()
                        else:
                            entities = {"raw_match": match.group(0)}

                    return intent, entities

        # 如果没有匹配到任何意图，返回fallback
        return "fallback", {"raw_message": message}

    def _handle_search_intent(self, entities: Dict) -> Dict[str, Any]:
        """处理搜索意图"""
        query = entities.get("query", "")
        if not query:
            return self._create_response(
                "search", "missing_query", "请提供要搜索的问题描述"
            )

        # 调用向量数据库工具搜索
        result = self.vector_tool.search_similar_issues(query)

        if result["success"] and result["results"]:
            # 格式化搜索结果
            response_message = f"🔍 搜索结果：{result['message']}\n\n"

            for i, item in enumerate(result["results"], 1):
                response_message += (
                    f"**{i}. PR #{item['pr_number']}: {item['pr_title']}**\n"
                )
                response_message += f"   📝 摘要：{item['summary']}\n"
                response_message += f"   📊 相关度：{item['relevance_score']:.2%}\n\n"

            response_message += "💡 提示：使用 'pr <编号>' 命令可以查看PR的详细信息"

            return self._create_response(
                "search",
                "success",
                response_message,
                {"query": query, "results_count": len(result["results"])},
            )
        else:
            return self._create_response(
                "search",
                "no_results",
                f"😔 未找到与「{query}」相关的问题\n\n💡 建议：\n- 尝试使用不同的关键词\n- 检查拼写是否正确\n- 使用更通用的描述",
            )

    def _handle_get_pr_intent(self, entities: Dict) -> Dict[str, Any]:
        """处理获取PR详情意图"""
        pr_number = entities.get("pr_number")
        if not pr_number:
            return self._create_response("get_pr", "missing_number", "请提供PR编号")

        # 调用向量数据库工具获取PR详情
        result = self.vector_tool.get_pr_details(pr_number)

        if result["success"]:
            response_message = f"📋 PR #{pr_number} 详细信息\n\n"
            response_message += f"**标题：** {result['pr_title']}\n\n"
            response_message += (
                f"**分析时间：** {result.get('analyzed_at', '未知')}\n\n"
            )
            response_message += f"**分析内容：**\n{result['content']}\n\n"

            if result.get("metadata"):
                response_message += f"**额外信息：**\n"
                for key, value in result["metadata"].items():
                    if key not in ["pr_number", "pr_title", "analyzed_at"]:
                        response_message += f"  - {key}: {value}\n"

            return self._create_response(
                "get_pr", "success", response_message, {"pr_number": pr_number}
            )
        else:
            return self._create_response(
                "get_pr",
                "not_found",
                f"❌ 未找到 PR #{pr_number} 的分析结果\n\n💡 可能的原因：\n- 该PR可能还未被分析\n- PR编号不正确\n- 数据库中没有相关记录",
            )

    def _handle_keywords_intent(self, entities: Dict) -> Dict[str, Any]:
        """处理关键词搜索意图"""
        keywords = entities.get("keywords", [])
        if not keywords:
            return self._create_response(
                "keywords", "missing_keywords", "请提供要搜索的关键词"
            )

        # 调用向量数据库工具进行关键词搜索
        result = self.vector_tool.search_by_keywords(keywords)

        if result["success"] and result["results"]:
            response_message = f"🏷️ 关键词搜索结果：{result['message']}\n\n"
            response_message += f"🔍 搜索关键词：{', '.join(keywords)}\n\n"

            for i, item in enumerate(result["results"][:5], 1):  # 限制显示前5个结果
                response_message += (
                    f"**{i}. PR #{item['pr_number']}: {item['pr_title']}**\n"
                )
                response_message += f"   📝 摘要：{item['summary']}\n"
                response_message += (
                    f"   🎯 关键词匹配：{item['keyword_matches']}/{len(keywords)}\n\n"
                )

            return self._create_response(
                "keywords",
                "success",
                response_message,
                {"keywords": keywords, "results_count": len(result["results"])},
            )
        else:
            return self._create_response(
                "keywords",
                "no_results",
                f"😔 未找到包含关键词「{', '.join(keywords)}」的相关内容",
            )

    def _handle_stats_intent(self) -> Dict[str, Any]:
        """处理统计信息意图"""
        # 获取数据库统计信息
        result = self.vector_tool.get_database_stats()

        if result["success"]:
            stats = result["stats"]
            response_message = "📊 数据库统计信息\n\n"
            response_message += (
                f"**总文档数：** {stats.get('total_documents', 0)} 个PR分析\n"
            )
            response_message += (
                f"**集合名称：** {stats.get('collection_name', 'N/A')}\n"
            )
            response_message += (
                f"**存储路径：** {stats.get('persist_directory', 'N/A')}\n\n"
            )
            response_message += "💡 数据库包含所有已分析的PR信息，支持智能搜索和问答"

            return self._create_response("stats", "success", response_message, stats)
        else:
            return self._create_response("stats", "error", "❌ 无法获取数据库统计信息")

    def _handle_help_intent(self) -> Dict[str, Any]:
        """处理帮助意图"""
        commands = self.vector_tool.get_available_commands()

        response_message = "🤖 IoTDB PR智能助手 - 使用帮助\n\n"
        response_message += "**可用命令：**\n\n"

        for cmd, desc in commands.items():
            response_message += f"• **{cmd}** - {desc}\n"

        response_message += "\n**使用示例：**\n"
        response_message += "• 搜索JDBC相关问题：`搜索 JDBC配置问题`\n"
        response_message += "• 查看PR详情：`pr 16487`\n"
        response_message += "• 关键词搜索：`keywords Maven,构建,错误`\n"
        response_message += "• 查看统计：`stats`\n\n"
        response_message += "💡 您可以直接用自然语言提问，系统会智能理解您的意图"

        return self._create_response("help", "success", response_message)

    def _handle_quit_intent(self) -> Dict[str, Any]:
        """处理退出意图"""
        response_message = "👋 感谢使用IoTDB PR智能助手！\n\n"
        response_message += (
            f"本次对话共进行了 {len(self.conversation_history)} 轮交互\n"
        )
        response_message += "如有需要，随时欢迎回来使用！"

        return self._create_response("quit", "success", response_message)

    def _handle_fallback_intent(self, message: str) -> Dict[str, Any]:
        """处理无法识别的意图"""
        # 尝试进行语义搜索
        result = self.vector_tool.search_similar_issues(message, max_results=3)

        if result["success"] and result["results"]:
            response_message = f"🤔 我理解您想了解「{message}」相关信息\n\n"
            response_message += f"**为您找到以下相关内容：**\n\n"

            for i, item in enumerate(result["results"], 1):
                response_message += (
                    f"**{i}. PR #{item['pr_number']}: {item['pr_title']}**\n"
                )
                response_message += f"   📝 {item['summary']}\n\n"

            response_message += "💡 如果这不是您想要的，请尝试使用更具体的描述或使用 `help` 查看所有可用命令"

            return self._create_response(
                "fallback", "semantic_search", response_message
            )
        else:
            response_message = f"😅 抱歉，我没有完全理解「{message}」\n\n"
            response_message += "**您可以尝试：**\n"
            response_message += "• 重新表述您的问题\n"
            response_message += "• 使用 `help` 查看所有可用命令\n"
            response_message += "• 直接搜索相关内容，如：`搜索 JDBC问题`\n\n"
            response_message += "💡 我支持自然语言对话，可以理解各种表述方式"

            return self._create_response("fallback", "not_understood", response_message)

    def _create_response(
        self, intent: str, status: str, message: str, metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        创建标准响应格式

        Args:
            intent: 意图类型
            status: 响应状态
            message: 响应消息
            metadata: 额外的元数据

        Returns:
            标准化的响应字典
        """
        response = {
            "intent": intent,
            "status": status,
            "message": message,
            "timestamp": self._get_current_time(),
        }

        if metadata:
            response["metadata"] = metadata

        return response

    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        获取对话摘要

        Returns:
            对话统计信息
        """
        if not self.conversation_history:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "intents_used": [],
                "duration": "0分钟",
            }

        user_messages = [
            msg for msg in self.conversation_history if msg["type"] == "user"
        ]
        assistant_messages = [
            msg for msg in self.conversation_history if msg["type"] == "assistant"
        ]

        intents_used = list(
            set(
                [
                    msg.get("intent", "unknown")
                    for msg in assistant_messages
                    if msg.get("intent")
                ]
            )
        )

        # 计算对话时长
        if len(self.conversation_history) >= 2:
            start_time = self.conversation_history[0]["timestamp"]
            end_time = self.conversation_history[-1]["timestamp"]
            # 简单的时间差计算
            duration = "几分钟"  # 这里可以更精确地计算
        else:
            duration = "少于1分钟"

        return {
            "total_messages": len(self.conversation_history),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "intents_used": intents_used,
            "duration": duration,
        }


# 使用示例
if __name__ == "__main__":
    from chat_vector_tool import VectorDBTool

    # 初始化处理器
    vector_tool = VectorDBTool()
    handler = ChatMessageHandler(vector_tool)

    # 测试消息处理
    test_messages = [
        "搜索JDBC配置问题",
        "pr 16487",
        "keywords Maven,构建",
        "stats",
        "help",
        "退出",
    ]

    for message in test_messages:
        print(f"\n用户: {message}")
        response = handler.process_message(message)
        print(f"助手: {response['message'][:100]}...")
