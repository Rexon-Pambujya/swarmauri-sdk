import pytest
from swarmauri.standard.embeddings.concrete.TfidfEmbedding import TfidfEmbedding

@pytest.mark.unit
def test_ubc_resource():
    def test():
        assert TfidfEmbedding().resource == 'Embedding'
    test()

@pytest.mark.unit
def test_fit_transform():
	def test():
		embedder = TfidfEmbedding()
		documents = ['test', 'test1', 'test2']
		embedder.fit_transform(documents)
		assert documents == embedder.extract_features()
	test()