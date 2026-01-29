import unittest

from src_whisper.utils.asr_subjects import (
    build_asr_subjects,
    is_subject_allowed,
    normalize_asr_prefix,
    parse_allowed_suffixes,
)


class TestAsrSubjects(unittest.TestCase):
    def test_normalize_prefix_adds_trailing_dot(self) -> None:
        prefix, wildcard, warnings = normalize_asr_prefix("asr.whisper")
        self.assertEqual(prefix, "asr.whisper.")
        self.assertIsNone(wildcard)
        self.assertEqual(warnings, [])

    def test_normalize_prefix_preserves_wildcard(self) -> None:
        prefix, wildcard, warnings = normalize_asr_prefix("asr.whisper.>")
        self.assertEqual(prefix, "asr.whisper.")
        self.assertEqual(wildcard, "asr.whisper.>")
        self.assertIsInstance(warnings, list)

    def test_build_exact_requires_user_id(self) -> None:
        with self.assertRaises(ValueError):
            build_asr_subjects("asr.whisper.", None, "exact")

    def test_build_both(self) -> None:
        subjects, _warnings = build_asr_subjects("asr.whisper", "u1", "both")
        self.assertEqual(subjects.prefix, "asr.whisper.")
        self.assertEqual(subjects.exact_subject, "asr.whisper.u1")
        self.assertEqual(subjects.wildcard_subject, "asr.whisper.>")
        self.assertEqual(subjects.subjects, ("asr.whisper.u1", "asr.whisper.>"))

    def test_allowed_suffixes_parse(self) -> None:
        self.assertIsNone(parse_allowed_suffixes(""))
        self.assertEqual(parse_allowed_suffixes("a,b , c"), {"a", "b", "c"})

    def test_is_subject_allowed(self) -> None:
        allowed = {"test1", "team.a"}
        self.assertTrue(is_subject_allowed("asr.whisper.", "asr.whisper.test1", allowed))
        self.assertTrue(is_subject_allowed("asr.whisper.", "asr.whisper.team.a", allowed))
        self.assertFalse(is_subject_allowed("asr.whisper.", "asr.whisper.evil", allowed))
        self.assertFalse(is_subject_allowed("asr.whisper.", "other.test1", allowed))

