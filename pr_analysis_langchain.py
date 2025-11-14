#!/usr/bin/env python3
"""
使用 LangChain 实现 PR 分析
集成 LangChain 的工具和 Agent 能力
"""
import asyncio
import json
import subprocess
import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool, StructuredTool
from langchain_anthropic import ChatAnthropic
from langchain.callbacks.base import BaseCallbackHandler
from pydantic import BaseModel, Field

from config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, DEFAULT_IOTDB_SOURCE_DIR
from database import DatabaseManager
from pr_analysis_common import (
    build_analysis_query,
    get_pr_by_number,
    get_tool_system_prompt,
)


class ThinkingCallbackHandler(BaseCallbackHandler):
    """自定义回调处理器：只显示 Claude 的思考过程（文本输出）"""

    def __init__(self):
        super().__init__()
        self.thinking_text = ""  # 累积思考内容

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """LLM 开始时调用"""
        pass

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """累积思考内容，不打印"""
        if isinstance(token, str):
            self.thinking_text += token
        elif isinstance(token, list):
            text_parts = [
                item["text"]
                for item in token
                if isinstance(item, dict) and item.get("type") == "text"
            ]

            if text_parts:
                self.thinking_text += "".join(text_parts)
        else:
            self.thinking_text += str(token)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """LLM 结束时调用"""
        pass

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """工具开始时打印之前累积的思考内容"""
        if self.thinking_text:
            print(self.thinking_text, flush=True)
            self.thinking_text = ""  # 清空，准备下一轮

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """工具结束执行时调用"""
        print()

    def on_agent_action(self, action: Any, **kwargs: Any) -> None:
        """Agent 执行动作时调用"""
        pass

    def on_agent_finish(self, finish: Any, **kwargs: Any) -> None:
        """Agent 完成时调用"""
        pass


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
        default="",
        description="搜索路径，相对于 IoTDB 源码根目录（可选，默认为根目录）",
    )


class GrepInput(BaseModel):
    """Grep 搜索的输入参数"""

    pattern: str = Field(description="搜索模式（正则表达式）")
    path: str = Field(
        default="", description="搜索路径，相对于 IoTDB 源码根目录（可选）"
    )
    file_type: str = Field(
        default="", description="文件类型过滤（如 'java', 'py', 'xml'）（可选）"
    )


class FindInput(BaseModel):
    """Find 查找文件的输入参数"""

    pattern: str = Field(
        description="文件名模式（支持通配符 * 和 ?，如 '*Operator.java', 'test_*.py'）",
        alias="name",
    )
    path: str = Field(
        default="",
        description="搜索路径，相对于 IoTDB 源码根目录（可选，默认为根目录）",
    )
    file_type: str = Field(
        default="f",
        description="文件类型：'f' 表示普通文件（默认），'d' 表示目录",
    )


class GitInput(BaseModel):
    """Git 命令的输入参数"""

    command: str = Field(
        description="要执行的 git 命令（纯git命令，不支持管道和重定向，如 'git status', 'git log', 'git diff HEAD~1'）"
    )


