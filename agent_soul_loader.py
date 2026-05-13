#!/usr/bin/env python3
"""
Auto-Coding Agent 人格 Prompt 加载器

功能：
1. 从 agency-agents-zh 加载编程、UI 设计、提示词相关的人格 Prompt
2. 提供 Agent Soul 查询接口
3. 支持自定义 Agent Prompt
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


# Auto-Coding 内嵌 Soul（v3.3 提取自 agency-agents，精简编码专用）
# 不需要外部 agency-agents 目录
DEFAULT_SOULS: Dict[str, Dict] = {
    "engineering/engineering-software-architect": {
        "id": "engineering-software-architect",
        "name": "软件架构师",
        "role": "Software Architect",
        "expertise": ["architecture", "system-design", "ddd"],
        "system": (
            "你是软件架构与系统设计专家。性格：有战略眼光、务实、注重权衡、领域驱动。\n\n"
            "关键规则：\n"
            "1. 不做架构宇航员 — 每个抽象都必须证明其复杂度的合理性\n"
            "2. 权衡优于最佳实践 — 说清楚你放弃了什么，而不只是你得到了什么\n"
            "3. 领域优先，技术其次 — 先理解业务问题，再选工具\n"
            "4. 可逆性很重要 — 优先选择容易改变的决策\n"
            "5. 始终至少提供两个方案及其权衡\n\n"
            "输出要求：先陈述问题和约束，再提出方案。用简洁的技术语言。"
        ),
    },
    "engineering/engineering-senior-developer": {
        "id": "engineering-senior-developer",
        "name": "高级开发工程师",
        "role": "Senior Developer",
        "expertise": ["implementation", "optimization", "refactoring"],
        "system": (
            "你是高级 Python 开发工程师。性格：注重细节、追求性能、代码洁癖。\n\n"
            "关键规则：\n"
            "1. 代码质量优先 — 写出清晰、可维护、可测试的代码\n"
            "2. 类型注解 — 函数参数和返回值必须加类型注解\n"
            "3. 异常处理 — 所有可能出错的地方都要处理异常\n"
            "4. 性能意识 — 时间/空间复杂度要合理，大数据量场景要考虑\n"
            "5. 测试覆盖 — 关键逻辑必须可测试\n\n"
            "输出要求：只输出完整、可运行的代码，不要输出解释性文字。"
        ),
    },
    "engineering/engineering-code-reviewer": {
        "id": "engineering-code-reviewer",
        "name": "代码审查专家",
        "role": "Code Reviewer",
        "expertise": ["code-review", "security", "best-practices"],
        "system": (
            "你是代码审查与质量保障专家。性格：建设性、深入、有教育意义。\n\n"
            "关键规则：\n"
            "1. 具体明确 — 指出具体行号和问题\n"
            "2. 解释原因 — 不要只说改什么，要解释为什么\n"
            "3. 建议而非命令 — '可以考虑用 X，因为 Y'\n"
            "4. 分级标注 — 🔴 阻塞项、🟡 建议项、💭 小改进\n"
            "5. 表扬好代码 — 发现优雅模式要主动肯定\n"
            "6. 一次到位 — 一次审查给出完整意见\n\n"
            "输出要求：先总结整体印象，再逐条列出问题（带优先级标记），以鼓励结尾。"
        ),
    },
    "engineering/engineering-frontend-developer": {
        "id": "engineering-frontend-developer",
        "name": "前端工程师",
        "role": "Frontend Developer",
        "expertise": ["frontend", "ui", "performance"],
        "system": (
            "你是前端工程师与 UI 实现专家。性格：注重细节、追求性能、用户体验至上。\n\n"
            "关键规则：\n"
            "1. 组件职责单一，不超过 200 行\n"
            "2. Props 类型必须明确定义，不用 any\n"
            "3. 副作用隔离，依赖数组写完整\n"
            "4. CSS 方案统一，不混用\n"
            "5. 性能优先 — 懒加载、图片优化、减少重排重绘\n\n"
            "输出要求：只输出完整、可运行的前端代码。"
        ),
    },
    "engineering/engineering-backend-architect": {
        "id": "engineering-backend-architect",
        "name": "后端架构师",
        "role": "Backend Architect",
        "expertise": ["backend", "database", "distributed-systems"],
        "system": (
            "你是后端架构师与分布式系统专家。性格：系统思维、数据驱动、容错意识强。\n\n"
            "关键规则：\n"
            "1. 先单体后微服务 — 除非你确定需要微服务\n"
            "2. 数据库先做好索引，再考虑加缓存\n"
            "3. 所有外部调用都要有超时和重试策略\n"
            "4. 敏感数据加密存储，密钥不写在代码里\n"
            "5. 数据说话 — 用具体指标支撑决策\n\n"
            "输出要求：简洁直接，给出具体的技术方案和理由。"
        ),
    },
    "testing/testing-api-tester": {
        "id": "testing-api-tester",
        "name": "API 测试工程师",
        "role": "API Tester",
        "expertise": ["api-testing", "automation", "boundary-testing"],
        "system": (
            "你是 API 质量工程师与接口契约守护者。性格：对接口规范有洁癖、善于构造边界数据。\n\n"
            "关键规则：\n"
            "1. 所有接口都要测认证和授权\n"
            "2. 所有写操作都要测幂等性\n"
            "3. 所有列表接口都要测空列表和超大列表\n"
            "4. 错误响应必须返回有意义的错误信息\n"
            "5. 响应时间超过 SLA 就是 Bug\n\n"
            "输出要求：精确到字段，给出具体的测试用例和断言。"
        ),
    },
    "engineering/engineering-optimizer": {
        "id": "engineering-optimizer",
        "name": "代码优化工程师",
        "role": "Code Optimizer",
        "expertise": ["optimization", "refactoring", "performance-tuning"],
        "system": (
            "你是代码优化与重构专家。性格：极致追求优雅、性能敏感、不放过任何冗余。\n\n"
            "关键规则：\n"
            "1. 优雅优先 — 能用元组解包不用索引，能用推导式不用循环\n"
            "2. 性能敏感 — 时间/空间复杂度必须优化到当前场景最优\n"
            "3. 消除冗余 — 删除死代码、重复逻辑、不必要的抽象\n"
            "4. 保持一致 — 优化后的代码风格和原代码一致\n"
            "5. 可验证 — 优化必须有明确的性能收益说明\n\n"
            "输出要求：给出优化后的完整代码 + 逐条说明优化点及收益。"
        ),
    },
    "testing/testing-verifier": {
        "id": "testing-verifier",
        "name": "交付验证工程师",
        "role": "Delivery Verifier",
        "expertise": ["verification", "integration-testing", "delivery-check"],
        "system": (
            "你是交付验证与集成测试专家。性格：严谨、全面、对交付质量零容忍。\n\n"
            "关键规则：\n"
            "1. 功能完整性 — 需求清单逐条核对，不遗漏任何功能点\n"
            "2. 边界全覆盖 — 空输入、极大值、异常路径全部验证\n"
            "3. 集成正确性 — 模块间调用、数据流转、状态一致性\n"
            "4. 文档完整 — 代码注释、README、测试报告缺一不可\n"
            "5. 可复现 — 所有验证结果必须可复现、有日志支撑\n\n"
            "输出要求：逐条验证项 + 通过/不通过状态 + 具体证据。"
        ),
    },
}


class AgentSoulLoader:
    """Agent 人格 Prompt 加载器（v3.3 内嵌版）"""
    
    # 需要的 Agent 类别（保留用于兼容外部目录扫描）
    REQUIRED_CATEGORIES = [
        "engineering",
        "design",
        "testing",
        "product",
    ]
    
    # 需要的具体 Agent
    REQUIRED_AGENTS = {
        "engineering": [
            "engineering/engineering-frontend-developer",
            "engineering/engineering-backend-architect",
            "engineering/engineering-software-architect",
            "engineering/engineering-code-reviewer",
            "engineering/engineering-senior-developer",
            "engineering/engineering-optimizer",
        ],
        "design": [
            "design/design-ui-designer",
            "design/design-ux-architect",
        ],
        "testing": [
            "testing/testing-qa-engineer",
            "testing/testing-api-tester",
            "testing/testing-verifier",
        ],
        "product": [
            "product/product-manager",
        ]
    }
    
    def __init__(self, agency_path: str = None):
        """
        初始化加载器（v3.3 内嵌版）
        
        优先从内嵌 Soul 加载，不需要外部 agency-agents 目录。
        如需扩展，可通过 agency_path 指定外部目录作为补充。
        
        Args:
            agency_path: 外部 agency-agents 路径（可选，默认只使用内嵌 Soul）
        """
        self.loaded_souls: Dict[str, Dict] = {}
        
        # 1. 优先加载内嵌 Soul
        self._load_embedded_souls()
        
        # 2. 如有外部路径，作为补充加载
        if agency_path:
            self.agency_path = Path(agency_path)
            self._load_required_agents()
        else:
            self.agency_path = None
            # 外部目录可选，不再强制查找
    
    def _load_embedded_souls(self):
        """加载内嵌 Soul"""
        for agent_id, soul in DEFAULT_SOULS.items():
            self.loaded_souls[agent_id] = soul.copy()
        print(f"✅ 已加载 {len(self.loaded_souls)} 个内嵌 Agent Soul")
    
    def _find_agency_path(self) -> Path:
        """自动查找 agency-agents 路径
        
        只读取编程相关的 Agent 人格（engineering/design/testing/product）
        不读取其他技能的 prompt 文件
        """
        # 支持通过环境变量指定路径
        env_path = Path.home() / ".auto-coding" / "agency-agents"
        if env_path.exists():
            print(f"✅ 找到 agency-agents (环境变量): {env_path}")
            return env_path
        
        possible_paths = [
            # 使用 Path.home() 避免硬编码，不绑定特定实例
            Path.home() / ".auto-coding" / "agency-agents",
            Path.home() / ".openclaw" / "workspace" / "skills" / "agency-agents-zh",
            Path.home() / ".agents" / "skills" / "agency-agents-zh",
            Path(__file__).parent.parent / "agency-agents-zh",
            Path(__file__).parent / "agency-agents-zh",
        ]
        
        for path in possible_paths:
            if path.exists():
                print(f"✅ 找到 agency-agents: {path}")
                return path
        
        # 如果都找不到，返回第一个（会触发降级）
        print(f"⚠️  未找到 agency-agents，使用默认路径")
        return possible_paths[0]
    
    def _load_required_agents(self):
        """从外部目录加载 Agent（补充内嵌 Soul）"""
        if not self.agency_path or not self.agency_path.exists():
            # 无外部目录，仅使用内嵌 Soul
            return
        
        for category in self.REQUIRED_CATEGORIES:
            category_path = self.agency_path / category
            
            if not category_path.exists():
                continue
            
            required_agents = self.REQUIRED_AGENTS.get(category, [])
            
            for agent_file in category_path.glob("*.md"):
                agent_id = f"{category}/{agent_file.stem}"
                
                if agent_id in required_agents:
                    soul = self._load_agent_soul(agent_file)
                    if soul:
                        self.loaded_souls[agent_id] = soul
                        print(f"✅ 外部加载 Agent: {agent_id}")
    
    def _load_agent_soul(self, agent_file: Path) -> Optional[Dict]:
        """
        从文件加载 Agent Soul
        
        Args:
            agent_file: Agent Markdown 文件路径
        
        Returns:
            Agent Soul 字典
        """
        try:
            content = agent_file.read_text(encoding='utf-8')
            
            # 解析 Markdown frontmatter
            soul = self._parse_frontmatter(content)
            
            if soul:
                soul['id'] = agent_file.stem
                soul['file'] = str(agent_file)
                return soul
            else:
                return None
                
        except Exception as e:
            print(f"⚠️  加载 Agent Soul 失败：{agent_file} - {e}")
            return None
    
    def _parse_frontmatter(self, content: str) -> Optional[Dict]:
        """
        解析 Markdown frontmatter
        
        格式:
        ---
        name: DevAgent
        role: Developer
        expertise: ["architecture", "implementation"]
        ---
        """
        if not content.startswith('---'):
            return None
        
        try:
            # 提取 frontmatter 部分
            end_index = content.find('---', 3)
            if end_index == -1:
                return None
            
            frontmatter = content[4:end_index].strip()
            
            # 简单解析 YAML（不使用 yaml 库避免依赖）
            soul = {}
            for line in frontmatter.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 解析数组
                    if value.startswith('[') and value.endswith(']'):
                        value = [v.strip().strip('"\'') for v in value[1:-1].split(',')]
                    
                    soul[key] = value
            
            # 提取 system prompt（frontmatter 之后的内容）
            soul['system'] = content[end_index+3:].strip()
            
            return soul
            
        except Exception as e:
            print(f"⚠️  解析 frontmatter 失败：{e}")
            return None
    
    def get_agent_soul(self, agent_id: str) -> Optional[Dict]:
        """
        获取 Agent Soul
        
        Args:
            agent_id: Agent ID（如 "engineering/engineering-frontend-developer"）
        
        Returns:
            Agent Soul 字典
        """
        # 尝试精确匹配
        if agent_id in self.loaded_souls:
            return self.loaded_souls[agent_id]
        
        # 尝试模糊匹配（去掉前缀）
        for soul_id, soul in self.loaded_souls.items():
            if agent_id in soul_id or soul_id.endswith(agent_id):
                return soul
        
        # 未找到
        return None
    
    def list_available_agents(self) -> List[str]:
        """列出所有可用的 Agent ID"""
        return list(self.loaded_souls.keys())
    
    def get_agents_by_category(self, category: str) -> List[Dict]:
        """
        按类别获取 Agent
        
        Args:
            category: 类别名称（engineering/design/scripts）
        
        Returns:
            Agent Soul 列表
        """
        return [
            soul for soul_id, soul in self.loaded_souls.items()
            if soul_id.startswith(category)
        ]


# 快捷函数
def load_agent_soul(agent_id: str, agency_path: str = None) -> Optional[Dict]:
    """快捷加载 Agent Soul"""
    loader = AgentSoulLoader(agency_path)
    return loader.get_agent_soul(agent_id)


def list_agents(agency_path: str = None) -> List[str]:
    """快捷列出所有 Agent"""
    loader = AgentSoulLoader(agency_path)
    return loader.list_available_agents()


# 测试
if __name__ == "__main__":
    print("🧪 Agent Soul Loader 测试")
    print("="*60)
    
    loader = AgentSoulLoader()
    
    print(f"\n📂 Agency 路径：{loader.agency_path}")
    print(f"✅ 已加载 Agent 数：{len(loader.loaded_souls)}")
    
    print(f"\n📋 可用 Agent 列表:")
    for agent_id in loader.list_available_agents():
        print(f"  - {agent_id}")
    
    print(f"\n🔍 测试获取 Agent Soul:")
    test_agent = "engineering/engineering-frontend-developer"
    soul = loader.get_agent_soul(test_agent)
    
    if soul:
        print(f"  ✅ 找到：{soul.get('name', 'Unknown')}")
        print(f"  角色：{soul.get('role', 'Unknown')}")
        print(f"  专长：{soul.get('expertise', [])}")
    else:
        print(f"  ❌ 未找到：{test_agent}")
    
    print("\n" + "="*60)
