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
"""generator implementations and their base class"""

import abc
import re

import rich.color

from .interpolator import Interpolator
from .parsers import StyleParser
from .exceptions import ThemeError
from .utils import AssertBool


class GeneratorBase(abc.ABC, AssertBool):
    """Abstract Base Class for all generators

    Subclass and implement generate()

    Creates a registry of all subclasses in cls.generators

    The string to use in your theme configuration file is the underscored
    class name, ie:

    EnvironmentVariables -> environment_variables
    LsColors -> ls_colors
    """

    classmap = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # make a registry of subclasses as they are defined
        cls.classmap[cls._name_of(cls.__name__)] = cls

    ## TODO: move prog into an msgdata dictionary parameter
    def __init__(self, prog, scope, scopedef, styles, variables):
        super().__init__()
        self.prog = prog
        self.scope = scope
        self.scopedef = scopedef
        self.styles = styles
        self.variables = variables
        # create scope_styles, the styles parsed from scopedef
        try:
            raw_styles = scopedef["style"]
        except (KeyError, TypeError):
            raw_styles = {}
        interp = StyleParser(styles, variables)
        self.scope_styles = interp.parse_dict(raw_styles)

    @classmethod
    def _name_of(cls, name: str) -> str:
        """Make an underscored, lowercase form of the given class name."""
        name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)
        name = name.replace("-", "_")
        return name.lower()

    @abc.abstractmethod
    def generate(self) -> str:
        """generate a string of text, with newlines, which can be sourced by bash

        returns an empty string if there is nothing to generate
        """
        return ""


class LsColorsFromStyle:
    # TODO put all the error message stuff into a errdata or msgdata dictionary
    def ls_colors_from_style(self, name, style, mapp, scope):
        """create an entry suitable for LS_COLORS from a style

        name should be a valid LS_COLORS entry, could be a code representing
        a file type, or a glob representing a file extension

        style is a style object

        mapp is a dictionary of friendly color names to native color names
            ie map['directory'] = 'di'

        scope is the scope where this mapped occured, used for error message
        """
        ansicodes = ""
        if not style:
            return "", ""
        try:
            mapname = mapp[name]
        except KeyError as exc:
            # they used a style for a file attribute that we don't know how to map
            # i.e. style.text or style.directory we know what to do with, but
            # style.bundleid we don't know how to map, so we generate an error
            raise ThemeError(
                (
                    f"{self.prog}: unknown style '{name}' while processing"
                    f" scope '{scope}' using the 'ls_colors' generator"
                )
            ) from exc

        if style.color.type == rich.color.ColorType.DEFAULT:
            ansicodes = "0"
        else:
            # this works, but it uses a protected method
            #   ansicodes = style._make_ansi_codes(rich.color.ColorSystem.TRUECOLOR)
            # here's another approach, we ask the style to render a string, then
            # go peel the ansi codes out of the generated escape sequence
            ansistring = style.render("-----")
            # style.render uses this string to build it's output
            # f"\x1b[{attrs}m{text}\x1b[0m"
            # so let's go split it apart
            match = re.match(r"^\x1b\[([;\d]*)m", ansistring)
            # and get the numeric codes
            ansicodes = match.group(1)
        return mapname, f"{mapname}={ansicodes}"


class EnvironmentVariables(GeneratorBase):
    "generate statements to export and unset environment variables"

    def generate(self) -> str:
        out = []
        interp = Interpolator(self.styles, self.variables)
        try:
            unsets = self.scopedef["environment"]["unset"]
            if isinstance(unsets, str):
                # if they used a string in the config file instead of a list
                # process it like a single item instead of trying to process
                # each letter in the string
                unsets = [unsets]
            for unset in unsets:
                out.append(f"unset {interp.interpolate(unset)}")
        except KeyError:
            # no unsets
            pass
        # render the variables to export
        try:
            exports = self.scopedef["environment"]["export"]
            for var, value in exports.items():
                new_var = interp.interpolate(var)
                new_value = interp.interpolate(value)
                out.append(f'export {new_var}="{new_value}"')
        except KeyError:
            # no exports
            pass
        return "\n".join(out)


