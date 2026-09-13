"""
ImageStorage — 图片文件存储与 SQLite 索引映射

知识点：ImageStorage 在 RAG Pipeline 中的位置
  - 摄取链路：Loader 提取图片 → **ImageStorage** 保存文件 + 索引
  - 检索链路：ImageCaptioner 生成 caption → chunk metadata 关联 image_id
  - 职责：保存图片二进制到文件系统 + SQLite 记录 image_id→path 映射

为什么用 SQLite 而非 JSON（面试考点）：
  - 图片数量可能很多（PDF 每页多张图）→ JSON 加载全量到内存不划算
  - SQLite 支持索引查询（按 collection / doc_hash 快速查找）
  - SQLite WAL 模式支持并发读写（Pipeline 异步摄取时安全）
  - 面试考点："为什么 file_integrity 用 JSON 而 image_storage 用 SQLite？" → 量级不同

数据库表结构：
  CREATE TABLE image_index (
      image_id TEXT PRIMARY KEY,
      file_path TEXT NOT NULL,
      collection TEXT,
      doc_hash TEXT,
      page_num INTEGER,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );

接口签名：
  ImageStorage(images_dir: str = "data/images", db_path: str = "data/db/image_index.db")
  save(image_id, image_data, collection, doc_hash, page_num) -> str  # 返回文件路径
  get_path(image_id) -> str | None
  get_by_collection(collection) -> list[dict]
  get_by_doc_hash(doc_hash) -> list[dict]
  delete(image_id) -> bool
  delete_by_doc_hash(doc_hash) -> int
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ImageStorageError(Exception):
    """图片存储异常

    知识点：自定义异常
      - 文件写入失败 / 数据库操作失败时抛出
      - 面试考点："什么时候抛 ImageStorageError？" → IO 错误 / SQLite 错误
    """
    pass


class ImageStorage:
    """图片文件存储 + SQLite 索引映射

    知识点：文件存储 + 索引分离
      - 文件存储：图片二进制保存到 data/images/{collection}/{image_id}.{ext}
      - 索引存储：SQLite 记录 image_id → file_path 映射 + 元数据
      - 分离原因：文件系统擅长存二进制，SQLite 擅长查询
      - 面试考点："为什么不把图片存 SQLite BLOB？" → 文件系统更适合大文件 + 可直接 serve

    接口签名：
      ImageStorage(images_dir, db_path)
      save(image_id, image_data, collection, doc_hash, page_num) -> str
      get_path(image_id) -> str | None
      get_by_collection(collection) -> list[dict]
      get_by_doc_hash(doc_hash) -> list[dict]
      delete(image_id) -> bool
      delete_by_doc_hash(doc_hash) -> int
    """

    def __init__(
        self,
        images_dir: str = "data/images",
        db_path: str = "data/db/image_index.db",
    ) -> None:
        """初始化 ImageStorage

        接口签名：ImageStorage(images_dir="data/images", db_path="data/db/image_index.db")
        入参：
          - images_dir: 图片文件存储根目录
          - db_path: SQLite 索引数据库路径
        """
        self._images_dir = Path(images_dir)
        self._db_path = Path(db_path)

        # 确保目录存在
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_db()

    # --------------------------------------------------------
    # 数据库初始化
    # --------------------------------------------------------

    def _init_db(self) -> None:
        """初始化 SQLite 数据库（建表 + 索引 + WAL 模式）

        知识点：WAL 模式（Write-Ahead Logging）
          - 默认模式：DELETE（写入时锁定整个数据库）
          - WAL 模式：写入先写到 WAL 文件，异步合并到主数据库
          - 好处：读写不互斥（并发安全），写入性能更好
          - 面试考点："为什么要 WAL？" → 并发安全 + 写入性能
        """
        conn = self._get_connection()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS image_index (
                    image_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    collection TEXT,
                    doc_hash TEXT,
                    page_num INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_collection ON image_index(collection)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_hash ON image_index(doc_hash)")
            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """获取 SQLite 连接（每次操作新建，用完关闭）

        知识点：SQLite 连接管理
          - SQLite 的连接是轻量级的（不像 PostgreSQL 需要连接池）
          - 每次操作新建连接 + 用完关闭，避免线程安全问题
          - 面试考点："为什么不用连接池？" → SQLite 是嵌入式数据库，连接开销极小
        """
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row  # 返回 dict-like 行
        return conn

    # --------------------------------------------------------
    # 保存图片
    # --------------------------------------------------------

    def save(
        self,
        image_id: str,
        image_data: bytes,
        collection: str = "default",
        doc_hash: str = "",
        page_num: int = 0,
        extension: str = ".png",
    ) -> str:
        """保存图片到文件系统 + 写入 SQLite 索引

        接口签名：save(image_id, image_data, collection, doc_hash, page_num, extension) -> str
        入参：
          - image_id: 图片唯一标识
          - image_data: 图片二进制数据
          - collection: 图片集合名称（如 doc_hash 前8位，用于按文档分组）
          - doc_hash: 所属文档哈希
          - page_num: 图片所在页码
          - extension: 文件扩展名（.png/.jpg）
        出参：图片文件路径
        异常：ImageStorageError — 文件写入失败 / 数据库错误

        处理流程：
          1. 创建 collection 子目录
          2. 写入图片文件（覆盖已有）
          3. 写入/更新 SQLite 索引（INSERT OR REPLACE 幂等）
        """
        # 1. 创建目录
        collection_dir = self._images_dir / collection
        collection_dir.mkdir(parents=True, exist_ok=True)

        # 2. 写入文件
        file_path = collection_dir / f"{image_id}{extension}"
        try:
            file_path.write_bytes(image_data)
        except OSError as e:
            raise ImageStorageError(f"图片文件写入失败: {file_path}: {e}")

        # 3. 写入索引（幂等：INSERT OR REPLACE）
        conn = self._get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO image_index
                   (image_id, file_path, collection, doc_hash, page_num)
                   VALUES (?, ?, ?, ?, ?)""",
                (image_id, str(file_path), collection, doc_hash, page_num),
            )
            conn.commit()
        except sqlite3.Error as e:
            raise ImageStorageError(f"索引写入失败: {e}")
        finally:
            conn.close()

        logger.debug("ImageStorage: 保存图片 %s → %s", image_id, file_path)
        return str(file_path)

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------

    def get_path(self, image_id: str) -> str | None:
        """查找 image_id 对应的文件路径

        接口签名：get_path(image_id: str) -> str | None
        出参：文件路径（不存在返回 None）
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT file_path FROM image_index WHERE image_id = ?",
                (image_id,),
            ).fetchone()
            return row["file_path"] if row else None
        finally:
            conn.close()

    def get_by_collection(self, collection: str) -> list[dict[str, Any]]:
        """按 collection 批量查询图片

        接口签名：get_by_collection(collection: str) -> list[dict]
        出参：图片记录列表 [{image_id, file_path, collection, doc_hash, page_num, created_at}]
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM image_index WHERE collection = ? ORDER BY page_num",
                (collection,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_by_doc_hash(self, doc_hash: str) -> list[dict[str, Any]]:
        """按 doc_hash 查询文档的所有图片

        接口签名：get_by_doc_hash(doc_hash: str) -> list[dict]
        出参：图片记录列表
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM image_index WHERE doc_hash = ? ORDER BY page_num",
                (doc_hash,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # --------------------------------------------------------
    # 删除
    # --------------------------------------------------------

    def delete(self, image_id: str) -> bool:
        """删除单个图片（文件 + 索引）

        接口签名：delete(image_id: str) -> bool
        出参：是否删除成功（不存在返回 False）

        知识点：删除策略
          1. 先查索引获取文件路径
          2. 删除文件
          3. 删除索引记录
          4. 文件删除失败不阻塞索引删除（索引是主要数据源）
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT file_path FROM image_index WHERE image_id = ?",
                (image_id,),
            ).fetchone()

            if row is None:
                return False

            # 删除文件（失败不阻塞索引删除）
            file_path = Path(row["file_path"])
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError as e:
                logger.warning("ImageStorage: 删除图片文件失败 %s: %s", file_path, e)

            # 删除索引
            conn.execute("DELETE FROM image_index WHERE image_id = ?", (image_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    def delete_by_doc_hash(self, doc_hash: str) -> int:
        """按 doc_hash 删除文档的所有图片

        接口签名：delete_by_doc_hash(doc_hash: str) -> int
        出参：删除的图片数量
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT image_id, file_path FROM image_index WHERE doc_hash = ?",
                (doc_hash,),
            ).fetchall()

            for row in rows:
                file_path = Path(row["file_path"])
                try:
                    if file_path.exists():
                        file_path.unlink()
                except OSError as e:
                    logger.warning("ImageStorage: 删除图片文件失败 %s: %s", file_path, e)

            conn.execute("DELETE FROM image_index WHERE doc_hash = ?", (doc_hash,))
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    # --------------------------------------------------------
    # 统计
    # --------------------------------------------------------

    def count(self) -> int:
        """图片总数"""
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM image_index").fetchone()
            return row["cnt"]
        finally:
            conn.close()

    def count_by_collection(self, collection: str) -> int:
        """按 collection 统计图片数"""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM image_index WHERE collection = ?",
                (collection,),
            ).fetchone()
            return row["cnt"]
        finally:
            conn.close()

    # --------------------------------------------------------
    # 只读属性
    # --------------------------------------------------------

    @property
    def images_dir(self) -> Path:
        """图片存储根目录"""
        return self._images_dir

    @property
    def db_path(self) -> Path:
        """SQLite 索引数据库路径"""
        return self._db_path

