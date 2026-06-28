# 图片描述生成 — Vision LLM
# 知识点：Image-to-Text 策略
#   - 用 Vision LLM（如 GPT-4o）将图片转为文字描述
#   - Caption 写入 Chunk 的 metadata/text，复用纯文本检索链路
#   - 降级模式：Vision LLM 不可用时，标记 has_unprocessed_images 但不阻塞
