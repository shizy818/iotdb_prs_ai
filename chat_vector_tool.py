#!/usr/bin/env python3
"""
向量数据库工具类 - 为聊天应用提供智能检索工具
基于现有的VectorStoreManager，提供适合聊天应用的接口
"""

import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from vector_store import VectorStoreManager
from logger_config import setup_logger

logger = setup_logger(__name__)


class VectorDBTool:
    """向量数据库工具类，为聊天应用提供智能检索功能"""

    def __init__(self, persist_directory: str = "./chroma_db"):
        """
        初始化向量数据库工具

        Args:
            persist_directory: Chroma数据库持久化目录
        """
        self.vector_store = VectorStoreManager(persist_directory)
        logger.info("向量数据库工具已初始化")

    def search_similar_issues(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        搜索相似的问题和解决方案

        Args:
            query: 用户查询的问题描述
            max_results: 最大返回结果数

        Returns:
            包含搜索结果的字典
        """
        try:
            logger.info(f"搜索相似问题: {query}")

            # 执行语义搜索
            results = self.vector_store.search_similar_prs(query, k=max_results)

            if not results:
                return {
                    "success": True,
                    "query": query,
                    "results": [],
                    "message": "未找到相关的问题和解决方案",
                }

            # 格式化结果
            formatted_results = []
            for result in results:
                formatted_results.append(
                    {
                        "pr_number": result["pr_number"],
                        "pr_title": result["pr_title"],
                        "summary": self._extract_summary(result["content"]),
                        "relevance_score": self._calculate_relevance(
                            query, result["content"]
                        ),
                        "metadata": result["metadata"],
                    }
                )

            return {
                "success": True,
                "query": query,
                "results": formatted_results,
                "total_found": len(formatted_results),
                "message": f"找到 {len(formatted_results)} 个相关的问题",
            }

        except Exception as e:
            logger.error(f"搜索相似问题时出错: {e}")
            return {"success": False, "error": str(e), "message": "搜索过程中出现错误"}

    def get_pr_details(self, pr_number: int) -> Dict[str, Any]:
        """
        获取特定PR的详细信息

        Args:
            pr_number: PR编号

        Returns:
            包含PR详细信息的字典
        """
        try:
            logger.info(f"获取PR #{pr_number} 的详细信息")

            pr_data = self.vector_store.get_pr_by_number(pr_number)

            if not pr_data:
                return {
                    "success": False,
                    "pr_number": pr_number,
                    "message": f"未找到 PR #{pr_number} 的分析结果",
                }

            return {
                "success": True,
                "pr_number": pr_data["pr_number"],
                "pr_title": pr_data["pr_title"],
                "content": pr_data["content"],
                "metadata": pr_data["metadata"],
                "analyzed_at": pr_data["metadata"].get("analyzed_at"),
                "message": f"成功获取 PR #{pr_number} 的详细信息",
            }

        except Exception as e:
            logger.error(f"获取PR详情时出错: {e}")
            return {
                "success": False,
                "pr_number": pr_number,
                "error": str(e),
                "message": "获取PR详情时出现错误",
            }

    def search_by_keywords(
        self, keywords: List[str], max_results: int = 10
    ) -> Dict[str, Any]:
        """
        根据关键词搜索相关PR

        Args:
            keywords: 关键词列表
            max_results: 最大返回结果数

        Returns:
            包含搜索结果的字典
        """
        try:
            query = " ".join(keywords)
            logger.info(f"根据关键词搜索: {query}")

            results = self.vector_store.search_similar_prs(query, k=max_results)

            if not results:
                return {
                    "success": True,
                    "keywords": keywords,
                    "results": [],
                    "message": "未找到包含这些关键词的相关内容",
                }

            # 计算每个结果与关键词的匹配度
            formatted_results = []
            for result in results:
                keyword_matches = self._count_keyword_matches(
                    keywords, result["content"]
                )
                formatted_results.append(
                    {
                        "pr_number": result["pr_number"],
                        "pr_title": result["pr_title"],
                        "summary": self._extract_summary(result["content"]),
                        "keyword_matches": keyword_matches,
                        "match_ratio": (
                            keyword_matches / len(keywords) if keywords else 0
                        ),
                        "metadata": result["metadata"],
                    }
                )

            # 按匹配度排序
            formatted_results.sort(key=lambda x: x["match_ratio"], reverse=True)

            return {
                "success": True,
                "keywords": keywords,
                "results": formatted_results,
                "total_found": len(formatted_results),
                "message": f"根据关键词找到 {len(formatted_results)} 个相关结果",
            }

        except Exception as e:
            logger.error(f"关键词搜索时出错: {e}")
            return {
                "success": False,
                "keywords": keywords,
                "error": str(e),
                "message": "关键词搜索过程中出现错误",
            }

    def get_database_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息

        Returns:
            包含数据库统计信息的字典
        """
        try:
            stats = self.vector_store.get_collection_stats()

            return {
                "success": True,
                "stats": stats,
                "message": "数据库统计信息获取成功",
            }

        except Exception as e:
            logger.error(f"获取数据库统计信息时出错: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "获取数据库统计信息时出现错误",
            }

    def _extract_summary(self, content: str, max_length: int = 200) -> str:
        """
        从内容中提取摘要

        Args:
            content: 原始内容
            max_length: 摘要最大长度

        Returns:
            内容摘要
        """
        # 移除PR编号和标题行，只保留分析内容
        lines = content.split("\n")
        if lines and ("PR #" in lines[0] or lines[0].strip().isdigit() == False):
            # 跳过第一行（PR编号和标题）
            content = "\n".join(lines[1:]) if len(lines) > 1 else content

        # 清理内容
        content = content.strip()

        # 截取摘要
        if len(content) <= max_length:
            return content
        else:
            return (
                content[:max_length].rsplit("。", 1)[0] + "..."
                if "。" in content[:max_length]
                else content[:max_length] + "..."
            )

    def _calculate_relevance(self, query: str, content: str) -> float:
        """
        计算查询与内容的相关性（简单实现）

        Args:
            query: 查询字符串
            content: 内容字符串

        Returns:
            相关性分数 (0-1)
        """
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())

        if not query_words:
            return 0.0

        intersection = query_words.intersection(content_words)
        return len(intersection) / len(query_words)

    def _count_keyword_matches(self, keywords: List[str], content: str) -> int:
        """
        计算关键词在内容中的匹配数

        Args:
            keywords: 关键词列表
            content: 内容字符串

        Returns:
            匹配的关键词数量
        """
        content_lower = content.lower()
        matches = 0

        for keyword in keywords:
            if keyword.lower() in content_lower:
                matches += 1

        return matches

    def get_available_commands(self) -> Dict[str, str]:
        """
        获取可用命令列表

        Returns:
            命令名称和描述的字典
        """
        return {
            "search": "搜索相似问题，例如：search JDBC配置问题",
            "pr": "获取特定PR详情，例如：pr 16487",
            "keywords": "关键词搜索，例如：keywords Maven,构建,错误",
            "stats": "显示数据库统计信息",
            "help": "显示帮助信息",
            "quit": "退出聊天应用",
        }


# 使用示例
if __name__ == "__main__":
    # 初始化工具
    tool = VectorDBTool()

    # 测试搜索功能
    result = tool.search_similar_issues("JDBC配置问题")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 测试获取PR详情
    result = tool.get_pr_details(16487)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 测试数据库统计
    result = tool.get_database_stats()
    print(json.dumps(result, ensure_ascii=False, indent=2))
