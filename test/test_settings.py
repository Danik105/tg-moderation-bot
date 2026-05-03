"""
tests/test_settings.py

Функции _require/_load_telethon_credentials вызывают os.getenv() в рантайме,
поэтому patch.dict должен быть активен во время вызова, а не только при exec.
Тестируем логику через постоянно активный patch.dict на уровне теста.
"""
import sys
import os
import json
import types
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_settings_with_env(extra_env=None):
    """Загружает settings.py с полным набором обязательных переменных."""
    env = {
        'BOT_TOKEN': 'test:bot:token',
        'API_ID': '12345',
        'API_HASH': 'testhash',
        'ADMIN_IDS': '1,2,3',
    }
    if extra_env:
        env.update(extra_env)
    return env


_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_settings_path = os.path.join(_base, 'config', 'settings.py')


def _exec_mod(env):
    """Загружает config/settings.py внутри patch.dict и возвращает модуль."""
    with open(_settings_path, 'r', encoding='utf-8') as f:
        source = f.read()
    mod = types.ModuleType('_settings_isolated')
    mod.__file__ = _settings_path
    with patch.dict(os.environ, env, clear=False):
        exec(compile(source, _settings_path, 'exec'), mod.__dict__)
    return mod, env


class TestRequire(unittest.TestCase):
    def test_raises_if_missing(self):
        env = _load_settings_with_env()
        mod, env = _exec_mod(env)
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError):
                mod._require('__MISSING_KEY_XYZ__')

    def test_returns_value_if_set(self):
        env = _load_settings_with_env({'MY_KEY': 'hello'})
        mod, env = _exec_mod(env)
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(mod._require('MY_KEY'), 'hello')


class TestSaveTelethonCredentials(unittest.TestCase):
    def test_saves_json_file(self):
        tmpdir = tempfile.mkdtemp()
        orig_dir = os.getcwd()
        os.chdir(tmpdir)
        try:
            env = _load_settings_with_env()
            mod, _ = _exec_mod(env)
            mod.save_telethon_credentials(88888, 'savehash')
            with open('credentials.json') as f:
                data = json.load(f)
            self.assertEqual(data['API_ID'], 88888)
            self.assertEqual(data['API_HASH'], 'savehash')
        finally:
            os.chdir(orig_dir)

    def test_file_contains_valid_json(self):
        tmpdir = tempfile.mkdtemp()
        orig_dir = os.getcwd()
        os.chdir(tmpdir)
        try:
            env = _load_settings_with_env()
            mod, _ = _exec_mod(env)
            mod.save_telethon_credentials(1, 'h')
            with open('credentials.json') as f:
                data = json.load(f)
            self.assertIn('API_ID', data)
            self.assertIn('API_HASH', data)
        finally:
            os.chdir(orig_dir)


class TestLoadTelethonCredentials(unittest.TestCase):
    def test_loads_from_credentials_json(self):
        tmpdir = tempfile.mkdtemp()
        orig_dir = os.getcwd()
        os.chdir(tmpdir)
        try:
            creds = {'API_ID': 77777, 'API_HASH': 'filehash'}
            with open('credentials.json', 'w') as f:
                json.dump(creds, f)
            env = _load_settings_with_env()
            mod, env = _exec_mod(env)
            with patch.dict(os.environ, env, clear=False):
                api_id, api_hash = mod._load_telethon_credentials()
            self.assertEqual(api_id, 77777)
            self.assertEqual(api_hash, 'filehash')
        finally:
            os.chdir(orig_dir)

    def test_falls_back_to_env(self):
        tmpdir = tempfile.mkdtemp()
        orig_dir = os.getcwd()
        os.chdir(tmpdir)
        try:
            env = _load_settings_with_env({'API_ID': '55555', 'API_HASH': 'envhash'})
            mod, env = _exec_mod(env)
            with patch.dict(os.environ, env, clear=False):
                api_id, api_hash = mod._load_telethon_credentials()
            self.assertEqual(api_id, 55555)
            self.assertEqual(api_hash, 'envhash')
        finally:
            os.chdir(orig_dir)


class TestSettingsAdminIds(unittest.TestCase):
    def _make_settings(self, admin_ids_str):
        env = _load_settings_with_env({'ADMIN_IDS': admin_ids_str})
        mod, env = _exec_mod(env)
        with patch.dict(os.environ, env, clear=False):
            return mod.Settings()

    def test_parses_multiple_admin_ids(self):
        s = self._make_settings('100,200,300')
        self.assertEqual(s.admin_ids, [100, 200, 300])

    def test_empty_admin_ids(self):
        s = self._make_settings('')
        self.assertEqual(s.admin_ids, [])

    def test_ignores_non_digit_entries(self):
        s = self._make_settings('111,abc,222')
        self.assertEqual(s.admin_ids, [111, 222])

    def test_single_admin(self):
        s = self._make_settings('42')
        self.assertEqual(s.admin_ids, [42])

    def test_default_db_path(self):
        s = self._make_settings('1')
        self.assertEqual(s.db_path, 'users.db')


if __name__ == '__main__':
    unittest.main(verbosity=2)
