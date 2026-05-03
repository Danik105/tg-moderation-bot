"""
tests/test_posting_state.py
"""
import sys
import os
import json
import asyncio
import tempfile
import unittest
from unittest.mock import MagicMock

for mod in ['aiogram', 'aiogram.types', 'aiogram.filters', 'aiogram.fsm.context',
            'aiogram.fsm.state', 'telethon', 'telethon.tl', 'telethon.tl.types',
            'g4f', 'g4f.client']:
    sys.modules.setdefault(mod, MagicMock())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util

def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state_mod = _load_module('posting.state', os.path.join(_base, 'posting', 'state.py'))
PostingState = state_mod.PostingState
PostEntry = state_mod.PostEntry
DEFAULT_PROMPT = state_mod.DEFAULT_PROMPT


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestPostingStateBasic(unittest.TestCase):
    def setUp(self):
        self.state = PostingState()

    def test_add_post_returns_index(self):
        idx = run(self.state.add_post(PostEntry(clean_text="hello")))
        self.assertEqual(idx, 0)

    def test_add_multiple_posts_increments_index(self):
        for i in range(3):
            idx = run(self.state.add_post(PostEntry(clean_text=f"post {i}")))
            self.assertEqual(idx, i)

    def test_get_post_existing(self):
        idx = run(self.state.add_post(PostEntry(clean_text="test post")))
        result = run(self.state.get_post(idx))
        self.assertIsNotNone(result)
        self.assertEqual(result.clean_text, "test post")

    def test_get_post_out_of_bounds(self):
        self.assertIsNone(run(self.state.get_post(999)))

    def test_get_post_negative_index(self):
        self.assertIsNone(run(self.state.get_post(-1)))

    def test_remove_post_returns_entry(self):
        idx = run(self.state.add_post(PostEntry(clean_text="removable")))
        removed = run(self.state.remove_post(idx))
        self.assertIsNotNone(removed)
        self.assertEqual(removed.clean_text, "removable")

    def test_remove_post_actually_removes(self):
        idx = run(self.state.add_post(PostEntry(clean_text="gone")))
        run(self.state.remove_post(idx))
        self.assertIsNone(run(self.state.get_post(0)))

    def test_remove_post_invalid_index(self):
        self.assertIsNone(run(self.state.remove_post(999)))

    def test_pending_posts_only_pending(self):
        run(self.state.add_post(PostEntry(clean_text="pending")))
        run(self.state.add_post(PostEntry(clean_text="done", status="published")))
        pending = run(self.state.pending_posts())
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0][1].clean_text, "pending")

    def test_pending_count(self):
        for _ in range(3):
            run(self.state.add_post(PostEntry(clean_text="p")))
        run(self.state.add_post(PostEntry(clean_text="done", status="published")))
        self.assertEqual(run(self.state.pending_count()), 3)

    def test_default_prompt_set(self):
        self.assertEqual(self.state.prompt, DEFAULT_PROMPT)

    def test_default_sources_empty(self):
        self.assertEqual(self.state.sources, [])

    def test_default_target_none(self):
        self.assertIsNone(self.state.target_chat)


class TestPostingStatePersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_dir = os.getcwd()
        os.chdir(self.tmpdir)
        self.state = PostingState()

    def tearDown(self):
        os.chdir(self.orig_dir)

    def test_save_and_load_sources(self):
        self.state.sources = ['@channel1', '@channel2']
        self.state.save_sources()
        new_state = PostingState()
        new_state._load_sources()
        self.assertEqual(new_state.sources, ['@channel1', '@channel2'])

    def test_save_and_load_target(self):
        self.state.target_chat = '@my_target'
        self.state.save_target()
        new_state = PostingState()
        new_state._load_target()
        self.assertEqual(new_state.target_chat, '@my_target')

    def test_save_and_load_config(self):
        self.state.prompt = "Custom prompt {text}"
        self.state.save_config()
        new_state = PostingState()
        new_state._load_config()
        self.assertEqual(new_state.prompt, "Custom prompt {text}")

    def test_save_and_load_links(self):
        self.state.signature_links = [
            {"label": "CHAT", "url": "https://t.me/chat"},
            {"label": "CHANNEL", "url": "https://t.me/channel"},
        ]
        self.state.save_links()
        new_state = PostingState()
        new_state._load_links()
        self.assertEqual(new_state.signature_links, self.state.signature_links)

    def test_load_missing_files_no_crash(self):
        try:
            PostingState().load_all()
        except Exception as e:
            self.fail(f"load_all() упал: {e}")

    def test_load_corrupted_json_no_crash(self):
        with open('config.json', 'w') as f:
            f.write("{invalid json}")
        new_state = PostingState()
        try:
            new_state._load_config()
        except Exception as e:
            self.fail(f"_load_config() упал с повреждённым JSON: {e}")
        self.assertEqual(new_state.prompt, DEFAULT_PROMPT)

    def test_backward_compat_links_format(self):
        old_format = {"chat_link": "https://t.me/oldchat", "channel_link": "https://t.me/oldchannel"}
        with open('links.json', 'w') as f:
            json.dump(old_format, f)
        new_state = PostingState()
        new_state._load_links()
        urls = [l['url'] for l in new_state.signature_links]
        self.assertIn("https://t.me/oldchat", urls)
        self.assertIn("https://t.me/oldchannel", urls)


class TestPostEntry(unittest.TestCase):
    def test_default_status_pending(self):
        self.assertEqual(PostEntry(clean_text="hello").status, "pending")

    def test_default_aiogram_message_ids_empty(self):
        self.assertEqual(PostEntry(clean_text="hello").aiogram_message_ids, [])

    def test_default_media_none(self):
        self.assertIsNone(PostEntry(clean_text="hello").media)

    def test_custom_status(self):
        self.assertEqual(PostEntry(clean_text="done", status="published").status, "published")


if __name__ == '__main__':
    unittest.main(verbosity=2)
