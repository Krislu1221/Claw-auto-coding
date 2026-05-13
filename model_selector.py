#!/usr/bin/env python3
"""
RoundTable 模型选择器

功能：
1. 优先使用 OpenClaw 官方 API 获取可用模型（安全、审计友好）
2. 如果 API 不可用，降级到标准单一模型配置
3. 支持用户显式指定模型配置（最高优先级）

核心原则：
- 不读取任何包含敏感信息的配置文件
- 不接触 apiKey、baseUrl 等敏感字段
- 所有模型信息来自官方 API 或用户显式配置
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class ModelSelector:
    """RoundTable 模型选择器 - 安全、审计友好"""
    
    # 专家角色 - 模型标签映射（通用规则）
    ROLE_TAGS = {
        "engineering": ["code", "technical", "engineering", "coder"],
        "design": ["creative", "long-context", "design", "art"],
        "testing": ["balanced", "fast", "general", "qa"],
        "product": ["chinese", "knowledge", "product", "business"],
        "host": ["logic", "summary", "decision", "max"]
    }
    
    # 标准降级方案：MiMo 模型（xiaomimimo provider）
    FALLBACK_MODELS = [
        {
            'id': 'xiaomimimo/mimo-v2.5',
            'name': 'MiMo V2.5',
            'tags': ['code', 'technical', 'engineering', 'fast', 'fallback'],
            'priority': 3
        },
        {
            'id': 'xiaomimimo/mimo-v2.5-pro',
            'name': 'MiMo V2.5 Pro',
            'tags': ['code', 'technical', 'engineering', 'reasoning', 'fallback'],
            'priority': 4
        }
    ]
    
    def __init__(self, user_models: List[Dict] = None, config_path: str = None):
        """
        初始化模型选择器
        
        Args:
            user_models: 用户显式指定的模型列表（可选，最高优先级）
            config_path: 独立配置文件路径（可选，用于导入导出）
        """
        self.available_models: List[Dict] = []
        self.user_specified_models = user_models
        self.config_path = config_path
        self._load_available_models()
    
    def _load_available_models(self):
        """
        加载可用模型列表（按优先级）
        
        优先级：
        1. 用户显式指定（最高优先级）
        2. 环境变量 ROUNDTable_MODELS（次高优先级）
        3. OpenClaw 官方 API
        4. 标准单一模型配置（降级方案）
        """
        # 优先级 1: 用户显式指定
        if self.user_specified_models:
            self.available_models = self.user_specified_models
            print(f"✅ 使用用户显式指定的 {len(self.available_models)} 个模型")
            return
        
        # 优先级 2: 环境变量 ROUNDTable_MODELS
        # 格式："model1:tag1,tag2;model2:tag3,tag4"
        # 示例："bailian/glm-5:chinese;bailian/kimi-k2.5:creative"
        env_models = os.environ.get('ROUNDTable_MODELS')
        if env_models:
            parsed_models = []
            for item in env_models.split(';'):
                if ':' in item:
                    model_id, tags_str = item.split(':', 1)
                    parsed_models.append({
                        'id': model_id.strip(),
                        'name': model_id.strip().split('/')[-1],
                        'tags': [t.strip() for t in tags_str.split(',')],
                        'priority': 2
                    })
            
            if parsed_models:
                self.available_models = parsed_models
                print(f"✅ 从环境变量加载 {len(parsed_models)} 个模型")
                return
        
        # 优先级 3: OpenClaw 官方 API
        try:
            models = self._fetch_from_openclaw_api()
            if models:
                self.available_models = models
                print(f"✅ 从 OpenClaw API 获取到 {len(self.available_models)} 个模型")
                return
        except Exception as e:
            print(f"⚠️ OpenClaw API 不可用：{e}")
        
        # 优先级 4: MiMo 模型降级方案
        print("⚠️ 降级到 MiMo 模型配置")
        self.available_models = self.FALLBACK_MODELS
    
    def _fetch_from_openclaw_api(self) -> Optional[List[Dict]]:
        """
        从 OpenClaw 官方 API 获取可用模型
        
        Returns:
            模型列表，如果失败返回 None
        """
        try:
            # 尝试使用 OpenClaw 官方工具
            from openclaw.tools import get_available_models as openclaw_get_models
            models = openclaw_get_models()
            
            # 验证返回数据
            if models and isinstance(models, list) and len(models) > 0:
                # 确保每个模型都有必要字段
                validated_models = []
                for model in models:
                    if isinstance(model, dict) and 'id' in model:
                        validated_models.append({
                            'id': model.get('id', 'unknown'),
                            'name': model.get('name', model.get('id')),
                            'tags': model.get('tags', []),
                            'priority': model.get('priority', 3),
                            'provider': model.get('provider', 'unknown')
                        })
                
                if validated_models:
                    return validated_models
            
            return None
            
        except ImportError:
            print("⚠️ openclaw.tools 不可用")
            return None
        except Exception as e:
            print(f"⚠️ API 调用失败：{e}")
            return None
    
    def get_available_models(self) -> List[Dict]:
        """获取可用模型列表"""
        return self.available_models
    
    def select_model_for_role(self, role: str, user_specified: str = None) -> str:
        """
        为专家角色选择最合适的模型
        
        匹配逻辑：
        1. 用户显式指定 → 使用用户指定（最高优先级）
        2. 只有一个模型 → 直接使用（所有专家都用这个）
        3. 多个模型 → 根据标签匹配 + 优先级
        
        Args:
            role: 专家角色（engineering/design/testing/product/host）
            user_specified: 用户显式指定的模型（可选）
        
        Returns:
            模型 ID
        """
        # 优先级 1: 用户显式指定
        if user_specified:
            print(f"📌 使用用户指定模型：{user_specified}")
            return user_specified
        
        # 优先级 2: 只有一个模型，所有专家都用这个
        if len(self.available_models) == 1:
            model_id = self.available_models[0]['id']
            print(f"📌 单一模型配置，所有专家都使用：{model_id}")
            return model_id
        
        # 优先级 3: 多个模型，根据角色标签匹配
        role_tags = self.ROLE_TAGS.get(role, [])
        
        # 计算每个模型的匹配分数
        model_scores = []
        for model in self.available_models:
            score = 0
            
            # 标签匹配（每个标签 +10 分）
            for tag in role_tags:
                if tag in model.get('tags', []):
                    score += 10
            
            # 优先级加分
            priority = model.get('priority', 3)
            if priority == 1:
                score += 30
            elif priority == 2:
                score += 20
            else:
                score += 10
            
            model_scores.append((model['id'], score))
        
        # 按分数排序，返回最高分的模型
        model_scores.sort(key=lambda x: x[1], reverse=True)
        best_model = model_scores[0][0]
        
        print(f"📌 为角色 '{role}' 匹配模型：{best_model} (得分：{model_scores[0][1]})")
        return best_model
    
    def select_models_for_roundtable(self, roles: List[str], 
                                     user_specified: Dict[str, str] = None) -> Dict[str, str]:
        """
        为 RoundTable 所有专家选择模型
        
        Args:
            roles: 专家角色列表
            user_specified: 用户显式指定的模型字典 {role: model_id}
        
        Returns:
            模型分配字典 {role: model_id}
        """
        if user_specified is None:
            user_specified = {}
        
        model_assignment = {}
        
        for role in roles:
            specified = user_specified.get(role)
            model_id = self.select_model_for_role(role, specified)
            model_assignment[role] = model_id
        
        return model_assignment
    
    def print_model_summary(self):
        """打印模型配置摘要"""
        print("\n" + "="*60)
        print("📊 RoundTable 模型配置摘要")
        print("="*60)
        
        if self.user_specified_models:
            print(f"来源：用户显式指定")
        else:
            print(f"来源：OpenClaw 官方 API")
        
        print(f"可用模型：{len(self.available_models)} 个\n")
        
        if len(self.available_models) == 1:
            model = self.available_models[0]
            print(f"  ⚠️  单一模型配置：{model['name']}")
            print(f"     所有专家都将使用这个模型\n")
        else:
            for model in self.available_models:
                tags_str = ", ".join(model.get('tags', []))
                priority_str = "⭐" * (4 - model.get('priority', 3))
                print(f"  • {model['name']} ({model['id']})")
                print(f"    标签：{tags_str or '无'}")
                print(f"    优先级：{priority_str or '⭐'}\n")
        
        print("="*60)
    
    def export_config(self, output_path: str):
        """
        导出模型配置到独立文件（用于审计和备份）
        
        Args:
            output_path: 输出文件路径
        """
        config = {
            'version': '1.0',
            'source': 'user_specified' if self.user_specified_models else 'openclaw_api',
            'models': self.available_models,
            'note': '此配置不包含任何敏感信息（apiKey、baseUrl 等）'
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 模型配置已导出到：{output_path}")
    
    @classmethod
    def import_config(cls, input_path: str) -> 'ModelSelector':
        """
        从独立文件导入模型配置
        
        Args:
            input_path: 输入文件路径
        
        Returns:
            ModelSelector 实例
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        models = config.get('models', [])
        return cls(user_models=models)


