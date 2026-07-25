import os
import sys
import unittest

# Ensure parent directory is in sys.path for pii_masker imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from pii_masker.model import PIIMasker, MaskResult, EntityMatch

__all__ = ["PIIMasker", "MaskResult", "EntityMatch"]

if __name__ == "__main__":
    class TestPIIMasker(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.masker = PIIMasker()
            
        def test_mask_pii(self):
            input_text = "My name is John Doe and my SSN is 123-45-6789."
            masked_text, _ = self.masker.mask_pii(input_text)
            self.assertIn("[SSN]", masked_text)

        def test_extract_ssn(self):
            input_string = "My SSN is 987654320."
            ssn_dict = self.masker.extract_ssn(input_string)
            self.assertIn("987654320", ssn_dict)  

    unittest.main()