class PRAnalysisLangChain:
    """使用 LangChain 实现的 PR 分析器"""

    def __init__(self, iotdb_source_dir: str = DEFAULT_IOTDB_SOURCE_DIR):
        """
        初始化 PR 分析器

        Args:
            iotdb_source_dir: IoTDB 源码目录路径
        """
        self.db = DatabaseManager()
        self.iotdb_source_dir = Path(iotdb_source_dir)

        # 初始化 LangChain 聊天模型（启用流式输出）
        self.llm = ChatAnthropic(
            model="glm-4.6",
            # model="claude-sonnet-4-5-20250929",
            temperature=0.3,
            max_tokens=16384,
            base_url=ANTHROPIC_BASE_URL,
            api_key=ANTHROPIC_API_KEY,
        )

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
            # 参数验证
            if not file_path or not file_path.strip():
                error_msg = "错误: 必须提供 file_path 参数（文件路径不能为空）"
                print(f"❌ {error_msg}")
                return error_msg

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
                line_count = content.count("\n") + 1
                print(
                    f"📖 已读取文件: {file_path} ({file_size:,} 字符, {line_count:,} 行)"
                )

                # 返回完整内容给模型
                return content
            except Exception as e:
                print(f"❌ 读取文件失败: {file_path} - {str(e)}")
                return f"错误: 读取文件失败: {str(e)}"

        return StructuredTool.from_function(
            func=read_file,
            name="read",
            description=(
                "读取 IoTDB 源码文件的完整内容。"
                "**必须提供 file_path 参数**，文件路径相对于 IoTDB 源码根目录。"
                "示例调用: {'file_path': 'iotdb-core/datanode/src/main/java/org/apache/iotdb/db/queryengine/execution/operator/process/TableIntoOperator.java'}"
            ),
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
            # 参数验证
            if not pattern or not pattern.strip():
                error_msg = "错误: 必须提供 pattern 参数（glob 模式不能为空）"
                print(f"❌ {error_msg}")
                return json.dumps({"success": False, "error": error_msg})

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
                print(
                    f"🔍 Glob 搜索 '{pattern}' {search_path} -> 找到 {len(relative_paths)} 个文件"
                )

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
            description=(
                "使用 glob 模式查找匹配的文件。支持 ** 通配符。"
                "**必须提供 pattern 参数**（如 '**/*.java', '**/*Operator*.java'）。"
                "path 参数可选，默认在 IoTDB 源码根目录搜索。"
                "示例调用: {'pattern': '**/*TableIntoOperator*.java'} 或 {'pattern': '*.xml', 'path': 'iotdb-core/datanode'}"
            ),
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
            # 参数验证（防御性编程）
            if not pattern or not pattern.strip():
                error_msg = "错误: 必须提供 pattern 参数（搜索模式不能为空）"
                print(f"❌ {error_msg}")
                return json.dumps({"success": False, "error": error_msg})

            try:
                search_dir = (
                    self.iotdb_source_dir / path if path else self.iotdb_source_dir
                )

                # 构建 rg (ripgrep) 命令
                cmd = ["rg", "--json", pattern, str(search_dir)]
                if file_type:
                    cmd.extend(["--type", file_type])

                # 执行搜索
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

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
            description=(
                "在 IoTDB 源码中搜索匹配的内容（使用正则表达式）。"
                "**必须提供 pattern 参数**（正则表达式模式）。"
                "path 和 file_type 参数可选，默认在整个源码目录搜索所有文件类型。"
                "示例调用: {'pattern': 'class.*TableIntoOperator'} 或 {'pattern': 'INSERT INTO', 'path': 'iotdb-core', 'file_type': 'java'}"
            ),
            args_schema=GrepInput,
        )

    def _create_find_tool(self) -> BaseTool:
        """创建 Find 查找文件工具"""

        def find_files(pattern: str, path: str = "", file_type: str = "f") -> str:
            """
            按文件名查找文件（类似 Unix find 命令）

            Args:
                pattern: 文件名模式（支持通配符 * 和 ?）
                path: 搜索路径（相对于 IoTDB 源码根目录）
                file_type: 文件类型（'f' 表示文件，'d' 表示目录）

            Returns:
                匹配的文件列表（JSON 格式）
            """
            # 参数验证（防御性编程）
            if not pattern or not pattern.strip():
                error_msg = "错误: 必须提供 pattern 参数（文件名模式不能为空）"
                print(f"❌ {error_msg}")
                return json.dumps({"success": False, "error": error_msg})

            try:
                search_dir = (
                    self.iotdb_source_dir / path if path else self.iotdb_source_dir
                )

                if not search_dir.exists():
                    print(f"❌ 搜索路径不存在: {path}")
                    return json.dumps(
                        {"success": False, "error": f"搜索路径不存在: {path}"}
                    )

                # 递归搜索所有文件/目录
                matches = []
                try:
                    if file_type == "d":
                        # 只查找目录
                        all_items = [p for p in search_dir.rglob("*") if p.is_dir()]
                    else:
                        # 只查找文件（默认）
                        all_items = [p for p in search_dir.rglob("*") if p.is_file()]

                    # 使用 fnmatch 过滤文件名
                    for item in all_items:
                        if fnmatch.fnmatch(item.name, pattern):
                            try:
                                rel_path = str(item.relative_to(self.iotdb_source_dir))
                                matches.append(rel_path)
                            except ValueError:
                                # 如果路径不在 iotdb_source_dir 下，跳过
                                continue

                        # 限制结果数量
                        if len(matches) >= 100:
                            break

                except Exception as e:
                    print(f"❌ 搜索过程出错: {str(e)}")
                    return json.dumps(
                        {"success": False, "error": f"搜索过程出错: {str(e)}"}
                    )

                # 控制台显示搜索结果
                search_info = f"模式: '{pattern}'"
                if path:
                    search_info += f", 路径: {path}"
                type_str = "目录" if file_type == "d" else "文件"
                print(
                    f"🔎 Find 搜索 {search_info} ({type_str}) -> 找到 {len(matches)} 个匹配"
                )

                result = {
                    "success": True,
                    "matches": matches,
                    "count": len(matches),
                }
                return json.dumps(result, ensure_ascii=False, indent=2)

            except Exception as e:
                print(f"❌ Find 搜索失败: {pattern} - {str(e)}")
                return json.dumps(
                    {"success": False, "error": f"Find 搜索失败: {str(e)}"}
                )

        return StructuredTool.from_function(
            func=find_files,
            name="find",
            description=(
                "按文件名查找文件（支持通配符 * 和 ?）。比 glob 更灵活，可以递归搜索整个目录树。"
                "**必须提供 pattern 参数**（文件名模式，如 '*Operator.java', 'test_*.py'）。"
                "path 和 file_type 参数可选，默认在整个源码目录搜索文件（不含目录）。"
                "示例调用: {'pattern': '*TableIntoOperator.java'} 或 {'pattern': 'pom.xml', 'path': 'iotdb-core'}"
            ),
            args_schema=FindInput,
        )

    def _create_git_tool(self) -> BaseTool:
        """创建 Git 执行工具（禁止管道、重定向等 shell 特性）"""

        def run_git(command: str) -> str:
            """
            执行安全的 git 命令（禁止管道和重定向）

            Args:
                command: 要执行的 git 命令（纯git命令，不支持管道和重定向）

            Returns:
                命令执行结果
            """
            try:
                # 基本验证
                cmd_stripped = command.strip()
                if not cmd_stripped:
                    print(f"❌ 命令为空")
                    return "错误: 命令为空"

                # 检查是否以 git 开头
                if not cmd_stripped.lower().startswith("git "):
                    print(f"❌ 只允许 git 命令, 当前命令 {cmd_stripped}")
                    return "错误: 只允许 git 命令"

                # 检查是否包含管道或重定向操作符
                shell_operators = ["|", ">", ">>", "<", "&&", "||", ";"]
                for operator in shell_operators:
                    if operator in cmd_stripped:
                        print(f"❌ Git 命令不允许包含 shell 操作符 '{operator}'")
                        return f"错误: Git 命令不允许包含 shell 操作符 '{operator}'。请使用纯 git 命令。"

                # 解析 git 命令
                cmd_parts = cmd_stripped.split()
                if len(cmd_parts) < 2:
                    print(f"❌ Git 命令不完整")
                    return "错误: Git 命令不完整"

                git_subcmd = cmd_parts[1].lower()

                # 允许的安全 git 命令（只读 + checkout）
                safe_git_commands = {
                    "checkout",
                    "status",
                    "log",
                    "show",
                    "diff",
                    "branch",
                    "rev-parse",
                    "ls-tree",
                    "ls-files",
                }

                # 危险命令黑名单
                dangerous_git_commands = {
                    "push",
                    "reset",
                    "clean",
                    "rm",
                    "commit",
                    "rebase",
                    "merge",
                    "pull",
                    "fetch",
                    "add",
                }

                if git_subcmd in dangerous_git_commands:
                    print(f"❌ 禁止执行危险的 git 命令: git {git_subcmd}")
                    return f"错误: 禁止执行危险的 git 命令: git {git_subcmd}"

                if git_subcmd not in safe_git_commands:
                    allowed_list = ", ".join(sorted(safe_git_commands))
                    print(f"❌ Git 命令 '{git_subcmd}' 不在允许列表中")
                    return f"错误: Git 命令 '{git_subcmd}' 不在允许列表中（允许: {allowed_list}）"

                # 额外的安全检查：防止命令注入
                dangerous_patterns = [
                    ";rm ",
                    ";curl ",
                    ";wget ",
                    "&&rm ",
                    "$(curl",
                    "`curl",
                    ";sh ",
                    ";bash ",
                ]
                cmd_lower = cmd_stripped.lower()
                for pattern in dangerous_patterns:
                    if pattern in cmd_lower:
                        print(f"❌ 检测到危险模式: {pattern}")
                        return f"错误: 检测到危险模式: {pattern}"

                # 使用 shell=False 执行命令（禁用管道、重定向等）
                result = subprocess.run(
                    cmd_parts,  # 使用列表形式，避免shell注入
                    shell=False,  # 禁用shell特性，提高安全性
                    cwd=str(self.iotdb_source_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                # 合并 stdout 和 stderr
                output = result.stdout
                if result.stderr:
                    output += "\n" + result.stderr

                # 控制台显示执行结果
                if result.returncode == 0:
                    print(f"✅ Git 命令执行成功: {cmd_stripped}")
                    # 只显示输出的前几行（避免刷屏）
                    output_lines = output.strip().split("\n")
                    if len(output_lines) > 5:
                        preview = "\n".join(output_lines[:5])
                        print(
                            f"   输出预览 (前5行):\n{preview}\n   ... (共 {len(output_lines)} 行)"
                        )
                    else:
                        print(f"   输出:\n{output.strip()}")
                else:
                    print(
                        f"❌ Git 命令执行失败 (退出码: {result.returncode}): {cmd_stripped}"
                    )

                # 返回完整输出给模型
                return (
                    output.strip()
                    if result.returncode == 0
                    else f"错误 (退出码 {result.returncode}): {output.strip()}"
                )

            except subprocess.TimeoutExpired:
                print(f"❌ 命令执行超时（30秒）: {command}")
                return "错误: 命令执行超时（30秒）"
            except Exception as e:
                print(f"❌ 命令执行失败: {command} - {str(e)}")
                return f"错误: 命令执行失败: {str(e)}"

        return StructuredTool.from_function(
            func=run_git,
            name="git",
            description=(
                "执行安全的 git 命令（禁止管道、重定向等 shell 特性）。在 IoTDB 源码目录中执行。"
                "\n\n**重要限制**："
                "\n- ❌ 不支持管道 (|)、重定向 (>, >>)、命令链接 (&&, ;) 等 shell 特性"
                "\n- ❌ 如果需要搜索 git 输出，请先使用 git 工具获取内容，然后使用 grep 工具搜索"
                "\n\n**允许的 git 子命令**："
                "\n- 只读命令：status, log, show, diff, branch, rev-parse, ls-tree, ls-files"
                "\n- git checkout（用于切换分支/提交）"
                "\n\n**禁止的危险命令**："
                "\n- push, reset, clean, rm, commit, rebase, merge, pull, fetch, add"
                "\n\n**示例调用**："
                "\n- {'command': 'git show HEAD~1:file.java'}"
                "\n- {'command': 'git checkout <commit_sha>'}"
                "\n- {'command': 'git log --oneline -5'}"
            ),
            args_schema=GitInput,
        )

    def _create_tools(self) -> List[BaseTool]:
        """创建所有工具"""
        return [
            self._create_read_tool(),
            self._create_glob_tool(),
            self._create_grep_tool(),
            # self._create_find_tool(),
            self._create_git_tool(),
        ]

    def get_pr_by_number(self, pr_number: Optional[int] = None) -> Optional[Dict]:
        """
        从数据库获取指定PR的数据，如果没有指定编号则获取最新的PR
        """
        return get_pr_by_number(pr_number, self.db)

    async def analyze_pr(
        self, pr_number: Optional[int] = None, enable_tools: bool = True
    ) -> Dict:
        """
        使用 LangChain Agent 分析 PR

        Args:
            pr_number: PR编号，如果为None则分析最新的PR
            enable_tools: 是否启用工具调用（read, glob, grep）（默认 True）

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
        print(f"🔍 正在分析 PR #{pr_number}: {pr_title}")

        try:
            # 获取 diff 内容
            diff_content = target_pr.get("diff_content", "")
            diff_size = len(diff_content) if diff_content else 0
            print(f"📦 Diff 大小: {diff_size:,} 字符 (~{diff_size // 4:,} tokens)")

            # 构建分析提示（使用 pr_analysis_common 中的函数）
            analysis_prompt = build_analysis_query(target_pr, diff_content)
            print(f"📊 完整查询大小: {len(analysis_prompt):,} 字符")

            # 构建系统提示（使用公共函数）
            system_prompt = (
                get_tool_system_prompt()
                if enable_tools
                else "您是一名时序数据库IoTDB专家，请根据提供的PR信息和本地iotdb源码进行分析，然后提供详细的分析结果。"
            )

            print(f"🚀 正在使用 LangChain Agent 进行分析...")
            print(
                f"   工具支持: {'启用 (read, glob, grep, git)' if enable_tools else '禁用'}"
            )
            print("\n=== Claude 分析结果 ===\n")

            # 创建 Agent 提示模板
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("human", "{input}"),
                    MessagesPlaceholder(variable_name="agent_scratchpad"),
                ]
            )

            # 根据 enable_tools 决定是否使用工具
            tools = self._create_tools() if enable_tools else []

            # 创建 Agent
            agent = create_tool_calling_agent(self.llm, tools, prompt)

            # 创建回调处理器
            callback_handler = ThinkingCallbackHandler()

            # 创建 Agent 执行器
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=False,  # 关闭 LangChain 的详细日志
                max_iterations=50,
                handle_parsing_errors=True,
            )

            # 执行分析（使用回调来显示思考过程）
            result = agent_executor.invoke(
                {"input": analysis_prompt}, config={"callbacks": [callback_handler]}
            )

            # 获取分析结果
            analyze_output = result.get("output", "")

            # 如果是字符串，直接使用；如果是 list，提取文本
            if isinstance(analyze_output, str):
                analysis_result = analyze_output
            elif isinstance(analyze_output, list):
                analysis_result = ""
                for item in analyze_output:
                    if isinstance(item, dict) and item.get("type") == "text":
                        analysis_result += item["text"]
            else:
                analysis_result = str(analyze_output)

            print(f"\n=== 分析完成 ===\n")

            return {
                "success": True,
                "pr_number": pr_number,
                "pr_title": pr_title,
                "analysis": analysis_result,
                "analyzed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            error_msg = f"分析过程出错: {str(e)}"
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


async def main():
    """主函数"""
    analyzer = PRAnalysisLangChain()

    # 初始化分析器
    try:
        print("🚀 IoTDB PR 分析工具 (LongChain)")
        print("=" * 60)

        # 获取 PR 编号
        pr_number = 12879

        print("\n" + "=" * 60)
        print("🚀 开始PR分析 (使用 LongChain + 工具调用)...")

        result = await analyzer.analyze_pr(pr_number=pr_number, enable_tools=True)

        # 打印结果
        print(f"\n{'='*80}")
        if result["success"]:
            print(f"✅ 分析完成于: {result['analyzed_at']}")
            print(f"PR #{result['pr_number']}: {result['pr_title']}")
            print(f"\n📋 分析结果:")
            print(f"{'-'*60}")
            print(result["analysis"])
        else:
            print(f"❌ 分析失败: {result['error']}")
        print(f"\n{'='*80}")

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
    asyncio.run(main())
