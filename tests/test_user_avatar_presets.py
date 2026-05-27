import os
import tempfile
import unittest

import app as toursim_app


class UserAvatarPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_avatar_dir = toursim_app.USER_AVATAR_DIR
        toursim_app.USER_AVATAR_DIR = os.path.join(self.temp_dir.name, "avatars")

    def tearDown(self):
        toursim_app.USER_AVATAR_DIR = self.old_avatar_dir
        self.temp_dir.cleanup()

    def test_avatar_gallery_exposes_twenty_unique_static_presets(self):
        presets = toursim_app.get_preset_avatar_options()

        self.assertEqual(len(presets), 20)
        self.assertEqual(len({preset["id"] for preset in presets}), 20)
        self.assertEqual(len({preset["path"] for preset in presets}), 20)
        for preset in presets:
            self.assertTrue(preset["path"].startswith("images/avatars/chrome-avatar-"))
            self.assertTrue(preset["path"].endswith(".svg"))
            self.assertTrue(toursim_app.is_preset_avatar_path(preset["path"]))

    def test_default_avatar_uses_preset_gallery_without_generating_legacy_svg(self):
        avatar_path = toursim_app.ensure_user_avatar_asset("alice", 7)

        self.assertTrue(toursim_app.is_preset_avatar_path(avatar_path))
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir.name, "avatars", "alice_7.svg")))

    def test_invalid_preset_choice_falls_back_to_deterministic_gallery_avatar(self):
        default_path = toursim_app.ensure_user_avatar_asset("alice", 7)
        resolved_path = toursim_app.select_preset_avatar_path("../uploads/avatars/old.svg", "alice", 7)

        self.assertEqual(resolved_path, default_path)
        self.assertTrue(toursim_app.is_preset_avatar_path(resolved_path))


if __name__ == "__main__":
    unittest.main()
