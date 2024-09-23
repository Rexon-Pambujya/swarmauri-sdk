from typing import List, Union, Literal
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    VectorParams,
    Distance,
)

from swarmauri.standard.documents.concrete.Document import Document
from swarmauri.standard.embeddings.concrete.Doc2VecEmbedding import Doc2VecEmbedding
from swarmauri.standard.distances.concrete.CosineDistance import CosineDistance

from swarmauri.standard.vector_stores.base.VectorStoreBase import VectorStoreBase
from swarmauri.standard.vector_stores.base.VectorStoreRetrieveMixin import (
    VectorStoreRetrieveMixin,
)
from swarmauri.standard.vector_stores.base.VectorStoreSaveLoadMixin import (
    VectorStoreSaveLoadMixin,
)
from swarmauri.standard.vector_stores.base.VectorStoreCloudMixin import (
    VectorStoreCloudMixin,
)


class CloudQdrantVectorStore(
    VectorStoreSaveLoadMixin,
    VectorStoreRetrieveMixin,
    VectorStoreCloudMixin,
    VectorStoreBase,
):
    """
    CloudQdrantVectorStore is a concrete implementation that integrates functionality
    for saving, loading, storing, and retrieving vector documents, leveraging Qdrant as the backend.
    """

    type: Literal["CloudQdrantVectorStore"] = "CloudQdrantVectorStore"

    def __init__(
        self, api_key: str, url: str, collection_name: str, vector_size: int, **kwargs
    ):
        super().__init__(
            api_key=api_key,
            url=url,
            collection_name=collection_name,
            vector_size=vector_size,
            **kwargs,
        )
        self._embedder = Doc2VecEmbedding(vector_size=vector_size)
        self.vectorizer = self._embedder
        self._distance = CosineDistance()

        self.api_key = api_key
        self.url = url
        self.collection_name = collection_name
        self.vector_size = vector_size

        self.client = None

    def connect(self) -> None:
        """
        Connects to the Qdrant cloud vector store using the provided credentials.
        """
        if self.client is None:
            self.client = QdrantClient(
                api_key=self.api_key,
                url=self.url,
            )

        # TODO  may need optimization two loops may not be necessary
        # Check if the collection exists
        existing_collections = self.client.get_collections().collections
        collection_names = [collection.name for collection in existing_collections]

        if self.collection_name not in collection_names:
            # Ensure the collection exists with the desired configuration
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size, distance=Distance.COSINE
                ),
            )

    def disconnect(self) -> None:
        """
        Disconnects from the Qdrant cloud vector store.
        """
        if self.client is not None:
            self.client = None

    def add_document(self, document: Document) -> None:
        """
        Add a single document to the document store.

        Parameters:
            document (Document): The document to be added to the store.
        """
        embedding = None
        if not document.embedding:
            self.vectorizer.fit([document.content])  # Fit only once
            embedding = (
                self.vectorizer.transform([document.content])[0].to_numpy().tolist()
            )
        else:
            embedding = document.embedding

        payload = {
            "content": document.content,
            "metadata": document.metadata,
        }

        doc = PointStruct(id=document.id, vector=embedding, payload=payload)

        self.client.upsert(
            collection_name=self.collection_name,
            points=[doc],
        )

    def add_documents(self, documents: List[Document]) -> None:
        """
        Add multiple documents to the document store in a batch operation.

        Parameters:
            documents (List[Document]): A list of documents to be added to the store.
        """
        points = [
            PointStruct(
                id=doc.id,
                vector=doc.embedding
                or self.vectorizer.fit_transform([doc.content])[0].to_numpy().tolist(),
                payload={"content": doc.content, "metadata": doc.metadata},
            )
            for doc in documents
        ]
        self.client.upsert(self.collection_name, points=points)

    def get_document(self, id: str) -> Union[Document, None]:
        """
        Retrieve a single document by its identifier.

        Parameters:
            id (str): The unique identifier of the document to retrieve.

        Returns:
            Union[Document, None]: The requested document if found; otherwise, None.
        """
        response = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[id],
        )
        if response:
            payload = response[0].payload
            return Document(
                id=id, content=payload["content"], metadata=payload["metadata"]
            )
        return None

    def get_all_documents(self) -> List[Document]:
        """
        Retrieve all documents stored in the document store.

        Returns:
            List[Document]: A list of all documents in the store.
        """
        response = self.client.scroll(
            collection_name=self.collection_name,
        )

        return [
            Document(
                id=doc.id,
                content=doc.payload["content"],
                metadata=doc.payload["metadata"],
            )
            for doc in response[0]
        ]

    def delete_document(self, id: str) -> None:
        """
        Delete a document from the document store by its identifier.

        Parameters:
            id (str): The unique identifier of the document to delete.
        """
        self.client.delete(self.collection_name, points_selector=[id])

    def update_document(self, id: str, updated_document: Document) -> None:
        """
        Update a document in the document store.

        Parameters:
            id (str): The unique identifier of the document to update.
            updated_document (Document): The updated document instance.
        """
        # Precompute the embedding outside the update process
        if not updated_document.embedding:
            # Transform without refitting to avoid vocabulary issues
            document_vector = self.vectorizer.transform([updated_document.content])[0]
        else:
            document_vector = updated_document.embedding

        document_vector = document_vector.to_numpy().tolist()

        self.client.upsert(
            self.collection_name,
            points=[
                PointStruct(
                    id=id,
                    vector=document_vector,
                    payload={
                        "content": updated_document.content,
                        "metadata": updated_document.metadata,
                    },
                )
            ],
        )

    def clear_documents(self) -> None:
        """
        Deletes all documents from the vector store
        """
        self.client.delete_collection(self.collection_name)

    def document_count(self) -> int:
        """
        Returns the number of documents in the store.
        """
        response = self.client.scroll(
            collection_name=self.collection_name,
        )
        return len(response)

    def retrieve(self, query: str, top_k: int = 5) -> List[Document]:
        """
        Retrieve the top_k most relevant documents based on the given query.
        For the purpose of this example, this method performs a basic search.

        Args:
            query (str): The query string used for document retrieval.
            top_k (int): The number of top relevant documents to retrieve.

        Returns:
            List[Document]: A list of the top_k most relevant documents.
        """
        query_vector = self.vectorizer.infer_vector(query).value
        results = self.client.search(
            collection_name=self.collection_name, query_vector=query_vector, limit=top_k
        )

        return [
            Document(
                id=res.id,
                content=res.payload["content"],
                metadata=res.payload["metadata"],
            )
            for res in results
        ]