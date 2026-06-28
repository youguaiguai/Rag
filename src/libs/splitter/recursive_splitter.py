# RecursiveCharacterTextSplitter 实现
# 知识点：递归字符切分器的工作原理
#   - 按层级分隔符递归切分：段落(\n\n) → 句子(\n) → 字符
#   - 在长度限制内尽量保持语义边界
#   - 对 Markdown 文档天然适配（标题、列表、代码块）
