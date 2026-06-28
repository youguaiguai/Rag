# Loader 抽象基类
# 知识点：BaseLoader 定义统一的文档加载接口
#   - load(path) -> Document: 将原始文件转为统一的 Document 对象
#   - 不同格式（PDF/Markdown/HTML）只需实现此接口即可插拔
