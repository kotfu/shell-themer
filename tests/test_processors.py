#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2023 Jared Crapo
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# pylint: disable=protected-access, missing-function-docstring, redefined-outer-name
# pylint: disable=missing-module-docstring, unused-variable

import pytest
import rich.style
import rich.errors

from shell_themer import Themer


#
# test environment rendering
#
def test_render_environment_unset_list(thm, capsys):
    exit_code = thm.render(["ls"])
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert out
    assert not err
    assert "unset SOMEVAR" in out
    assert "unset ANOTHERVAR" in out
    assert 'export LS_COLORS="ace ventura"' in out


def test_render_environment_unset_string(thm, capsys):
    # we are testing a string domain instead of a list here on purpose
    exit_code = thm.render("unset")
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert out
    assert not err
    assert "unset NOLISTVAR" in out


#
# test the fzf processor
#
ATTRIBS_TO_FZF = [
    ("bold", "regular:bold"),
    ("underline", "regular:underline"),
    ("reverse", "regular:reverse"),
    ("dim", "regular:dim"),
    ("italic", "regular:italic"),
    ("strike", "regular:strikethrough"),
    ("bold underline", "regular:bold:underline"),
    ("underline italic", "regular:underline:italic"),
    ("italic underline", "regular:underline:italic"),
]


@pytest.mark.parametrize("styledef, fzf", ATTRIBS_TO_FZF)
def test_fzf_attribs_from_style(thm, styledef, fzf):
    style = rich.style.Style.parse(styledef)
    assert fzf == thm._fzf_attribs_from_style(style)


STYLE_TO_FZF = [
    # text, current_line, and preview styles have special processing
    # for foreground and background colors
    ("text", "", ""),
    ("text", "default", "fg:-1:regular"),
    ("text", "default on default", "fg:-1:regular,bg:-1"),
    ("text", "bold default on default underline", "fg:-1:regular:bold:underline,bg:-1"),
    ("text", "white on bright_red", "fg:7:regular,bg:9"),
    ("text", "bright_white", "fg:15:regular"),
    ("text", "bright_yellow on color(4)", "fg:11:regular,bg:4"),
    ("text", "green4", "fg:28:regular"),
    ("current_line", "navy_blue dim on grey82", "fg+:17:regular:dim,bg+:252"),
    # other styles do not
    ("preview", "#af00ff on bright_white", "preview-fg:#af00ff:regular,preview-bg:15"),
    ("border", "magenta", "border:5:regular"),
    ("query", "#2932dc", "query:#2932dc:regular"),
]


@pytest.mark.parametrize("name, styledef, fzf", STYLE_TO_FZF)
def test_fzf_from_style(thm, name, styledef, fzf):
    style = rich.style.Style.parse(styledef)
    assert fzf == thm._fzf_from_style(name, style)


def test_fzf_opts(thm_base, capsys):
    tomlstr = """
[domain.fzf]
processor = "fzf"
environment_variable = "QQQ"
opt."+i" = true
opt.--border = "rounded"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert not err
    assert out == """export QQQ=" +i --border='rounded'"\n"""


def test_fzf_no_opts(thm_base, capsys):
    tomlstr = """
[domain.fzf]
processor = "fzf"
environment_variable = "QQQ"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert not err
    assert out == """export QQQ=""\n"""


def test_fzf_no_varname(thm_base, capsys):
    tomlstr = """
[domain.fzf]
processor = "fzf"
opt."+i" = true
opt.--border = "rounded"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_ERROR
    assert not out
    assert "fzf processor requires 'environment_variable'" in err


#
# test the ls_colors processor
#
# we only reallly have to test that the style name maps to the right code in ls_colors
# ie directory -> di, or setuid -> su. The ansi codes are created by rich.style
# so we don't really need to test much of that
STYLE_TO_LSCOLORS = [
    ("text", "", ""),
    ("text", "default", "no=0"),
    ("file", "default", "fi=0"),
    ("directory", "#8be9fd", "di=38;2;139;233;253"),
    ("symlink", "green4 bold", "ln=1;38;5;28"),
    ("multi_hard_link", "blue on white", "mh=34;47"),
    ("pipe", "#f8f8f2 on #44475a underline", "pi=4;38;2;248;248;242;48;2;68;71;90"),
    ("socket", "bright_white", "so=97"),
    ("door", "bright_white", "do=97"),
    ("block_device", "default", "bd=0"),
    ("character_device", "black", "cd=30"),
    ("broken_symlink", "bright_blue", "or=94"),
    ("missing_symlink_target", "bright_blue", "mi=94"),
    ("setuid", "bright_blue", "su=94"),
    ("setgid", "bright_red", "sg=91"),
    ("sticky", "blue_violet", "st=38;5;57"),
    ("other_writable", "blue_violet italic", "ow=3;38;5;57"),
    ("sticky_other_writable", "deep_pink2 on #ffffaf", "tw=38;5;197;48;2;255;255;175"),
    ("executable_file", "cornflower_blue on grey82", "ex=38;5;69;48;5;252"),
    ("file_with_capability", "red on black", "ca=31;40"),
]


@pytest.mark.parametrize("name, styledef, lsc", STYLE_TO_LSCOLORS)
def test_ls_colors_from_style(thm_base, name, styledef, lsc):
    style = rich.style.Style.parse(styledef)
    assert lsc == thm_base._ls_colors_from_style(name, style)


def test_ls_colors_no_styles(thm_base, capsys):
    tomlstr = """
[domain.lsc]
processor = "ls_colors"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert not err
    assert out == 'export LS_COLORS=""\n'


def test_ls_colors_environment_variable(thm_base, capsys):
    tomlstr = """
[domain.lsc]
processor = "ls_colors"
environment_variable = "OTHER_LS_COLOR"
style.file = "default"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert not err
    assert out == 'export OTHER_LS_COLOR="fi=0"\n'


def test_ls_colors_clear_builtin(thm_base, capsys):
    tomlstr = """
[domain.lsc]
processor = "ls_colors"
clear_builtin = true
style.directory = "bright_blue"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert not err
    assert (
        out
        == 'export LS_COLORS="no=0:fi=0:di=94:ln=0:mh=0:pi=0:so=0:do=0:bd=0:cd=0:or=0:mi=0:su=0:sg=0:st=0:ow=0:tw=0:ex=0:ca=0"\n'
    )


def test_ls_colors_clear_builtin_not_boolean(thm_base, capsys):
    tomlstr = """
[domain.lsc]
processor = "ls_colors"
clear_builtin = "error"
style.directory = "bright_blue"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_ERROR
    assert not out
    assert "'clear_builtin' to be boolean" in err


#
# test the iterm processor
#
def test_iterm(thm_base, capsys):
    tomlstr = """
[domain.iterm]
processor = "iterm"
style.foreground = "#ffeebb"
style.background = "#221122"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert not err
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[0] == r'builtin echo -e "\e]1337;SetColors=fg=ffeebb\a"'
    assert lines[1] == r'builtin echo -e "\e]1337;SetColors=bg=221122\a"'


def test_iterm_bgonly(thm_base, capsys):
    tomlstr = """
[domain.iterm]
processor = "iterm"
style.background = "#b2cacd"
    """
    thm_base.loads(tomlstr)
    exit_code = thm_base.render()
    out, err = capsys.readouterr()
    assert exit_code == Themer.EXIT_SUCCESS
    assert not err
    lines = out.splitlines()
    assert len(lines) == 1
    assert lines[0] == r'builtin echo -e "\e]1337;SetColors=bg=b2cacd\a"'