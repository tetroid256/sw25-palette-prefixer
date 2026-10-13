"""ソード・ワールド2.5 チャットパレット変数プレフィックス付与スクリプト.

ゆとシートから出力されたチャットパレットテキスト内の変数定義（//変数名=値）および
変数参照（{変数名}）を走査し、指定したプレフィックス（例: 01, PC1_ 等）を一括付与します。
"""

import argparse
import re
import sys
from pathlib import Path

# 接頭辞に含めるとパレット構文が壊れる文字
_INVALID_PREFIX_CHARS = re.compile(r"[\s={}]")
# ファイル名に使えない文字（Windows 基準）
_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')
# {13} {-1} {１３} などの固定値（\d は全角数字にもマッチする）
_INTEGER_PATTERN = re.compile(r"[+-]?\d+")

_READ_ENCODINGS = ("utf-8-sig", "cp932")


class VariableRenamer:
    """変数名へのプレフィックス付与と、置換対象かどうかの判定を行うクラス."""

    def __init__(self, prefix: str, rename_all_refs: bool = False) -> None:
        """イニシャライザ.

        Args:
            prefix: 変数名の先頭に付与するプレフィックス文字列。
            rename_all_refs: True の場合、パレット内で定義されていない参照
                （ココフォリアのステータス参照など）も数値以外はすべて置換する。
        """
        self.prefix = prefix
        self.rename_all_refs = rename_all_refs
        self.known_variables: set[str] = set()

    def reset(self) -> None:
        """登録済みの変数定義をクリアする."""
        self.known_variables.clear()

    def register_variable(self, var_name: str) -> None:
        """定義された変数名を登録する."""
        self.known_variables.add(var_name)

    def format_name(self, var_name: str) -> str:
        """プレフィックスを付与した変数名を返す."""
        return f"{self.prefix}{var_name}"

    def is_target_reference(self, name: str) -> bool:
        """参照名がプレフィックス付与対象かを判定する."""
        if name in self.known_variables:
            return True
        if self.rename_all_refs:
            return _INTEGER_PATTERN.fullmatch(name) is None
        return False

    def looks_already_prefixed(self) -> bool:
        """定義済み変数がすべて接頭辞で始まっている（変換済みらしい）かを返す."""
        return bool(self.known_variables) and all(
            v.startswith(self.prefix) for v in self.known_variables
        )


class PaletteTransformer:
    """チャットパレット全体の走査・変換を行うクラス."""

    # 変数定義行: (行頭空白 + //)(変数名)=(値)
    DEF_PATTERN = re.compile(r"^(\s*//)([^=\s]+)=(.*)$")
    # 変数参照: {(前空白)(変数名)(後空白)} ※空白は位置を保ったまま残す
    REF_PATTERN = re.compile(r"\{(\s*)([^{}\s](?:[^{}]*[^{}\s])?)(\s*)\}")

    def __init__(self, renamer: VariableRenamer) -> None:
        self.renamer = renamer

    def _collect_definitions(self, lines: list[str]) -> None:
        """パレット全体から変数定義を先行走査して登録する."""
        for line in lines:
            match = self.DEF_PATTERN.match(line)
            if match:
                self.renamer.register_variable(match.group(2))

    def _replace_references(self, text: str) -> str:
        """テキスト内の {変数名} を置換する."""

        def repl(match: re.Match[str]) -> str:
            lead, name, trail = match.groups()
            if not self.renamer.is_target_reference(name):
                return match.group(0)
            return f"{{{lead}{self.renamer.format_name(name)}{trail}}}"

        return self.REF_PATTERN.sub(repl, text)

    def transform_line(self, line: str) -> str:
        """1行分の変数定義および参照を置換する（インデント・行末空白は保持）."""
        def_match = self.DEF_PATTERN.match(line)
        if def_match:
            head, name, expr = def_match.groups()
            new_name = self.renamer.format_name(name)
            # 右辺の値の中にある参照（例: //器用={器用度}）も置換
            return f"{head}{new_name}={self._replace_references(expr)}"
        return self._replace_references(line)

    def transform(self, content: str) -> str:
        """テキスト全体を変換して返す. 呼び出しごとに定義一覧はリセットされる."""
        self.renamer.reset()
        # read_text は改行を \n に正規化済み。split なら末尾改行の有無も保たれる
        lines = content.split("\n")
        self._collect_definitions(lines)
        return "\n".join(self.transform_line(line) for line in lines)


def read_palette(path: Path) -> tuple[str, str]:
    """パレットファイルを読み込み、(本文, 使用した文字コード) を返す."""
    for encoding in _READ_ENCODINGS:
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            continue
    tried = ", ".join(_READ_ENCODINGS)
    raise ValueError(f"文字コードを判別できませんでした（試行: {tried}）: {path}")


def write_palette(path: Path, content: str) -> None:
    """変換結果を UTF-8 で書き出す."""
    path.write_text(content, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    """コマンドライン引数パーサーを構築する."""
    parser = argparse.ArgumentParser(
        description=(
            "SW2.5のチャットパレットテキスト内にある変数にプレフィックスを付与します。"
            "入力は UTF-8 / Shift-JIS(CP932) に対応し、出力は常に UTF-8 です。"
        )
    )
    parser.add_argument("input", type=Path, help="変換対象のチャットパレットテキストファイル (.txt)")
    parser.add_argument(
        "-p", "--prefix", default="01",
        help="変数名の先頭に付与する接頭辞 (デフォルト: '01')",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="出力先ファイルパス (省略時は [入力ファイル名]_[prefix].txt)",
    )
    parser.add_argument(
        "--all-refs", action="store_true",
        help="パレット内で定義されていない参照（{HP} 等）も数値以外はすべて置換する",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="変換済みと思われるファイルでも強制的に変換する",
    )
    return parser


def main() -> None:
    """CLI エントリーポイント."""
    parser = build_arg_parser()
    args = parser.parse_args()

    input_path: Path = args.input
    prefix: str = args.prefix

    if not prefix:
        parser.error("接頭辞が空です。")
    if _INVALID_PREFIX_CHARS.search(prefix):
        parser.error("接頭辞に空白・'='・'{'・'}' は使えません。")
    if not input_path.is_file():
        parser.error(f"入力ファイルが見つかりません: {input_path}")

    if args.output is not None:
        output_path: Path = args.output
    else:
        if _INVALID_FILENAME_CHARS.search(prefix):
            parser.error("接頭辞にファイル名で使えない文字が含まれています。-o で出力先を指定してください。")
        output_path = input_path.with_name(f"{input_path.stem}_{prefix}{input_path.suffix}")

    try:
        content, encoding = read_palette(input_path)
    except ValueError as e:
        parser.exit(1, f"エラー: {e}\n")

    renamer = VariableRenamer(prefix=prefix, rename_all_refs=args.all_refs)
    transformer = PaletteTransformer(renamer=renamer)
    result = transformer.transform(content)

    if renamer.looks_already_prefixed() and not args.force:
        parser.exit(
            1,
            f"エラー: すべての変数が既に '{prefix}' で始まっています。変換済みのファイルではありませんか？\n"
            "意図した変換であれば --force を付けて再実行してください。\n",
        )
    if not renamer.known_variables and not args.all_refs:
        print(
            "警告: 変数定義（//変数名=値）が見つからなかったため、何も置換していません。",
            file=sys.stderr,
        )

    write_palette(output_path, result)
    print(
        f"変換完了: '{input_path}' ({encoding}) -> '{output_path}' "
        f"(Prefix: '{prefix}', 変数 {len(renamer.known_variables)} 件)"
    )


if __name__ == "__main__":
    main()