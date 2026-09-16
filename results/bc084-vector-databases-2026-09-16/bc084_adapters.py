"""Per-subject adapters implementing the generic DBClient interface for bc-084."""
import uuid

import numpy as np

from bc084_harness import DBClient


class QdrantAdapter(DBClient):
    name = "qdrant"
    COLLECTION = "bc084"

    def __init__(self, host="127.0.0.1", port=6333):
        from qdrant_client import QdrantClient

        self.client = QdrantClient(host=host, port=port, timeout=30)

    def setup(self, dim):
        from qdrant_client.models import Distance, VectorParams

        if self.client.collection_exists(self.COLLECTION):
            self.client.delete_collection(self.COLLECTION)
        self.client.create_collection(
            collection_name=self.COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        self._id_map = {}

    def insert(self, ids, vectors):
        from qdrant_client.models import PointStruct

        points = []
        self._id_map = {}
        for i, (rid, vec) in enumerate(zip(ids, vectors)):
            points.append(PointStruct(id=i, vector=vec.tolist(), payload={"doc_id": rid}))
            self._id_map[i] = rid
        batch = 256
        inserted = 0
        failed = 0
        for start in range(0, len(points), batch):
            chunk = points[start : start + batch]
            try:
                self.client.upsert(collection_name=self.COLLECTION, points=chunk, wait=True)
                inserted += len(chunk)
            except Exception:
                failed += len(chunk)
        return {"inserted": inserted, "failed": failed}

    def wait_ready(self, expected_count, timeout_s=60.0):
        import time

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            info = self.client.get_collection(self.COLLECTION)
            if info.points_count == expected_count and info.status.value == "green":
                return True
            time.sleep(0.5)
        return False

    def query(self, vector, k):
        hits = self.client.query_points(
            collection_name=self.COLLECTION, query=vector.tolist(), limit=k
        ).points
        return [self._id_map[h.id] for h in hits]

    def teardown(self):
        if self.client.collection_exists(self.COLLECTION):
            self.client.delete_collection(self.COLLECTION)


class WeaviateAdapter(DBClient):
    name = "weaviate"
    CLASS_NAME = "Bc084Doc"

    def __init__(self, host="127.0.0.1", port=8080):
        import weaviate

        self.client = weaviate.connect_to_local(host=host, port=port)

    def setup(self, dim):
        from weaviate.classes.config import Configure, VectorDistances

        if self.client.collections.exists(self.CLASS_NAME):
            self.client.collections.delete(self.CLASS_NAME)
        self.client.collections.create(
            self.CLASS_NAME,
            vector_config=Configure.Vectors.self_provided(
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE
                )
            ),
        )
        self.collection = self.client.collections.get(self.CLASS_NAME)

    def insert(self, ids, vectors):
        from weaviate.classes.data import DataObject

        objs = [
            DataObject(properties={"doc_id": rid}, vector=vec.tolist())
            for rid, vec in zip(ids, vectors)
        ]
        inserted = 0
        failed = 0
        batch = 256
        for start in range(0, len(objs), batch):
            chunk = objs[start : start + batch]
            result = self.collection.data.insert_many(chunk)
            errs = result.errors or {}
            failed += len(errs)
            inserted += len(chunk) - len(errs)
        return {"inserted": inserted, "failed": failed}

    def wait_ready(self, expected_count, timeout_s=60.0):
        import time

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            count = self.collection.aggregate.over_all(total_count=True).total_count
            if count == expected_count:
                return True
            time.sleep(0.5)
        return False

    def query(self, vector, k):
        res = self.collection.query.near_vector(near_vector=vector.tolist(), limit=k)
        return [o.properties["doc_id"] for o in res.objects]

    def teardown(self):
        if self.client.collections.exists(self.CLASS_NAME):
            self.client.collections.delete(self.CLASS_NAME)

    def close(self):
        self.client.close()


class ChromaAdapter(DBClient):
    name = "chroma"
    COLLECTION = "bc084"

    def __init__(self, host="127.0.0.1", port=8000):
        import chromadb

        self.client = chromadb.HttpClient(host=host, port=port)

    def setup(self, dim):
        try:
            self.client.delete_collection(self.COLLECTION)
        except Exception:
            pass
        self.collection = self.client.create_collection(
            self.COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def insert(self, ids, vectors):
        str_ids = [str(i) for i in range(len(ids))]
        self._id_map = dict(zip(str_ids, ids))
        inserted = 0
        failed = 0
        batch = 256
        for start in range(0, len(ids), batch):
            chunk_ids = str_ids[start : start + batch]
            chunk_vecs = vectors[start : start + batch].tolist()
            try:
                self.collection.add(ids=chunk_ids, embeddings=chunk_vecs)
                inserted += len(chunk_ids)
            except Exception:
                failed += len(chunk_ids)
        return {"inserted": inserted, "failed": failed}

    def wait_ready(self, expected_count, timeout_s=60.0):
        import time

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.collection.count() == expected_count:
                return True
            time.sleep(0.5)
        return False

    def query(self, vector, k):
        res = self.collection.query(query_embeddings=[vector.tolist()], n_results=k)
        result_str_ids = res["ids"][0]
        return [self._id_map[i] for i in result_str_ids]

    def teardown(self):
        try:
            self.client.delete_collection(self.COLLECTION)
        except Exception:
            pass


class PineconeAdapter(DBClient):
    name = "pinecone"
    INDEX = "bc084"

    def __init__(self, host="127.0.0.1", port=5080):
        from pinecone import Pinecone

        self.pc = Pinecone(api_key="pclocal", host=f"http://{host}:{port}")
        self.host = host
        self.port = port

    def setup(self, dim):
        from pinecone import ServerlessSpec

        existing = [i["name"] for i in self.pc.list_indexes()]
        if self.INDEX in existing:
            self.pc.delete_index(self.INDEX)
        self.pc.create_index(
            name=self.INDEX,
            vector_type="dense",
            dimension=dim,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            deletion_protection="disabled",
        )
        desc = self.pc.describe_index(self.INDEX)
        host = desc.host
        if not host.startswith("http"):
            host = f"http://{host}"
        self.index = self.pc.Index(host=host)

    def insert(self, ids, vectors):
        self._id_map = {}
        vecs = []
        for i, (rid, vec) in enumerate(zip(ids, vectors)):
            pid = str(i)
            self._id_map[pid] = rid
            vecs.append({"id": pid, "values": vec.tolist()})
        inserted = 0
        failed = 0
        batch = 100
        for start in range(0, len(vecs), batch):
            chunk = vecs[start : start + batch]
            try:
                self.index.upsert(vectors=chunk)
                inserted += len(chunk)
            except Exception:
                failed += len(chunk)
        return {"inserted": inserted, "failed": failed}

    def wait_ready(self, expected_count, timeout_s=60.0):
        import time

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            stats = self.index.describe_index_stats()
            if stats.total_vector_count == expected_count:
                return True
            time.sleep(0.5)
        return False

    def query(self, vector, k):
        res = self.index.query(vector=vector.tolist(), top_k=k)
        return [self._id_map[m["id"]] for m in res["matches"]]

    def teardown(self):
        existing = [i["name"] for i in self.pc.list_indexes()]
        if self.INDEX in existing:
            self.pc.delete_index(self.INDEX)
