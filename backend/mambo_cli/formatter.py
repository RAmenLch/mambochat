"""两级帮助：常用模式（-h）隐藏 advanced 参数并标注高级子命令，--help-all 显示全部。"""
from __future__ import annotations

import argparse
import sys


class LeveledHelpFormatter(argparse.HelpFormatter):
    """常用模式过滤 advanced 参数；show_advanced=True 时显示全部。"""

    def __init__(self, prog, show_advanced=False, **kwargs):
        super().__init__(prog, **kwargs)
        self.show_advanced = show_advanced
        self.parser = None  # 由帮助 action 注入，用于统计高级项数量

    def _visible(self, actions):
        return [a for a in actions if self.show_advanced or not getattr(a, "advanced", False)]

    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, self._visible(actions), groups, prefix)

    def add_arguments(self, actions):
        super().add_arguments(self._visible(actions))

    def _expand_help(self, action):
        text = super()._expand_help(action)
        if not self.show_advanced and getattr(action, "advanced", False):
            return ("[高级] " + text) if text else "[高级]"
        return text

    def _count_advanced(self, parser) -> int:
        count = sum(1 for a in parser._actions if getattr(a, "advanced", False))
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                count += sum(
                    1 for sp in action._name_parser_map.values() if getattr(sp, "advanced", False)
                )
        return count

    def format_help(self):
        text = super().format_help()
        if self.parser is not None:
            if not self.show_advanced and getattr(self.parser, "help_epilog_common", None):
                text += "\n" + self.parser.help_epilog_common + "\n"
            elif self.show_advanced and getattr(self.parser, "help_epilog_all", None):
                text += "\n" + self.parser.help_epilog_all + "\n"
            count = self._count_advanced(self.parser)
            if not self.show_advanced:
                if count:
                    text += f"\n提示: 还有 {count} 个高级参数/命令未显示，使用 --help-all 查看全部。\n"
            elif count == 0:
                text += "\n（该命令没有高级参数/命令，--help-all 与 -h 显示相同）\n"
        return text


def format_parser_help(parser: argparse.ArgumentParser, show_advanced: bool = False) -> str:
    """渲染两级帮助：show_advanced=False 隐藏高级参数并标注高级子命令。"""
    formatter = parser._get_formatter()
    formatter.show_advanced = show_advanced
    formatter.parser = parser
    formatter.add_usage(parser.usage, parser._actions, parser._mutually_exclusive_groups)
    formatter.add_text(parser.description)
    for action_group in parser._action_groups:
        formatter.start_section(action_group.title)
        formatter.add_text(action_group.description)
        formatter.add_arguments(action_group._group_actions)
        formatter.end_section()
    formatter.add_text(parser.epilog)
    return formatter.format_help()


class _LeveledHelpAction(argparse.Action):
    """-h 显示常用帮助；--help-all 显示完整帮助。"""

    def __init__(self, option_strings, dest, show_advanced=False, **kwargs):
        kwargs.setdefault("nargs", 0)
        super().__init__(option_strings, dest, **kwargs)
        self._show_advanced = show_advanced

    def __call__(self, parser, namespace, values, option_string=None):
        parser._print_message(
            format_parser_help(parser, show_advanced=self._show_advanced),
            sys.stdout,
        )
        parser.exit()


def add_leveled_help(parser: argparse.ArgumentParser, all_help: str = "显示全部参数（含高级）") -> None:
    parser.add_argument(
        "-h", "--help", action=_LeveledHelpAction, show_advanced=False,
        help="显示常用帮助（完整参数见 --help-all）",
    )
    parser.add_argument("--help-all", action=_LeveledHelpAction, show_advanced=True, help=all_help)


def add_arg(parser: argparse.ArgumentParser, *args, advanced: bool = False, **kwargs):
    """添加参数；advanced=True 时仅在 --help-all 中展示（常用模式隐藏）。"""
    action = parser.add_argument(*args, **kwargs)
    action.advanced = advanced
    return action


def mark_advanced(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """将子命令解析器标记为高级：常用模式的帮助中标注 [高级]。"""
    parser.advanced = True
    return parser
