import unittest
import logging
import sys
import copy
from pathlib import Path

# Adjust path / Import
sys.path.append(str(Path(__file__).resolve().parent.parent / "webdog_bot"))

from models import Config, Monitor, UserData, WeightedFingerprint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ConfigTest")

class TestConfig(unittest.TestCase):
    
    def test_validation(self):
        logger.info("Test 1: Validation")
        # Try invalid low interval
        c = Config(check_interval=10)
        self.assertEqual(c.check_interval, 30, "Should clamp to min 30")
        
        # Try invalid high threshold magnitude (e.g. 150%)?
        # dataclass won't catch type, but our init might not either unless we pass it.
        # But we check 0.0 < x <= 1.0 logic.
        c2 = Config(similarity_threshold=1.5)
        self.assertEqual(c2.similarity_threshold, 1.0, "Should clamp to 1.0")
        
    def test_hierarchy(self):
        logger.info("Test 2: Hierarchy")
        
        user_cfg = Config(similarity_threshold=0.85)
        monitor_cfg = Config(similarity_threshold=0.99)
        
        m_default = Monitor(url="a.com", config=None)
        m_custom = Monitor(url="b.com", config=monitor_cfg)
        
        ud = UserData(user_config=user_cfg, monitors=[m_default, m_custom])
        
        # Resolve m_default
        c1 = m_default.config if m_default.config else ud.user_config
        self.assertEqual(c1.similarity_threshold, 0.85)
        
        # Resolve m_custom
        c2 = m_custom.config if m_custom.config else ud.user_config
        self.assertEqual(c2.similarity_threshold, 0.99)
        
    def test_persistence(self):
        logger.info("Test 3: Persistence")
        
        cfg = Config(check_interval=300)
        m = Monitor(url="test.com", config=cfg)
        
        # Serialize
        data = m.to_dict()
        self.assertIn("config", data)
        self.assertEqual(data["config"]["check_interval"], 300)
        
        # Deserialize
        m_loaded = Monitor.from_dict(data)
        self.assertIsNotNone(m_loaded.config)
        self.assertEqual(m_loaded.config.check_interval, 300)

if __name__ == '__main__':
    unittest.main()
