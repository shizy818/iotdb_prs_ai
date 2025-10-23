#!/usr/bin/env python3
"""
使用 LangChain 实现 PR 分析
集成 LangChain 的工具和 Agent 能力
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool, StructuredTool
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from database import DatabaseManager


class ReadFileInput(BaseModel):
    """读取文件的输入参数"""

    file_path: str = Field(
        description="要读取的文件路径，相对于 IoTDB 源码根目录（如 'iotdb-core/datanode/src/main/java/org/apache/iotdb/db/queryengine/execution/operator/process/TableIntoOperator.java'）"
    )


class GlobInput(BaseModel):
    """Glob 查找文件的输入参数"""

    pattern: str = Field(
        description="Glob 模式（如 '**/*TableIntoOperator*.java', '**/*.xml'）"
    )
    path: str = Field(
        default="", description="搜索路径，相对于 IoTDB 源码根目录（可选，默认为根目录）"
    )


class GrepInput(BaseModel):
    """Grep 搜索的输入参数"""

    pattern: str = Field(description="搜索模式（正则表达式）")
    path: str = Field(default="", description="搜索路径，相对于 IoTDB 源码根目录（可选）")
    file_type: str = Field(default="", description="文件类型过滤（如 'java', 'py', 'xml'）（可选）")


def _build_analysis_prompt(pr_data: Dict, diff_content: str) -> str:
    """
    构建PR分析提示

    Args:
        pr_data: PR数据
        diff_content: diff内容

    Returns:
        分析提示字符串
    """
    # 构建评论部分
    if pr_data.get("comments"):
        comments_section = "- PR 讨论评论\n"
        for idx, comment in enumerate(pr_data["comments"], 1):
            comment_time = comment.get("created_at", "")
            comment_user = comment.get("user", "未知用户")
            comment_body = comment.get("body", "")
            comments_section += f"""  评论 {idx} (作者: {comment_user}, 时间: {comment_time}):
{comment_body}
---
"""
    else:
        comments_section = "- PR 讨论评论: 无\n"

    template = """
IoTDB PR详细信息：
- 编号: {number}
- 标题: {title}
- 描述: {body}
- 创建时间: {created_at}
- 合并时间: {merged_at}
- 作者: {user}
- 标签: {labels}
- 代码变更: +{additions} 行, -{deletions} 行
- 分支: {head} -> {base}
- Diff链接: {diff_url}
{comments_section}

这是一个IoTDB的Pull Request，请先阅读上述基本信息。接下来是代码变更的diff内容：

```diff
{diff_content}
```

现在你已经收到了完整的PR信息（包括基本信息和diff内容）。

**重要：在分析之前，请务必使用以下工具读取相关源码文件以便深入理解：**
1. 使用 glob 工具查找 diff 中涉及的源码文件（例如：`**/ClassName.java`）
2. 使用 read 工具读取这些完整的源码文件
3. 使用 grep 工具搜索相关的类、方法或关键字以获取更多上下文

**然后进行深入分析：**
1. 这个PR具体解决了什么技术问题？
2. 如果客户环境没有这个修复，系统可能出现什么具体错误？
3. 可能出现的错误信息、异常堆栈或日志是什么？
4. 对系统稳定性、性能和功能的影响程度？
5. 建议的临时解决方案或规避措施？
6. 推荐的升级优先级？

