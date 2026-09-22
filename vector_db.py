from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


class QdrantStorage:

    def __init__(
        self,
        url="http://localhost:6333",
        collection="docs",
        dim=3072
    ):
        self.client = QdrantClient(
            url=url,
            timeout=30
        )

        self.collection = collection

        # Create collection if it doesn't exist
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=dim,
                    distance=Distance.COSINE
                )
            )

    def upsert(
        self,
        ids,
        vectors,
        payloads
    ):
        points = [
            PointStruct(
                id=ids[i],
                vector=vectors[i],
                payload=payloads[i]
            )
            for i in range(len(ids))
        ]

        self.client.upsert(
            collection_name=self.collection,
            points=points
        )

    def search(
        self,
        vector,
        top_k: int = 5
    ):
        results = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            with_payload=True,
            limit=top_k
        )

        contexts = []
        sources = set()

        for r in results.points:

            payload = r.payload or {}

            text = payload.get("text", "")
            source = payload.get("source", "")

            if text:
                contexts.append(text)

            if source:
                sources.add(source)

        return {
            "contexts": contexts,
            "sources": list(sources)
        }


# from pydoc import text

# from qdrant_client import QdrantClient
# from qdrant_client.models import Distance, VectorParams, PointStruct
# from streamlit import context
# class QdrantStorage:
#     def __init__(self,url="http://localhost:6333", collection="docs", dim=3072):
#         self.client = QdrantClient(url=url, timeout=30)
#         self.collection = collection
        
#         if not self.client.collection_exists(self.collection):
#             self.client.create_collection(
#                 collection_name=self.collection,
#                 vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
#             )

#     def upsert(self, id, vector, payload):
#         points = [PointStruct(id=id[i], vector=vector[i], payload=payload[i]) for i in range(len(id))]
#         self.client.upsert(collection_name=self.collection, points=points)

#     def search(self, vector, top_k: int = 5):
#         results = self.client.search(  
#             collection_name=self.collection,   
#             query_vector=vector,
#             with_payload=True,
#             limit=top_k
#         )

#         contexts = []
#         sources = set()

#         for r in results:
#             payLoads= getattr(r, 'payload', None) or {}
#             text= payLoads.get('text', "")
#             source= payLoads.get('source', "")
#             if text:
#                 contexts.append(text)
#                 sources.add(source)

#         return contexts, list(sources)