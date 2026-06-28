# 数据摄取脚本 — 离线摄取入口
# 知识点：CLI 入口脚本的设计原则
#   - argparse 解析命令行参数
#   - 支持 --collection / --path / --force 等选项
#   - 调用 Ingestion Pipeline 完成摄取
#   - C15 阶段实现