class Fzf(GeneratorBase):
    "generate fzf options and environment variables"

    def generate(self) -> str:
        """render attribs into a shell statement to set an environment variable"""
        optstr = ""
        interp = Interpolator(self.styles, self.variables)

        # process all the command line options
        try:
            opts = self.scopedef["opt"]
        except KeyError:
            opts = {}

        for key, value in opts.items():
            if isinstance(value, str):
                interp_value = interp.interpolate_variables(value)
                optstr += f" {key}='{interp_value}'"
            elif isinstance(value, bool) and value:
                optstr += f" {key}"

        # process all the styles
        colors = []
        # then add them back
        for name, style in self.scope_styles.items():
            colors.append(self._fzf_from_style(name, style))
        # turn off all the colors, and add our color strings
        try:
            colorbase = f"{self.scopedef['colorbase']},"
        except KeyError:
            colorbase = ""
        if colorbase or colors:
            colorstr = f" --color='{colorbase}{','.join(colors)}'"
        else:
            colorstr = ""

        # figure out which environment variable to put it in
        try:
            varname = self.scopedef["environment_variable"]
            varname = interp.interpolate_variables(varname)
            print(f'export {varname}="{optstr}{colorstr}"')
        except KeyError as exc:
            raise ThemeError(
                (
                    f"{self.prog}: fzf generator requires 'environment_variable'"
                    f" key to process scope '{self.scope}'"
                )
            ) from exc

    def _fzf_from_style(self, name, style):
        """turn a rich.style into a valid fzf color"""
        fzf = []
        if name == "text":
            # turn this into fg and bg color names
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"fg:{fzfc}:{fzfa}")
            if style.bgcolor:
                fzfc = self._fzf_color_from_rich_color(style.bgcolor)
                fzf.append(f"bg:{fzfc}")
        elif name == "current_line":
            # turn this into fg+ and bg+ color names
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"fg+:{fzfc}:{fzfa}")
            if style.bgcolor:
                fzfc = self._fzf_color_from_rich_color(style.bgcolor)
                fzf.append(f"bg+:{fzfc}")
        elif name == "preview":
            # turn this into fg+ and bg+ color names
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"preview-fg:{fzfc}:{fzfa}")
            if style.bgcolor:
                fzfc = self._fzf_color_from_rich_color(style.bgcolor)
                fzf.append(f"preview-bg:{fzfc}")
        else:
            # we only use the foreground color of the style, and ignore
            # any background color specified by the style
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"{name}:{fzfc}:{fzfa}")

        return ",".join(fzf)

    def _fzf_color_from_rich_color(self, color):
        """turn a rich.color into it's fzf equivilent"""
        fzf = ""

        if color.type == rich.color.ColorType.DEFAULT:
            fzf = "-1"
        elif color.type == rich.color.ColorType.STANDARD:
            # python rich uses underscores, fzf uses dashes
            fzf = str(color.number)
        elif color.type == rich.color.ColorType.EIGHT_BIT:
            fzf = str(color.number)
        elif color.type == rich.color.ColorType.TRUECOLOR:
            fzf = color.triplet.hex
        return fzf

    def _fzf_attribs_from_style(self, style):
        attribs = "regular"
        if style.bold:
            attribs += ":bold"
        if style.underline:
            attribs += ":underline"
        if style.reverse:
            attribs += ":reverse"
        if style.dim:
            attribs += ":dim"
        if style.italic:
            attribs += ":italic"
        if style.strike:
            attribs += ":strikethrough"
        return attribs


class LsColors(GeneratorBase, LsColorsFromStyle):
    "generator for LS_COLORS environment variable"
    LS_COLORS_BASE_MAP = {
        # map both a friendly name and the "real" name
        "text": "no",
        "file": "fi",
        "directory": "di",
        "symlink": "ln",
        "multi_hard_link": "mh",
        "pipe": "pi",
        "socket": "so",
        "door": "do",
        "block_device": "bd",
        "character_device": "cd",
        "broken_symlink": "or",
        "missing_symlink_target": "mi",
        "setuid": "su",
        "setgid": "sg",
        "sticky": "st",
        "other_writable": "ow",
        "sticky_other_writable": "tw",
        "executable_file": "ex",
        "file_with_capability": "ca",
    }
    # this map allows you to either use the 'native' color code, or the
    # 'friendly' name defined by shell-themer
    LS_COLORS_MAP = {}
    for friendly, actual in LS_COLORS_BASE_MAP.items():
        LS_COLORS_MAP[friendly] = actual
        LS_COLORS_MAP[actual] = actual

    def generate(self):
        "Render a LS_COLORS variable suitable for GNU ls"
        outlist = []
        havecodes = []
        # figure out if we are clearing builtin styles
        try:
            clear_builtin = self.scopedef["clear_builtin"]
            # TODO change "ls_colors" to use the generated name from GeneratorBase
            self.assert_bool(
                self.prog, clear_builtin, "ls_colors", self.scope, "clear_builtin"
            )
        except KeyError:
            clear_builtin = False

        # iterate over the styles given in our configuration
        for name, style in self.scope_styles.items():
            if style:
                mapcode, render = self.ls_colors_from_style(
                    name, style, self.LS_COLORS_MAP, self.scope
                )
                havecodes.append(mapcode)
                outlist.append(render)

        if clear_builtin:
            style_parser = StyleParser(None, None)
            style = style_parser.parse_text("default")
            # go through all the color codes, and render them with the
            # 'default' style and add them to the output
            for name, code in self.LS_COLORS_BASE_MAP.items():
                if not code in havecodes:
                    _, render = self.ls_colors_from_style(
                        name, style, self.LS_COLORS_MAP, self.scope
                    )
                    outlist.append(render)

        # process the filesets

        # figure out which environment variable to put it in
        try:
            varname = self.scopedef["environment_variable"]
            interp = Interpolator(self.styles, self.variables)
            varname = interp.interpolate(varname)
        except KeyError:
            varname = "LS_COLORS"

        # even if outlist is empty, we have to set the variable, because
        # when we are switching a theme, there may be contents in the
        # environment variable already, and we need to tromp over them
        # we chose to set the variable to empty instead of unsetting it
        return f'''export {varname}="{':'.join(outlist)}"'''


