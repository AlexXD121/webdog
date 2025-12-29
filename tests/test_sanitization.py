import unittest
import sys
from pathlib import Path
import html

# Adjust path
sys.path.append(str(Path(__file__).parent.parent / "webdog_bot"))

from interface import escape_html, format_diff_message

class TestSanitization(unittest.TestCase):
    def test_escape_html(self):
        unsafe = "<script>alert('xss')</script>"
        safe = escape_html(unsafe)
        self.assertEqual(safe, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")

    def test_format_diff_message_sanitization(self):
        url = "http://malicious.com/?a=<b>bold</b>"
        diff = "<script>bad()</script>"
        msg = format_diff_message(url, 0.5, "TEST", diff)
        
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", msg)
        self.assertIn("&lt;script&gt;", msg)
        self.assertNotIn("<script>", msg)

if __name__ == '__main__':
    unittest.main()
