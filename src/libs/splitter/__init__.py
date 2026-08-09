"""
Splitter 模块 — 可插拔的文本切分抽象层


导出：
  - BaseSplitter: 抽象基类，所有切分策略的统一接口
  - SplitterError: 切分异常
  - SplitterFactory: 工厂类，根据配置创建对应实现
  - FakeSplitter: 测试桩，不依赖外部库
"""

__all__ = [
    "BaseSplitter",
    "SplitterError",
    "SplitterFactory",
    "FakeSplitter",
]

