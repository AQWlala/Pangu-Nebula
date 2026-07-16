# server/kb/graph/kuzu_store.py
"""Kuzu 嵌入式图数据库存储"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path


class KuzuGraphStore:
    SCHEMA_DDL = [
        "CREATE NODE TABLE IF NOT EXISTS Document (id STRING PRIMARY KEY, title STRING, type STRING, scope STRING, confidence DOUBLE, file_path STRING, updated_at TIMESTAMP)",
        "CREATE NODE TABLE IF NOT EXISTS Entity (id STRING PRIMARY KEY, name STRING, entity_type STRING, description STRING, mention_count INT64)",
        "CREATE REL TABLE IF NOT EXISTS References (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS Extends (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS Contradicts (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS DerivedFrom (FROM Document TO Document, weight DOUBLE, created_at TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS Mentions (FROM Document TO Entity, count INT64, first_seen TIMESTAMP)",
        "CREATE REL TABLE IF NOT EXISTS RelatedTo (FROM Entity TO Entity, relation STRING, weight DOUBLE)",
    ]

    def __init__(self, db_dir: Path):
        self.db_dir = db_dir
        # kuzu 在 db_dir 路径创建数据库文件（非目录）。
        # 如果 db_dir 已存在为空目录（可能由 ensure_dirs() 创建），删除它让 kuzu 自行创建文件。
        # 如果 db_dir 已存在为文件（已有数据库），保持原样。
        self.db_dir.parent.mkdir(parents=True, exist_ok=True)
        if self.db_dir.exists() and self.db_dir.is_dir():
            try:
                self.db_dir.rmdir()  # 只删除空目录
            except OSError:
                pass  # 目录非空，保持原样
        self._db = None
        self._conn = None

    def _ensure_connection(self):
        if self._conn is not None:
            return
        import kuzu
        self._db = kuzu.Database(str(self.db_dir))
        self._conn = kuzu.Connection(self._db)

    def close(self):
        """Release the KùzuDB connection and database references.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        try:
            self._conn = None
            self._db = None
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def init_schema(self):
        self._ensure_connection()
        for ddl in self.SCHEMA_DDL:
            self._conn.execute(ddl)

    def add_document(self, doc_id, title, doc_type, scope, confidence, file_path):
        self._ensure_connection()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            "MERGE (d:Document {id: $id}) SET d.title=$title, d.type=$type, d.scope=$scope, d.confidence=$confidence, d.file_path=$file_path, d.updated_at=timestamp($ts)",
            {"id": doc_id, "title": title, "type": doc_type, "scope": scope, "confidence": confidence, "file_path": file_path, "ts": now_str},
        )

    def add_relation(self, source_id, target_id, rel_type, weight):
        self._ensure_connection()
        valid = {"References", "Extends", "Contradicts", "DerivedFrom"}
        if rel_type not in valid:
            raise ValueError(f"rel_type 必须是 {valid} 之一")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = f"MATCH (s:Document {{id: $src}}), (t:Document {{id: $tgt}}) MERGE (s)-[r:{rel_type}]->(t) SET r.weight=$w, r.created_at=timestamp($ts)"
        self._conn.execute(query, {"src": source_id, "tgt": target_id, "w": weight, "ts": now_str})

    def list_documents(self, scope=None):
        self._ensure_connection()
        if scope:
            result = self._conn.execute("MATCH (d:Document) WHERE d.scope=$scope RETURN d.id, d.title, d.type, d.scope, d.confidence", {"scope": scope})
        else:
            result = self._conn.execute("MATCH (d:Document) RETURN d.id, d.title, d.type, d.scope, d.confidence")
        docs = []
        while result.has_next():
            row = result.get_next()
            docs.append({"id": row[0], "title": row[1], "type": row[2], "scope": row[3], "confidence": row[4]})
        return docs

    def get_relations(self, doc_id):
        self._ensure_connection()
        result = self._conn.execute("MATCH (d:Document {id: $id})-[r]->(t:Document) RETURN t.id, label(r), r.weight", {"id": doc_id})
        rels = []
        while result.has_next():
            row = result.get_next()
            rels.append({"target_id": row[0], "rel_type": row[1], "weight": row[2]})
        return rels

    def get_neighbors(self, doc_id, depth=2, scope=None):
        self._ensure_connection()
        query = f"MATCH (d:Document {{id: $id}})-[r*1..{depth}]-(t:Document)"
        params = {"id": doc_id}
        if scope:
            query += " WHERE t.scope = $scope"
            params["scope"] = scope
        query += " RETURN DISTINCT t.id, t.title, t.scope, t.confidence"
        result = self._conn.execute(query, params)
        neighbors = []
        while result.has_next():
            row = result.get_next()
            neighbors.append({"id": row[0], "title": row[1], "scope": row[2], "confidence": row[3]})
        return neighbors

    def list_tables(self):
        self._ensure_connection()
        result = self._conn.execute("CALL show_tables() RETURN *")
        tables = []
        while result.has_next():
            row = result.get_next()
            # show_tables() 返回列: [id, name, type, database name, comment]
            tables.append(row[1])
        return tables
