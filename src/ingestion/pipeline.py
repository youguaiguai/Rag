# Pipeline 主流程编排
# 知识点：Pipeline 模式 — 串行执行多个处理阶段
#   - 流程：load → split → transform → embed → upsert
#   - 支持 on_progress 回调，Dashboard 据此展示进度条
#   - 增量更新：通过 FileIntegrity (SHA256) 判断文件是否变更
