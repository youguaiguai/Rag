"""
test_smoke_imports.py — 冒烟测试：验证所有顶层包可正常 import

知识点：
  - 冒烟测试 (Smoke Test)：源自硬件领域，"通电后有没有冒烟"
  - 目的：最基本级别的验证——包能不能被导入，不测业务逻辑
  - 为什么重要：如果 import 都失败，后续所有测试都没有意义
  - 测试函数命名规则：test_ 前缀，pytest 自动发现

关键技术细节：
  - pytest 测试发现规则：
      1. 文件名以 test_ 开头或 _test 结尾
      2. 函数名以 test_ 开头
      3. 类名以 Test 开头（且不含 __init__）
  - 测试函数签名：def test_xxx() -> None（无返回值，断言通过即成功）
  - pytest.importorskip()：如果包不可导入则跳过（而非报错）
    签名：pytest.importorskip(modname: str, minversion: str = None, reason: str = None) -> ModuleType
"""


def test_import_mcp_server():
    """验证 mcp_server 包可导入"""
    import mcp_server
    assert mcp_server is not None


def test_import_core():
    """验证 core 包可导入"""
    import core
    assert core is not None


def test_import_ingestion():
    """验证 ingestion 包可导入"""
    import ingestion
    assert ingestion is not None


def test_import_libs():
    """验证 libs 包可导入"""
    import libs
    assert libs is not None


def test_import_observability():
    """验证 observability 包可导入"""
    import observability
    assert observability is not None


def test_import_core_submodules():
    """验证 core 层子模块可导入

    知识点：测试子模块导入可以及早发现 __init__.py 遗漏
    """
    import core.query_engine
    import core.response
    import core.trace
    assert core.query_engine is not None
    assert core.response is not None
    assert core.trace is not None


def test_import_libs_submodules():
    """验证 libs 层子模块可导入"""
    import libs.loader
    import libs.llm
    import libs.embedding
    import libs.splitter
    import libs.vector_store
    import libs.reranker
    import libs.evaluator
    assert libs.loader is not None
    assert libs.llm is not None
    assert libs.embedding is not None
    assert libs.splitter is not None
    assert libs.vector_store is not None
    assert libs.reranker is not None
    assert libs.evaluator is not None


def test_import_ingestion_submodules():
    """验证 ingestion 层子模块可导入"""
    import ingestion.chunking
    import ingestion.transform
    import ingestion.embedding
    import ingestion.storage
    assert ingestion.chunking is not None
    assert ingestion.transform is not None
    assert ingestion.embedding is not None
    assert ingestion.storage is not None


def test_import_yaml_dependency():
    """验证 YAML 依赖可导入

    知识点：测试第三方依赖是否正确安装
    如果此测试失败，说明 pip install 没成功
    """
    import yaml
    assert yaml is not None
    # 验证 yaml.load 接口签名：yaml.load(stream, Loader) -> Any
    # Loader 参数是安全必需的，防止 YAML 反序列化攻击
    result = yaml.safe_load("key: value")
    assert result == {"key": "value"}


def test_project_root_exists(project_root):
    """验证项目根目录存在

    知识点：fixture 通过参数注入，pytest 自动解析
    签名：def test_xxx(project_root: Path) -> None
    pytest 发现参数名 project_root → 查找 conftest.py 中同名 fixture → 注入返回值
    """
    assert project_root.exists()
    assert (project_root / "pyproject.toml").exists()
    assert (project_root / "config").exists()


def test_config_path_exists(config_path):
    """验证配置文件路径存在"""
    assert config_path.exists()
    assert config_path.name == "settings.yaml"


def test_sample_documents_dir_exists(sample_documents_dir):
    """验证样例文档目录存在"""
    assert sample_documents_dir.exists()
