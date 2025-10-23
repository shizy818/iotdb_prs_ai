#!/usr/bin/env python3
"""
向量数据库管理模块 - 使用Chroma存储PR分析结果
支持向量化存储、语义检索和相似度搜索
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain.schema import Document


class VectorStoreManager:
    """管理PR分析结果的向量数据库"""

    def __init__(self, persist_directory: str = "./chroma_db"):
        """
        初始化向量数据库管理器

        Args:
            persist_directory: Chroma数据库持久化目录
        """
        self.persist_directory = persist_directory

        # 确保目录存在
        os.makedirs(persist_directory, exist_ok=True)

        # 初始化embedding模型 - 使用轻量级的中文模型
        print("正在加载embedding模型...")
        # 获取项目根目录（vector_store.py所在目录）
        project_root = Path(__file__).parent
        model_path = project_root / "models" / "paraphrase-multilingual-MiniLM-L12-v2"

        if not model_path.exists():
            raise FileNotFoundError(
                f"模型文件不存在: {model_path}\n" f"请确保模型已下载到正确位置"
            )

        self.embeddings = HuggingFaceEmbeddings(
            model_name=str(model_path),
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        # 初始化或加载Chroma向量数据库
        self.vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=self.embeddings,
            collection_name="pr_analysis",
        )

        print(f"向量数据库已初始化: {persist_directory}")

    def pr_exists(self, pr_number: int) -> bool:
        """
        检查指定PR是否已经存在于向量数据库中

        Args:
            pr_number: PR编号

        Returns:
            如果PR已存在返回True，否则返回False
        """
        try:
            # 查询指定pr_number的文档
            results = self.vectorstore.get(where={"pr_number": pr_number})
            # 如果有结果，说明PR已存在
            return len(results.get("ids", [])) > 0
        except Exception as e:
            print(f"⚠️  检查PR是否存在时出错: {e}")
            return False

    def add_pr_analysis(
        self,
        pr_number: int,
        pr_title: str,
        analysis: str,
        metadata: Optional[Dict] = None,
        skip_if_exists: bool = True,
    ) -> bool:
        """
        添加PR分析结果到向量数据库

        Args:
            pr_number: PR编号
            pr_title: PR标题
            analysis: Claude分析结果
            metadata: 额外的元数据（如分析时间、标签等）
            skip_if_exists: 如果PR已存在，是否跳过添加（默认True）

        Returns:
            是否成功添加
        """
        try:
            # 检查PR是否已存在
            if skip_if_exists and self.pr_exists(pr_number):
                print(f"ℹ️  PR #{pr_number} 已存在于向量数据库中，跳过添加")
                return False

            # 准备文档元数据
            doc_metadata = {
                "pr_number": pr_number,
                "pr_title": pr_title,
                "analyzed_at": datetime.now().isoformat(),
                "source": "claude_analysis",
            }

            # 合并用户提供的额外元数据
            if metadata:
                doc_metadata.update(metadata)

            # 创建完整的文档内容，包含PR基本信息
            content = f"PR #{pr_number}: {pr_title}\n\n{analysis}"

            # 创建单个Document对象
            doc = Document(page_content=content, metadata=doc_metadata)

            # 添加到向量数据库
            self.vectorstore.add_documents([doc])
            print(f"✅ PR #{pr_number} 分析结果已添加到向量数据库")

            return True

        except Exception as e:
            print(f"❌ 添加PR分析到向量数据库失败: {e}")
            return False

    def search_similar_prs(
        self, query: str, k: int = 5, filter_dict: Optional[Dict] = None
    ) -> List[Dict]:
        """
        语义搜索相似的PR分析

        Args:
            query: 搜索查询
            k: 返回最相似的k个结果
            filter_dict: 元数据过滤条件

        Returns:
            相似PR列表，包含内容和元数据
        """
        try:
            # 执行相似度搜索
            if filter_dict:
                results = self.vectorstore.similarity_search(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search(query, k=k)

            # 格式化结果
            formatted_results = []
            for doc in results:
                formatted_results.append(
                    {
                        "pr_number": doc.metadata.get("pr_number"),
                        "pr_title": doc.metadata.get("pr_title"),
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                    }
                )

            return formatted_results

        except Exception as e:
            print(f"❌ 搜索失败: {e}")
            return []

    def search_with_score(
        self, query: str, k: int = 5, filter_dict: Optional[Dict] = None
    ) -> List[tuple]:
        """
        带相似度分数的搜索

        Args:
            query: 搜索查询
            k: 返回最相似的k个结果
            filter_dict: 元数据过滤条件

        Returns:
            (Document, score)元组列表
        """
        try:
            if filter_dict:
                results = self.vectorstore.similarity_search_with_score(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search_with_score(query, k=k)

            return results

        except Exception as e:
            print(f"❌ 搜索失败: {e}")
            return []

    def get_pr_by_number(self, pr_number: int) -> Optional[Dict]:
        """
        根据PR编号获取分析结果

        Args:
            pr_number: PR编号

        Returns:
            包含PR分析内容和元数据的字典，如果不存在则返回None
        """
        try:
            # 查询指定pr_number的所有文档
            results = self.vectorstore.get(where={"pr_number": pr_number})

            if not results or not results.get("ids"):
                return None

            # 合并所有chunks的内容
            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])

            if not documents:
                return None

            # 组合完整内容
            full_content = "\n".join(documents)

            # 使用第一个文档的元数据作为基础
            metadata = metadatas[0] if metadatas else {}

            return {
                "pr_number": pr_number,
                "pr_title": metadata.get("pr_title", ""),
                "content": full_content,
                "metadata": metadata,
            }

        except Exception as e:
            print(f"❌ 获取PR #{pr_number}失败: {e}")
            return None

    def delete_pr_analysis(self, pr_number: int) -> bool:
        """
        删除指定PR的分析结果

        Args:
            pr_number: PR编号

        Returns:
            是否成功删除
        """
        try:
            # 使用元数据过滤删除
            self.vectorstore.delete(where={"pr_number": pr_number})
            print(f"✅ PR #{pr_number} 的分析结果已从向量数据库删除")
            return True

        except Exception as e:
            print(f"❌ 删除失败: {e}")
            return False

    def get_collection_stats(self) -> Dict:
        """
        获取向量数据库统计信息

        Returns:
            包含统计信息的字典
        """
        try:
            collection = self.vectorstore._collection
            count = collection.count()

            return {
                "total_documents": count,
                "collection_name": "pr_analysis",
                "persist_directory": self.persist_directory,
            }

        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return {}


# 使用示例
if __name__ == "__main__":
    # 初始化向量数据库
    vector_store = VectorStoreManager()

    # 添加示例PR分析
    sample_analysis = """
    这是一个修复JDBC配置错误的PR。
    主要解决了feature.xml路径配置错误的问题。
    影响范围：使用Karaf部署的用户。
    建议优先级：中等。
    """

    vector_store.add_pr_analysis(
        pr_number=16487,
        pr_title="Fix jdbc feature.xml error",
        analysis=sample_analysis,
        metadata={"labels": ["bug", "jdbc"]},
    )

    # 搜索示例
    results = vector_store.search_similar_prs("JDBC配置问题", k=3)
    print("\n搜索结果:")
    for result in results:
        print(f"PR #{result['pr_number']}: {result['pr_title']}")

    # 获取统计信息
    stats = vector_store.get_collection_stats()
    print(f"\n数据库统计: {stats}")
