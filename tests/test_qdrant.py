import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Test Qdrant in embedded mode (local file-based)
client = QdrantClient(path=":memory:")
collection_name = "reid_embeddings"

# Create collection
client.create_collection(
    collection_name=collection_name,
    vectors_config=VectorParams(size=512, distance=Distance.COSINE),
)
print(f"Qdrant collection '{collection_name}' created")

# Insert dummy embedding
dummy_embedding = np.random.randn(512).astype(np.float32).tolist()
client.upsert(
    collection_name=collection_name,
    points=[
        PointStruct(
            id=1,
            vector=dummy_embedding,
            payload={"camera_id": "camera-01", "track_id": "track_001", "timestamp": "2026-09-02T12:00:00Z"},
        )
    ],
)
print("Embedding inserted")

# Search
results = client.query_points(
    collection_name=collection_name,
    query=dummy_embedding,
    limit=1,
)
print(f"Search result: id={results.points[0].id}, score={results.points[0].score:.4f}")

# Cleanup
client.delete_collection(collection_name)
print("Qdrant test: PASS")
