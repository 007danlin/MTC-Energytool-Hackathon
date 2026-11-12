import unittest
import warnings
from settings import Settings

class DepthTests(unittest.TestCase):
    def test_platform_depth_cannot_erase_validated_floor(self):
        base={"LLM_BASE_URL":"http://local/v1","LLM_API_KEY":"local","LLM_MODEL":"provided-model"}
        for requested,effective in [(1,12),(4,12),(8,12),(12,12),(16,16),(50,40)]:
            with self.subTest(requested=requested), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cfg=Settings.from_env({**base,"TOP_K":str(requested)})
                self.assertEqual(cfg.top_k,effective)
                self.assertEqual(cfg.model,"provided-model")
