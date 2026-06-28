"""
conftest.py — pytest 全局配置与共享 fixture

知识点：
  - conftest.py 是 pytest 的"共享配置中心"，所有测试文件自动加载
  - fixture 是 pytest 的依赖注入机制：用 @pytest.fixture 定义，测试函数通过参数名引用
  - fixture 的作用域（scope）：
      - function: 每个测试函数执行一次（默认）
      - class: 每个测试类执行一次
      - module: 每个测试文件执行一次
      - session: 整个测试会话只执行一次

关键技术细节：
  - conftest.py 的查找规则：pytest 从测试文件向上逐级查找 conftest.py
  - 子目录的 conftest.py 可以覆盖父目录的同名 fixture
  - fixture 签名：@pytest.fixture(scope="function") def fixture_name() -> ReturnType
"""

import sys
from pathlib import Path

import pytest

# 将 src/ 加入 sys.path，确保测试中能 import 项目包
# 这是 conftest.py 的关键职责之一：路径配置
# pyproject.toml 中的 [tool.pytest.ini_options] pythonpath = ["src"] 也做了同样的事
# 两处都配置，双重保障
SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ============================================================
# 共享 Fixture
# ============================================================

@pytest.fixture(scope="session")
def project_root() -> Path:
    """项目根目录路径

    接口签名：project_root() -> Path
    返回值：项目根目录的 Path 对象
    用法：在测试中通过参数 `project_root` 引用
    """
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def config_path(project_root: Path) -> Path:
    """配置文件路径

    接口签名：config_path(project_root: Path) -> Path
    入参：project_root — 由上面的 fixture 注入
    返回值：config/settings.yaml 的 Path 对象
    """
    return project_root / "config" / "settings.yaml"


@pytest.fixture(scope="session")
def fixtures_dir(project_root: Path) -> Path:
    """测试数据目录

    接口签名：fixtures_dir(project_root: Path) -> Path
    返回值：tests/fixtures/ 的 Path 对象
    """
    return project_root / "tests" / "fixtures"


@pytest.fixture(scope="session")
def sample_documents_dir(fixtures_dir: Path) -> Path:
    """样例文档目录

    接口签名：sample_documents_dir(fixtures_dir: Path) -> Path
    返回值：tests/fixtures/sample_documents/ 的 Path 对象
    """
    return fixtures_dir / "sample_documents"
