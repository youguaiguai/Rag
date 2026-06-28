# PDF Loader — 使用 MarkItDown 将 PDF 转为 Markdown
# 知识点：为什么先转 Markdown 再切分？
#   - Markdown 有天然的结构标记（标题、段落、代码块）
#   - RecursiveCharacterTextSplitter 可以按 Markdown 结构智能切分
#   - 比直接从 PDF 提取纯文本再切分质量高得多
