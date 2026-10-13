"""prefix_palette.py のユニットテスト."""

import unittest
from prefix_palette import PaletteTransformer, VariableRenamer


class TestVariableRenamer(unittest.TestCase):
    """VariableRenamer 単体のロジック検証."""

    def test_prefix_starts_with_same_letter(self):
        """プレフィックスと同じ文字で始まる変数も正常に付与されること."""
        renamer = VariableRenamer(prefix="魔")
        renamer.register_variable("魔力")
        self.assertEqual(renamer.format_name("魔力"), "魔魔力")

    def test_numeric_reference_is_not_target(self):
        """数値のみの参照（固定値）は置換対象外となること."""
        renamer = VariableRenamer(prefix="01", rename_all_refs=False)
        self.assertFalse(renamer.is_target_reference("13"))
        self.assertFalse(renamer.is_target_reference("-1"))
        self.assertFalse(renamer.is_target_reference("１３"))

    def test_unregistered_reference_with_all_refs(self):
        """--all-refs 有効時、未定義変数のみ置換対象になること."""
        renamer = VariableRenamer(prefix="01", rename_all_refs=True)
        self.assertTrue(renamer.is_target_reference("HP"))
        self.assertFalse(renamer.is_target_reference("13"))


class TestPaletteTransformer(unittest.TestCase):
    """PaletteTransformer によるテキスト変換の統合検証."""

    def setUp(self):
        self.renamer = VariableRenamer(prefix="01")
        self.transformer = PaletteTransformer(renamer=self.renamer)

    def test_basic_transformation(self):
        """定義、参照、右辺代入がすべて正しく置換されること."""
        text = (
            "2d+{冒険者}+{器用B} 判定\n"
            "//器用度=22\n"
            "//器用={器用度}\n"
            "//器用B=(({器用})/6)\n"
            "//冒険者=7\n"
        )
        expected = (
            "2d+{01冒険者}+{01器用B} 判定\n"
            "//01器用度=22\n"
            "//01器用={01器用度}\n"
            "//01器用B=(({01器用})/6)\n"
            "//01冒険者=7\n"
        )
        self.assertEqual(self.transformer.transform(text), expected)

    def test_numeric_bracket_ignored(self):
        """k10[13] などの固定値参照が置換されないこと."""
        text = "k10[(13)]+{神聖魔法} 回復\n//神聖魔法=5\n"
        expected = "k10[(13)]+{01神聖魔法} 回復\n//01神聖魔法=5\n"
        self.assertEqual(self.transformer.transform(text), expected)

    def test_whitespace_preservation(self):
        """インデントや波括弧内の空白が維持されること."""
        text = "  //器用度=22\n  2d+{ 器用度 } 判定\n"
        expected = "  //01器用度=22\n  2d+{ 01器用度 } 判定\n"
        self.assertEqual(self.transformer.transform(text), expected)

    def test_already_prefixed_detection(self):
        """変換済みファイルの検出フラグが立つこと."""
        text = "//01器用度=22\n//01知力=10\n"
        self.transformer.transform(text)
        self.assertTrue(self.renamer.looks_already_prefixed())

    def test_reset_between_calls(self):
        """連続実行時に前回の定義が混ざらないこと."""
        self.transformer.transform("//器用度=22\n")
        self.assertIn("器用度", self.renamer.known_variables)

        self.transformer.transform("//敏捷度=20\n")
        self.assertNotIn("器用度", self.renamer.known_variables)
        self.assertIn("敏捷度", self.renamer.known_variables)


if __name__ == "__main__":
    unittest.main()