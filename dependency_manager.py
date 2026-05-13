"""
依赖管理器 - 自主编码 Agent 核心组件
Dependency Manager for Autonomous Coding Agent

P1 修复：实现完整的任务依赖性管理
- 依赖图构建
- 拓扑排序
- 环检测
- 并行任务调度
"""

import json
import fcntl
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, deque
from contextlib import contextmanager

# 配置日志
logger = logging.getLogger(__name__)


class DependencyManager:
    """依赖管理器 - 负责任务依赖关系的构建和解析"""
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.dependency_file = self.project_dir / "dependency_graph.json"
        self._lock_path = self.project_dir / ".dependency_lock"
    
    @contextmanager
    def _file_lock(self):
        """文件锁上下文管理器"""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, 'w') as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    
    def build_dependency_graph(self, tasks: List[Dict]) -> Dict:
        """
        构建任务依赖图
        
        Args:
            tasks: 任务列表，每个任务包含 id, name, depends_on 字段
        
        Returns:
            依赖图字典 {node_id: [依赖的节点 ID 列表]}
        """
        graph = defaultdict(list)
        nodes = set()
        
        for task in tasks:
            task_id = task.get('id')
            depends_on = task.get('depends_on', [])
            
            nodes.add(task_id)
            
            # 验证依赖关系
            if depends_on:
                if not isinstance(depends_on, list):
                    logger.warning(f"任务 {task_id} 的 depends_on 不是列表，已转换为列表")
                    depends_on = [depends_on]
                
                for dep_id in depends_on:
                    if not isinstance(dep_id, int):
                        logger.warning(f"任务 {task_id} 的依赖 ID {dep_id} 不是整数，已跳过")
                        continue
                    graph[task_id].append(dep_id)
                    nodes.add(dep_id)
        
        # 确保所有节点都在图中
        for node in nodes:
            if node not in graph:
                graph[node] = []
        
        dependency_data = {
            'graph': dict(graph),
            'nodes': list(nodes),
            'created_at': datetime.now().isoformat()
        }
        
        # 保存到文件
        self._save_dependency_graph(dependency_data)
        
        logger.info(f"构建依赖图完成：{len(nodes)} 个节点，{sum(len(v) for v in graph.values())} 条边")
        return dependency_data
    
    def _save_dependency_graph(self, data: Dict):
        """保存依赖图到文件"""
        with self._file_lock():
            try:
                with open(self.dependency_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.debug("依赖图已保存到文件")
            except Exception as e:
                logger.error(f"保存依赖图失败：{e}")
    
    def load_dependency_graph(self) -> Optional[Dict]:
        """加载依赖图"""
        with self._file_lock():
            if not self.dependency_file.exists():
                logger.debug("依赖图文件不存在")
                return None
            
            try:
                with open(self.dependency_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"加载依赖图成功：{len(data.get('nodes', []))} 个节点")
                return data
            except Exception as e:
                logger.error(f"加载依赖图失败：{e}")
                return None
    
    def topological_sort(self, graph: Dict = None) -> Optional[List[int]]:
        """
        拓扑排序 - 确定任务执行顺序（Kahn 算法）
        
        Args:
            graph: 依赖图 {task_id: [依赖的 task_id 列表]}
                   注意：graph[A] = [B] 表示 A 依赖于 B，B 必须先执行
        
        Returns:
            任务执行顺序列表，如果有环则返回 None
        """
        if graph is None:
            data = self.load_dependency_graph()
            if data is None:
                return None
            graph = data.get('graph', {})
        
        # 统一转换为整数 ID
        int_graph = {}
        for node, deps in graph.items():
            node_int = int(node) if isinstance(node, str) else node
            int_graph[node_int] = [int(d) if isinstance(d, str) else d for d in deps]
        
        # 收集所有节点
        all_nodes = set(int_graph.keys())
        for deps in int_graph.values():
            all_nodes.update(deps)
        
        # 计算入度（有多少任务依赖这个任务）
        in_degree = {node: 0 for node in all_nodes}
        for node, deps in int_graph.items():
            for dep in deps:
                in_degree[node] += 1
        
        # 初始化队列（入度为 0 的节点，即没有依赖的任务）
        queue = deque([node for node in all_nodes if in_degree[node] == 0])
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            # 找到所有依赖当前节点的节点，减少它们的入度
            for other_node, deps in int_graph.items():
                if node in deps:
                    in_degree[other_node] -= 1
                    if in_degree[other_node] == 0:
                        queue.append(other_node)
        
        # 检查是否有环
        if len(result) != len(all_nodes):
            logger.warning(f"检测到循环依赖！已排序 {len(result)} 个节点，共 {len(all_nodes)} 个节点")
            return None
        
        logger.info(f"拓扑排序完成：{len(result)} 个任务 - {result}")
        return result
    
    def detect_cycle(self, graph: Dict = None) -> bool:
        """
        检测依赖图中是否有环（三色标记法）
        
        Args:
            graph: 依赖图（可选，默认从文件加载）
                   注意：graph[A] = [B] 表示 A 依赖于 B
        
        Returns:
            True 表示有环，False 表示无环
        """
        if graph is None:
            data = self.load_dependency_graph()
            if data is None:
                return False
            graph = data.get('graph', {})
        
        # 统一转换为整数 ID
        int_graph = {}
        for node, deps in graph.items():
            node_int = int(node) if isinstance(node, str) else node
            int_graph[node_int] = [int(d) if isinstance(d, str) else d for d in deps]
        
        # 使用三色标记法检测环
        WHITE, GRAY, BLACK = 0, 1, 2
        color = defaultdict(int)  # 默认为 WHITE
        
        # 收集所有节点
        all_nodes = set(int_graph.keys())
        for deps in int_graph.values():
            all_nodes.update(deps)
        
        def dfs(node):
            color[node] = GRAY  # 标记为正在访问
            
            for neighbor in int_graph.get(node, []):
                if color[neighbor] == GRAY:
                    # 发现后向边，存在环
                    return True
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            
            color[node] = BLACK  # 标记为已完成
            return False
        
        # 遍历所有节点
        for node in all_nodes:
            if color[node] == WHITE:
                if dfs(node):
                    logger.warning("检测到循环依赖")
                    return True
        
        logger.info("依赖图无环")
        return False
    
    def get_parallel_tasks(self, graph: Dict = None, completed_tasks: Set[int] = None) -> List[int]:
        """
        获取当前可以并行执行的任务
        
        Args:
            graph: 依赖图（可选，默认从文件加载）
            completed_tasks: 已完成的任务 ID 集合
        
        Returns:
            可以并行执行的任务 ID 列表
        """
        if graph is None:
            data = self.load_dependency_graph()
            if data is None:
                return []
            graph = data.get('graph', {})
        
        if completed_tasks is None:
            completed_tasks = set()
        
        # 统一转换为整数 ID
        int_graph = {}
        for node, deps in graph.items():
            node_int = int(node) if isinstance(node, str) else node
            int_graph[node_int] = [int(d) if isinstance(d, str) else d for d in deps]
        
        # 获取所有未完成的节点
        all_nodes = set(int_graph.keys())
        for deps in int_graph.values():
            all_nodes.update(deps)
        
        pending_tasks = all_nodes - completed_tasks
        
        # 找出依赖都已完成的任务
        parallel_tasks = []
        for task_id in pending_tasks:
            dependencies = set(int_graph.get(task_id, []))
            if dependencies.issubset(completed_tasks):
                parallel_tasks.append(task_id)
        
        logger.info(f"可并行执行的任务：{len(parallel_tasks)} 个 - {parallel_tasks}")
        return parallel_tasks
    
    def get_task_dependencies(self, task_id: int, graph: Dict = None) -> List[int]:
        """
        获取任务的所有依赖（包括间接依赖）
        
        Args:
            task_id: 任务 ID
            graph: 依赖图（可选，默认从文件加载）
        
        Returns:
            所有依赖任务的 ID 列表
        """
        if graph is None:
            data = self.load_dependency_graph()
            if data is None:
                return []
            graph = data.get('graph', {})
        
        dependencies = []
        queue = deque([task_id])
        visited = {task_id}
        
        while queue:
            current = queue.popleft()
            for dep in graph.get(current, []):
                if dep not in visited:
                    visited.add(dep)
                    dependencies.append(dep)
                    queue.append(dep)
        
        logger.debug(f"任务 {task_id} 的依赖：{dependencies}")
        return dependencies
    
    def validate_dependency_graph(self, tasks: List[Dict]) -> Tuple[bool, str]:
        """
        验证依赖图的有效性
        
        Args:
            tasks: 任务列表
        
        Returns:
            (是否有效，错误信息)
        """
        # 1. 构建依赖图
        dependency_data = self.build_dependency_graph(tasks)
        graph = dependency_data['graph']
        
        # 2. 检查是否有环
        if self.detect_cycle(graph):
            return False, "检测到循环依赖，请检查任务依赖关系"
        
        # 3. 检查依赖的任务是否存在
        all_task_ids = {task.get('id') for task in tasks}
        for task in tasks:
            task_id = task.get('id')
            depends_on = task.get('depends_on', [])
            
            if depends_on:
                for dep_id in depends_on:
                    if dep_id not in all_task_ids:
                        return False, f"任务 {task_id} 依赖不存在的任务 {dep_id}"
        
        # 4. 检查拓扑排序是否成功
        if self.topological_sort(graph) is None:
            return False, "拓扑排序失败，依赖关系存在问题"
        
        logger.info("依赖图验证通过")
        return True, "依赖图有效"


# 测试代码
if __name__ == "__main__":
    import asyncio
    
    async def test_dependency_manager():
        """测试依赖管理器"""
        print("🧪 依赖管理器测试")
        print("="*60)
        
        # 创建测试目录
        test_dir = Path("/tmp/test-dependency")
        test_dir.mkdir(parents=True, exist_ok=True)
        
        dm = DependencyManager(str(test_dir))
        
        # 测试 1: 简单依赖图
        print("\n✅ 测试 1: 简单依赖图")
        tasks = [
            {"id": 1, "name": "初始化项目", "depends_on": []},
            {"id": 2, "name": "安装依赖", "depends_on": [1]},
            {"id": 3, "name": "编写代码", "depends_on": [2]},
            {"id": 4, "name": "运行测试", "depends_on": [3]},
        ]
        
        result = dm.validate_dependency_graph(tasks)
        print(f"  验证结果：{result}")
        assert result[0] == True, "依赖图验证失败"
        
        # 测试 2: 拓扑排序
        print("\n✅ 测试 2: 拓扑排序")
        sort_result = dm.topological_sort()
        print(f"  排序结果：{sort_result}")
        assert sort_result == [1, 2, 3, 4], "拓扑排序错误"
        
        # 测试 3: 环检测
        print("\n✅ 测试 3: 环检测")
        has_cycle = dm.detect_cycle()
        print(f"  是否有环：{has_cycle}")
        assert has_cycle == False, "错误检测到环"
        
        # 测试 4: 循环依赖
        print("\n✅ 测试 4: 循环依赖检测")
        circular_tasks = [
            {"id": 1, "name": "任务 A", "depends_on": [3]},
            {"id": 2, "name": "任务 B", "depends_on": [1]},
            {"id": 3, "name": "任务 C", "depends_on": [2]},
        ]
        
        dm2 = DependencyManager(str(test_dir / "circular"))
        result2 = dm2.validate_dependency_graph(circular_tasks)
        print(f"  验证结果：{result2}")
        assert result2[0] == False, "未检测到循环依赖"
        
        # 测试 5: 并行任务
        print("\n✅ 测试 5: 并行任务")
        parallel_tasks = [
            {"id": 1, "name": "任务 A", "depends_on": []},
            {"id": 2, "name": "任务 B", "depends_on": []},
            {"id": 3, "name": "任务 C", "depends_on": [1, 2]},
        ]
        
        dm3 = DependencyManager(str(test_dir / "parallel"))
        dm3.build_dependency_graph(parallel_tasks)
        
        # 初始可以并行执行的任务
        parallel = dm3.get_parallel_tasks(completed_tasks=set())
        print(f"  初始并行任务：{parallel}")
        assert set(parallel) == {1, 2}, "初始并行任务错误"
        
        # 完成任务 1 后可以并行的任务
        parallel = dm3.get_parallel_tasks(completed_tasks={1})
        print(f"  完成任务 1 后并行任务：{parallel}")
        assert parallel == [2], "并行任务错误"
        
        # 完成任务 1 和 2 后可以并行的任务
        parallel = dm3.get_parallel_tasks(completed_tasks={1, 2})
        print(f"  完成任务 1,2 后并行任务：{parallel}")
        assert parallel == [3], "并行任务错误"
        
        # 清理
        import shutil
        shutil.rmtree(test_dir)
        
        print("\n" + "="*60)
        print("🎉 所有依赖管理器测试通过！")
        print("="*60)
    
    asyncio.run(test_dependency_manager())