请提供详细、结构化的分析结果。"""

    return template.format(
        number=pr_data.get("number", ""),
        title=pr_data.get("title", ""),
        body=pr_data.get("body", "无描述"),
        created_at=pr_data.get("created_at", ""),
        merged_at=pr_data.get("merged_at", ""),
        user=pr_data.get("user", ""),
        labels=json.dumps(pr_data.get("labels", []), ensure_ascii=False),
        additions=pr_data.get("additions", 0),
        deletions=pr_data.get("deletions", 0),
        head=pr_data.get("head", ""),
        base=pr_data.get("base", ""),
        comments_section=comments_section,
        diff_url=pr_data.get("diff_url", "无"),
        diff_content=diff_content if diff_content else "无代码变更",
    )


class PRAnalysisLangChain:
    """使用 LangChain 实现的 PR 分析器"""

    def __init__(
        self, iotdb_source_dir: str = "/Users/shizy/projects/iotdb_issues_ai/iotdb"
    ):
        """
        初始化 PR 分析器

        Args:
            iotdb_source_dir: IoTDB 源码目录路径
        """
        self.db = DatabaseManager()
        self.iotdb_source_dir = Path(iotdb_source_dir)

        # 设置 Anthropic API
        os.environ["ANTHROPIC_BASE_URL"] = "https://open.bigmodel.cn/api/anthropic"
        os.environ["ANTHROPIC_API_KEY"] = "9be7a6c89bfc4cd99efb491c77140aa4.GI2bDndwSd7hqy69"

        # 初始化 LangChain 聊天模型
        self.llm = ChatAnthropic(
            model="glm-4-plus",
            # model="claude-sonnet-4-5-20250929",
            temperature=0.3,
            max_tokens=16384,
        )

        # 创建工具
        self.tools = self._create_tools()

    def _create_read_tool(self) -> BaseTool:
        """创建读取文件的工具"""

        def read_file(file_path: str) -> str:
            """
            读取 IoTDB 源码文件的内容

            Args:
                file_path: 文件路径（相对于 IoTDB 源码根目录）

            Returns:
                完整文件内容（给模型分析用）
            """
            try:
                full_path = self.iotdb_source_dir / file_path
                if not full_path.exists():
                    print(f"❌ 文件不存在: {file_path}")
                    return f"错误: 文件不存在: {file_path}"

                # 读取文件内容（限制大小）
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read(500000)  # 限制 500KB

                # 控制台只显示简要信息
                file_size = len(content)
                line_count = content.count('\n') + 1
                print(f"📖 已读取文件: {file_path} ({file_size:,} 字符, {line_count:,} 行)")

                # 返回完整内容给模型
                return content
            except Exception as e:
                print(f"❌ 读取文件失败: {file_path} - {str(e)}")
                return f"错误: 读取文件失败: {str(e)}"

        return StructuredTool.from_function(
            func=read_file,
            name="read",
            description="读取 IoTDB 源码文件的内容。文件路径相对于 IoTDB 源码根目录。",
            args_schema=ReadFileInput,
        )

    def _create_glob_tool(self) -> BaseTool:
        """创建 Glob 查找文件的工具"""

        def glob_files(pattern: str, path: str = "") -> str:
            """
            使用 glob 模式查找匹配的文件

            Args:
                pattern: Glob 模式（如 '**/*.java'）
                path: 搜索路径（相对于 IoTDB 源码根目录）

            Returns:
                匹配的文件列表（JSON 格式）
            """
            try:
                search_dir = (
                    self.iotdb_source_dir / path if path else self.iotdb_source_dir
                )
                matches = list(search_dir.glob(pattern))

                # 转换为相对路径
                relative_paths = [
                    str(p.relative_to(self.iotdb_source_dir)) for p in matches[:100]
                ]  # 限制 100 个结果

                # 控制台显示搜索结果
                search_path = f"路径: {path if path else '根目录'}"
                print(f"🔍 Glob 搜索 '{pattern}' {search_path} -> 找到 {len(relative_paths)} 个文件")

                result = {
                    "success": True,
                    "matches": relative_paths,
                    "count": len(relative_paths),
                }
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ Glob 搜索失败: {pattern} - {str(e)}")
                return json.dumps(
                    {"success": False, "error": f"Glob 搜索失败: {str(e)}"}
                )

        return StructuredTool.from_function(
            func=glob_files,
            name="glob",
            description="使用 glob 模式查找匹配的文件。支持 ** 通配符。",
            args_schema=GlobInput,
        )

    def _create_grep_tool(self) -> BaseTool:
        """创建 Grep 搜索工具"""

        def grep_search(pattern: str, path: str = "", file_type: str = "") -> str:
            """
            在 IoTDB 源码中搜索匹配的内容

            Args:
                pattern: 搜索模式（正则表达式）
                path: 搜索路径（相对于 IoTDB 源码根目录）
                file_type: 文件类型过滤（如 'java', 'py', 'xml'）

            Returns:
                搜索结果（JSON 格式）
            """
            import subprocess

            try:
                search_dir = (
                    self.iotdb_source_dir / path if path else self.iotdb_source_dir
                )

                # 构建 rg (ripgrep) 命令
                cmd = ["rg", "--json", pattern, str(search_dir)]
                if file_type:
                    cmd.extend(["--type", file_type])

                # 执行搜索
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=10
                )

                # 解析结果
                matches = []
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("type") == "match":
                            match_data = data.get("data", {})
                            file_path = match_data.get("path", {}).get("text", "")
                            line_number = match_data.get("line_number")
                            line_text = (
                                match_data.get("lines", {}).get("text", "").strip()
                            )

                            # 转换为相对路径
                            if file_path:
                                rel_path = str(
                                    Path(file_path).relative_to(self.iotdb_source_dir)
                                )
                                matches.append(
                                    {
                                        "file": rel_path,
                                        "line": line_number,
                                        "content": line_text,
                                    }
                                )
                    except json.JSONDecodeError:
                        continue

                # 控制台显示搜索结果
                search_info = f"模式: '{pattern}'"
                if path:
                    search_info += f", 路径: {path}"
                if file_type:
                    search_info += f", 类型: {file_type}"
                print(f"🔎 Grep 搜索 {search_info} -> 找到 {len(matches)} 个匹配")

                result_data = {
                    "success": True,
                    "matches": matches[:50],  # 限制 50 个结果
                    "count": len(matches),
                }
                return json.dumps(result_data, ensure_ascii=False, indent=2)

            except FileNotFoundError:
                print(f"❌ ripgrep (rg) 未安装，请安装: brew install ripgrep")
                return json.dumps(
                    {
                        "success": False,
                        "error": "ripgrep (rg) 未安装，请安装: brew install ripgrep",
                    }
                )
            except Exception as e:
                print(f"❌ Grep 搜索失败: {pattern} - {str(e)}")
                return json.dumps(
                    {"success": False, "error": f"Grep 搜索失败: {str(e)}"}
                )

        return StructuredTool.from_function(
            func=grep_search,
            name="grep",
            description="在 IoTDB 源码中搜索匹配的内容。使用正则表达式模式。",
            args_schema=GrepInput,
        )

    def _create_tools(self) -> List[BaseTool]:
        """创建所有工具"""
        return [
            self._create_read_tool(),
            self._create_glob_tool(),
            self._create_grep_tool(),
        ]

    def get_pr_by_number(self, pr_number: Optional[int] = None) -> Optional[Dict]:
        """
        从数据库获取指定PR的数据

        Args:
            pr_number: PR编号，如果为None则获取最新的PR

        Returns:
            PR数据字典，如果未找到则返回None
        """
        try:
            cursor = self.db.connection.cursor(dictionary=True)

            if pr_number:
                query = """
                SELECT number, title, body, created_at, merged_at, user, labels,
                       head, base, additions, deletions, diff_url, comments_url
                FROM iotdb_prs
                WHERE number = %s
                """
                cursor.execute(query, (pr_number,))
            else:
                query = """
                SELECT number, title, body, created_at, merged_at, user, labels,
                       head, base, additions, deletions, diff_url, comments_url
                FROM iotdb_prs
                ORDER BY merged_at DESC
                LIMIT 1
                """
                cursor.execute(query)

            pr = cursor.fetchone()

            if pr:
                # 解析JSON格式的labels
                if pr["labels"]:
                    try:
                        pr["labels"] = json.loads(pr["labels"])
                    except (json.JSONDecodeError, TypeError):
                        pr["labels"] = []
                else:
                    pr["labels"] = []

                # 获取对应的diff内容
                diff_query = """
                SELECT diff_content
                FROM pr_diffs
                WHERE pr_number = %s
                ORDER BY created_at DESC
                LIMIT 1
                """
                cursor.execute(diff_query, (pr["number"],))
                diff_result = cursor.fetchone()

                if diff_result and diff_result["diff_content"]:
                    pr["diff_content"] = diff_result["diff_content"]
                else:
                    pr["diff_content"] = None

                # 获取对应的评论内容
                comments_query = """
                SELECT id, user, body, created_at, updated_at, html_url
                FROM pr_comments
                WHERE pr_number = %s
                ORDER BY created_at ASC
                """
                cursor.execute(comments_query, (pr["number"],))
                comments_results = cursor.fetchall()

                if comments_results:
                    pr["comments"] = comments_results
                else:
                    pr["comments"] = []

            cursor.close()
            return pr

        except Exception as e:
            print(f"从数据库获取PR数据时出错: {e}")
            return None

    def analyze_pr(
        self, pr_number: Optional[int] = None, verbose: bool = True
    ) -> Dict:
        """
        使用 LangChain Agent 分析 PR

        Agent 会在单次调用中自动进行多轮工具调用，每轮都记住之前的工具结果

        Args:
            pr_number: PR编号，如果为None则分析最新的PR
            verbose: 是否显示详细过程

        Returns:
            分析结果字典
        """
        # 获取PR数据
        target_pr = self.get_pr_by_number(pr_number)

        if not target_pr:
            if pr_number:
                return {"success": False, "error": f"未找到编号为 {pr_number} 的PR"}
            else:
                return {"success": False, "error": "数据库中没有找到PR数据"}

        pr_number = target_pr["number"]
        pr_title = target_pr["title"]

        if verbose:
            print(f"🔍 正在分析 PR #{pr_number}: {pr_title}")

        try:
            # 获取 diff 内容
            diff_content = target_pr.get("diff_content", "")
            diff_size = len(diff_content) if diff_content else 0

            if verbose:
                print(f"📦 Diff 大小: {diff_size:,} 字符 (~{diff_size // 4:,} tokens)")

            # 构建分析提示
            analysis_prompt = _build_analysis_prompt(target_pr, diff_content)

            if verbose:
                print(f"📊 完整查询大小: {len(analysis_prompt):,} 字符")
                print(f"🚀 正在使用 LangChain Agent 进行分析...")
                print("\n=== Claude 分析结果 ===\n")

            # 创建 Agent 提示模板
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "您是一名时序数据库IoTDB专家。您可以使用工具读取和搜索 IoTDB 源码来辅助分析。"
                        "请根据提供的PR信息和本地iotdb源码进行深入分析，然后提供详细的分析结果。",
                    ),
                    ("human", "{input}"),
                    MessagesPlaceholder(variable_name="agent_scratchpad"),
                ]
            )

            # 创建 Agent
            agent = create_tool_calling_agent(self.llm, self.tools, prompt)

            # 创建 Agent 执行器
            agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=verbose,
                max_iterations=15,
                handle_parsing_errors=True,
            )

            # 执行分析
            result = agent_executor.invoke({"input": analysis_prompt})

            analysis_result = result.get("output", "")

            if verbose:
                print(f"\n\n=== 分析完成 ===\n")

            return {
                "success": True,
                "pr_number": pr_number,
                "pr_title": pr_title,
                "analysis": analysis_result,
                "analyzed_at": datetime.now().isoformat(),
                "pr_data": target_pr,
            }

        except Exception as e:
            error_msg = f"分析过程出错: {str(e)}"
            if verbose:
                print(f"❌ {error_msg}")
                import traceback

                traceback.print_exc()

            return {
                "success": False,
                "pr_number": pr_number,
                "pr_title": target_pr.get("title", ""),
                "error": error_msg,
                "analyzed_at": datetime.now().isoformat(),
            }

    def close(self):
        """关闭数据库连接"""
        if self.db:
            self.db.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="IoTDB PR分析工具 - 使用 LangChain 实现"
    )
    parser.add_argument("--pr", type=int, help="分析特定PR编号")
    parser.add_argument("--output", type=str, help="输出结果到JSON文件")
    parser.add_argument("--quiet", action="store_false", help="静默模式，不显示详细过程")

    args = parser.parse_args()

    # 初始化分析器
    try:
        analyzer = PRAnalysisLangChain()
        print("✅ PR分析器初始化成功（使用 LangChain）")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return 1

    try:
        # 分析PR
        if args.pr:
            print(f"\n🔍 正在分析 PR #{args.pr}...")
        else:
            print(f"\n🔍 正在分析最新PR...")

        result = analyzer.analyze_pr(pr_number=args.pr, verbose=not args.quiet)

        # 打印结果
        print(f"\n{'='*80}")
        if result["success"]:
            print(f"✅ 分析完成于: {result['analyzed_at']}")
            print(f"PR #{result['pr_number']}: {result['pr_title']}")
            print(f"\n📋 分析结果:")
            print(f"{'-'*60}")
            print(result["analysis"][0]["text"])
        else:
            print(f"❌ 分析失败: {result['error']}")
        print(f"\n{'='*80}")

        # 输出结果到文件
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"\n📁 结果已保存到: {args.output}")
            except Exception as e:
                print(f"\n❌ 保存文件失败: {e}")

        return 0 if result["success"] else 1

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
        return 1
    except Exception as e:
        print(f"\n❌ 执行过程中出现错误: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        analyzer.close()


if __name__ == "__main__":
    import sys

    sys.exit(main())
