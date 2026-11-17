import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from website.runtime_paths import research_groups


class ResearchGroupConfigTests(unittest.TestCase):
    def test_missing_config_is_empty_or_explicitly_required(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'TELEGRAM_RESEARCH_CONFIG':str(Path(folder)/'missing.json')}):
            self.assertEqual(research_groups(),[])
            with self.assertRaises(ValueError):research_groups(required=True)

    def test_valid_private_group_alias_and_dates(self):
        row={'name':'Synthetic research group','archive':'group_a','start':'2020-01-01','split':'2024-01-01'}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'groups.json';path.write_text(json.dumps([row]))
            with patch.dict(os.environ,{'TELEGRAM_RESEARCH_CONFIG':str(path)}):
                self.assertEqual(research_groups(required=True),[row])

    def test_traversal_duplicate_aliases_and_reversed_dates_are_rejected(self):
        row={'name':'Synthetic research group','archive':'group_a','start':'2020-01-01','split':'2024-01-01'}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'groups.json'
            for rows in [[dict(row,archive='../escape')],[row,row],[dict(row,start='2025-01-01')]]:
                path.write_text(json.dumps(rows))
                with patch.dict(os.environ,{'TELEGRAM_RESEARCH_CONFIG':str(path)}):
                    with self.assertRaises(ValueError):research_groups()
