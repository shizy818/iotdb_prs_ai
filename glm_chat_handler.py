#!/usr/bin/env python3
"""
基于GLM-4.6的聊天处理器
让用户直接与GLM-4.6模型对话，模型可以调用chroma工具
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from zhipuai import ZhipuAI
from chat_vector_tool import VectorDBTool
from logger_config import setup_logger
from config import ANTHROPIC_API_KEY

logger = setup_logger(__name__)


class GLMChatHandler:
    """基于GLM-4.6的聊天处理器"""

    def __init__(self, vector_tool: VectorDBTool):
        """
        初始化GLM聊天处理器

        Args:
            vector_tool: 向量数据库工具实例
        """
        # 从config导入API配置
        self.client = ZhipuAI(api_key=ANTHROPIC_API_KEY)
        self.vector_tool = vector_tool
        self.conversation_history = []
        self.start_time = datetime.now()

        # 工具函数定义 - 主要使用关键词搜索
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_by_keywords",
                    "description": "根据关键词搜索相关的IoTDB PR，这是主要的搜索方式",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "关键词列表，例如：['内存泄漏', '1.3.2', '版本']",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "最大返回结果数量，默认5个",
                                "default": 5,
                            },
                        },
                        "required": ["keywords"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pr_details",
                    "description": "获取特定PR的详细信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pr_number": {"type": "integer", "description": "PR编号"}
                        },
                        "required": ["pr_number"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_database_stats",
                    "description": "获取数据库统计信息，包括PR总数等",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

        # 系统提示词
        self.system_prompt = """你是一个IoTDB技术专家助手，专门帮助用户查询和了解IoTDB项目中的PR（Pull Request）信息。你的主要职责是：

1. **理解用户需求**：准确理解用户关于IoTDB技术问题的询问
2. **智能提取关键词**：从用户问题中提取关键词进行精确搜索
3. **专业解答**：基于搜索结果，为用户提供准确、专业的技术解答

**主要工具：**
- `search_by_keywords`: 根据关键词搜索相关PR
- `get_pr_details`: 获取特定PR的详细信息
- `get_database_stats`: 获取数据库统计信息

**关键词提取原则：**
- 提取具体的技术问题描述（如：内存泄漏、连接超时、查询慢等）
- 包含具体版本信息（如：1.3.2、1.3.1等）
- 包含相关组件名（如：JDBC、TSFile、查询引擎、存储引擎等）
- 包含具体的技术术语（如：并发、压缩、序列化、索引等）
- 避免使用过于宽泛的词汇（如："问题"、"相关"、"有关"、"修复"等）

**使用示例：**
用户问题："客户在iotdb1.3.2版本遇到内存泄漏问题，请列出最相关的5个PR"
提取关键词：['内存泄漏', '1.3.2']
应该调用：search_by_keywords(keywords=['内存泄漏', '1.3.2'], max_results=5)

用户问题："我想了解JDBC连接相关的PR"
提取关键词：['JDBC', '连接']
应该调用：search_by_keywords(keywords=['JDBC', '连接'])

用户问题："查询引擎性能优化有哪些改进？"
提取关键词：['查询引擎', '性能', '优化']
应该调用：search_by_keywords(keywords=['查询引擎', '性能', '优化'])

