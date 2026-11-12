import unittest
import warnings
from settings import Settings

class DepthTests(unittest.TestCase):
    def test_requested_depth_is_respected_as_in_a2(self):
        base={"LLM_BASE_URL":"http://local/v1","LLM_API_KEY":"local","LLM_MODEL":"provided-model"}
        for requested,effective in [(1,1),(4,4),(8,8),(12,12),(16,16),(50,40),(0,1)]:
            with self.subTest(requested=requested), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cfg=Settings.from_env({**base,"TOP_K":str(requested)})
                self.assertEqual(cfg.top_k,effective)
        self.assertEqual(Settings.from_env(base).top_k,12)