class ExaColors(GeneratorBase, LsColorsFromStyle):
    "generator for environment variables for exa"
    #
    # exa color generator
    #
    EXA_COLORS_BASE_MAP = {
        # map both a friendly name and the "real" name
        "text": "no",
        "file": "fi",
        "directory": "di",
        "symlink": "ln",
        "multi_hard_link": "mh",
        "pipe": "pi",
        "socket": "so",
        "door": "do",
        "block_device": "bd",
        "character_device": "cd",
        "broken_symlink": "or",
        "missing_symlink_target": "mi",
        "setuid": "su",
        "setgid": "sg",
        "sticky": "st",
        "other_writable": "ow",
        "sticky_other_writable": "tw",
        "executable_file": "ex",
        "file_with_capability": "ca",
        "perms_user_read": "ur",
        "perms_user_write": "uw",
        "perms_user_execute_files": "ux",
        "perms_user_execute_directories": "ue",
        "perms_group_read": "gr",
        "perms_group_write": "gw",
        "perms_group_execute": "gx",
        "perms_other_read": "tr",
        "perms_other_write": "tw",
        "perms_other_execute": "tx",
        "perms_suid_files": "su",
        "perms_sticky_directories": "sf",
        "perms_extended_attribute": "xa",
        "size_number": "sn",
        "size_unit": "sb",
        "df": "df",
        "ds": "ds",
        "uu": "uu",
        "un": "un",
        "gu": "gu",
        "gn": "gn",
        "lc": "lc",
        "lm": "lm",
        "ga": "ga",
        "gm": "gm",
        "gd": "gd",
        "gv": "gv",
        "gt": "gt",
        "punctuation": "xx",
        "date_time": "da",
        "in": "in",
        "bl": "bl",
        "column_headers": "hd",
        "lp": "lp",
        "cc": "cc",
        "b0": "b0",
    }
    # this map allows you to either use the 'native' exa code, or the
    # 'friendly' name defined by shell-themer
    EXA_COLORS_MAP = {}
    for friendly, actual in EXA_COLORS_BASE_MAP.items():
        EXA_COLORS_MAP[friendly] = actual
        EXA_COLORS_MAP[actual] = actual

    def generate(self):
        "Render a EXA_COLORS variable suitable for exa"
        outlist = []
        # figure out if we are clearing builtin styles
        try:
            clear_builtin = self.scopedef["clear_builtin"]
            self.assert_bool(
                self.prog, clear_builtin, "exa_colors", self.scope, "clear_builtin"
            )
        except KeyError:
            clear_builtin = False

        if clear_builtin:
            # this tells exa to not use any built-in/hardcoded colors
            outlist.append("reset")

        # iterate over the styles given in our configuration
        for name, style in self.scope_styles.items():
            if style:
                _, render = self.ls_colors_from_style(
                    name, style, self.EXA_COLORS_MAP, self.scope
                )
                outlist.append(render)

        # process the filesets

        # figure out which environment variable to put it in
        try:
            varname = self.scopedef["environment_variable"]
            interp = Interpolator(self.styles, self.variables)
            varname = interp.interpolate(varname)
        except KeyError:
            varname = "EXA_COLORS"

        # even if outlist is empty, we have to set the variable, because
        # when we are switching a theme, there may be contents in the
        # environment variable already, and we need to tromp over them
        # we chose to set the variable to empty instead of unsetting it
        print(f'''export {varname}="{':'.join(outlist)}"''')


class Iterm(GeneratorBase):
    "generator to set iterm foreground and background colors"

    def generate(self):
        """send the special escape sequences to make the iterm2
        terminal emulator for macos change its foreground and backgroud
        color

        echo "\033]1337;SetColors=bg=331111\007"
        """
        out = []
        rendered = self._iterm_render_style("foreground", "fg")
        if rendered:
            out.append(rendered)
        rendered = self._iterm_render_style("background", "bg")
        if rendered:
            out.append(rendered)
        return "\n".join(out)

    def _iterm_render_style(self, style_name, iterm_key):
        """print an iterm escape sequence to change the color palette"""
        try:
            style = self.scope_styles[style_name]
        except KeyError:
            return None
        if style:
            clr = style.color.get_truecolor()
            # gotta use raw strings here so the \033 and \007 don't get
            # interpreted by python
            out = r'builtin echo -e "\e]1337;'
            out += f"SetColors={iterm_key}={clr.hex.replace('#','')}"
            out += r'\a"'
            return out


class Shell(GeneratorBase):
    "generator for shell commands"

    def generate(self):
        out = []
        interp = Interpolator(self.styles, self.variables)
        try:
            cmds = self.scopedef["command"]
            for _, cmd in cmds.items():
                out.append(interp.interpolate(cmd))
        except KeyError:
            pass
        return "\n".join(out)