**回答原则：**
- 优先使用关键词搜索工具查找相关PR
- 回答要简洁明了，重点突出
- 列出最相关的PR信息（编号、标题、简要描述）
- 如果需要更多细节，可以建议用户查看特定PR的详细信息"""

        logger.info("GLM聊天处理器已初始化")

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
                return self._create_response("error", "empty_message", "请输入您的问题")

            # 记录到对话历史
            self.conversation_history.append({"role": "user", "content": message})

            # 准备消息历史（限制最近10轮对话以控制token使用）
            messages = [{"role": "system", "content": self.system_prompt}]

            # 添加最近的对话历史（转换为GLM格式）
            recent_history = (
                self.conversation_history[-10:]
                if len(self.conversation_history) > 10
                else self.conversation_history
            )
            for msg in recent_history[:-1]:  # 排除当前用户消息
                messages.append({"role": msg["role"], "content": msg["content"]})

            # 添加当前用户消息
            messages.append({"role": "user", "content": message})

            logger.info(f"发送消息到GLM-4.6: {message[:100]}...")

            # 调用GLM API
            response = self.client.chat.completions.create(
                model="glm-4.6",  # 使用GLM-4.6模型
                messages=messages,
                tools=self.tools,
                tool_choice="auto",  # 让模型自动决定是否使用工具
                temperature=0.3,
                max_tokens=50000,
            )

            assistant_message = response.choices[0].message

            # 循环处理工具调用，直到没有更多工具调用
            final_message = ""
            current_message = assistant_message

            while True:
                # 检查是否有工具调用
                if current_message.tool_calls:
                    # 执行工具调用
                    tool_results = []
                    for tool_call in current_message.tool_calls:
                        tool_result = self._execute_tool_call(tool_call)
                        tool_results.append(tool_result)

                    # 构建包含工具结果的消息
                    messages.append(
                        {
                            "role": "assistant",
                            "content": current_message.content or "",
                            "tool_calls": [
                                tool_call.model_dump()
                                for tool_call in current_message.tool_calls
                            ],
                        }
                    )

                    for tool_result in tool_results:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_result["tool_call_id"],
                                "content": json.dumps(
                                    tool_result["result"], ensure_ascii=False
                                ),
                            }
                        )

                    # 再次调用GLM获取下一步回答
                    next_response = self.client.chat.completions.create(
                        model="glm-4.6",
                        messages=messages,
                        tools=self.tools,
                        tool_choice="auto",
                        temperature=0.3,
                        max_tokens=50000,
                    )

                    current_message = next_response.choices[0].message
                    # 继续循环检查是否有新的工具调用
                else:
                    # 没有更多工具调用，获取最终回答
                    final_message = current_message.content or ""
                    break

            # 记录助手回复到对话历史
            self.conversation_history.append(
                {"role": "assistant", "content": final_message}
            )

            logger.info(f"收到GLM回复: {final_message[:100]}...")

            return self._create_response("success", "glm_response", final_message)

        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            error_message = f"处理消息时出现错误: {str(e)}"

            # 记录错误回复到对话历史
            self.conversation_history.append(
                {"role": "assistant", "content": error_message}
            )

            return self._create_response("error", "processing_error", error_message)

    def _execute_tool_call(self, tool_call) -> Dict[str, Any]:
        """
        执行工具调用

        Args:
            tool_call: GLM返回的工具调用对象

        Returns:
            包含工具调用结果的字典
        """
        try:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            logger.info(f"执行工具调用: {function_name}, 参数: {arguments}")

            if function_name == "search_by_keywords":
                result = self.vector_tool.search_by_keywords(
                    keywords=arguments["keywords"],
                    max_results=arguments.get("max_results", 5),
                )
            elif function_name == "get_pr_details":
                result = self.vector_tool.get_pr_details(arguments["pr_number"])
            elif function_name == "get_database_stats":
                result = self.vector_tool.get_database_stats()
            else:
                result = {"success": False, "error": f"未知的工具函数: {function_name}"}

            logger.info(f"工具调用结果: {result.get('success', False)}")

            return {"tool_call_id": tool_call.id, "result": result}

        except Exception as e:
            logger.error(f"执行工具调用时出错: {e}")
            return {
                "tool_call_id": tool_call.id,
                "result": {"success": False, "error": f"工具调用执行错误: {str(e)}"},
            }

    def _create_response(
        self,
        status: str,
        message_type: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        创建标准响应格式

        Args:
            status: 响应状态
            message_type: 消息类型
            content: 响应内容
            metadata: 额外的元数据

        Returns:
            标准化的响应字典
        """
        response = {
            "status": status,
            "type": message_type,
            "message": content,
            "timestamp": self._get_current_time(),
        }

        if metadata:
            response["metadata"] = metadata

        return response

    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []
        logger.info("对话历史已清空")

    def get_conversation_length(self) -> int:
        """获取对话轮数"""
        return len([msg for msg in self.conversation_history if msg["role"] == "user"])

    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        获取对话摘要

        Returns:
            对话统计信息
        """
        # 统计消息数量
        user_messages = [
            msg for msg in self.conversation_history if msg["role"] == "user"
        ]
        assistant_messages = [
            msg for msg in self.conversation_history if msg["role"] == "assistant"
        ]

        intents_used = []  # GLM模型不使用意图分类，返回空列表

        # 计算对话时长 - 即使没有消息也要计算
        end_time = datetime.now()
        duration_minutes = int((end_time - self.start_time).total_seconds() / 60)

        if duration_minutes == 0:
            duration = "少于1分钟"
        else:
            duration = f"{duration_minutes}分钟"

        return {
            "total_messages": len(self.conversation_history),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "intents_used": intents_used,
            "duration": duration,
        }
