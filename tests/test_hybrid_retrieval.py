"""Regression checks for explicit opt-in and safe fallback; no external service."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from contracts import Fragment
from hybrid_retrieval import APIEmbedder, HybridRetriever, create_retriever
from retrieval import LexicalRetriever
from settings import Settings


class HybridTests(unittest.TestCase):
    def test_default_requests_no_embeddings_and_matches_a2(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'knowledge.zip'
            with ZipFile(path, 'w') as archive:
                archive.writestr('product.md', '# Учёт\n\nСистема учёта показаний.')
            config = Settings('http://127.0.0.1:1/v1', 'test', 'test')
            with patch.object(APIEmbedder, 'embed', side_effect=AssertionError('unexpected network call')) as embed:
                retriever = create_retriever(path, config, environ={})
                self.assertEqual(retriever.search('показания'), LexicalRetriever.from_zip(path).search('показания'))
                embed.assert_not_called()
            with self.assertRaises(ValueError):
                create_retriever(path, config, environ={'RETRIEVAL_MODE': 'typo'})

    def test_query_dimension_mismatch_falls_back(self):
        class Embedder:
            def embed(self, texts, query=False):
                return [[1.0] if query else [1.0, 0.0] for _ in texts]
        fragments = [Fragment('test.md', 's1', 'Учёт показаний.')]
        retriever = HybridRetriever(fragments, Embedder())
        for _ in range(3):
            self.assertEqual(retriever.search('показания'), LexicalRetriever(fragments).search('показания'))
        self.assertTrue(retriever.stats['breaker_open'])

    def test_startup_exception_does_not_expose_private_details(self):
        class Embedder:
            def embed(self, texts, query=False):
                raise ValueError('private-key-and-document')
        retriever = HybridRetriever([Fragment('test.md', 's1', 'Test')], Embedder())
        self.assertNotIn('private-key', json.dumps(retriever.stats))
        self.assertEqual(retriever.stats['mode'], 'lexical_fallback')

    def test_invalid_vectors_and_duplicate_indices_are_rejected(self):
        class Transport:
            def __init__(self, data): self.data = data
            def post(self, *args): return 200, {}, json.dumps({'data': self.data}).encode()
        cases = [
            [{'index': 0, 'embedding': []}],
            [{'index': 0, 'embedding': [float('nan')]}],
            [{'index': 0, 'embedding': [0.0]}],
            [{'index': -1, 'embedding': [1.0]}],
            [{'index': 0, 'embedding': [1.0]}, {'index': 0, 'embedding': [2.0]}],
        ]
        for data in cases:
            with self.subTest(data=data):
                client = APIEmbedder('http://unused', 'key', 'model', transport=Transport(data))
                with self.assertRaises((ValueError, RuntimeError)):
                    client.embed(['first', 'second'] if len(data) > 1 else ['first'])


if __name__ == '__main__':
    unittest.main()