# 快捷函数
def get_model_selector(user_models: List[Dict] = None) -> ModelSelector:
    """获取模型选择器实例"""
    return ModelSelector(user_models)


def select_model(role: str, user_models: List[Dict] = None, user_specified: str = None) -> str:
    """为角色选择模型"""
    selector = ModelSelector(user_models)
    return selector.select_model_for_role(role, user_specified)


def list_available_models(user_models: List[Dict] = None) -> List[Dict]:
    """列出所有可用模型"""
    selector = ModelSelector(user_models)
    return selector.get_available_models()


# 测试
if __name__ == "__main__":
    print("🧪 RoundTable 模型选择器测试\n")
    
    # 测试 1: 使用 OpenClaw API（或降级）
    print("测试 1: 自动获取模型")
    print("-"*60)
    selector = ModelSelector()
    selector.print_model_summary()
    
    # 测试 2: 用户显式指定
    print("\n测试 2: 用户显式指定模型")
    print("-"*60)
    user_models = [
        {'id': 'bailian/glm-5', 'name': 'GLM-5', 'tags': ['chinese'], 'priority': 2}
    ]
    selector2 = ModelSelector(user_models=user_models)
    selector2.print_model_summary()
    
    # 测试 3: 模型匹配
    print("\n测试 3: 模型匹配测试")
    print("-"*60)
    test_roles = ["engineering", "design", "testing", "host"]
    for role in test_roles:
        model = selector.select_model_for_role(role)
        print(f"{role:15} → {model}")
