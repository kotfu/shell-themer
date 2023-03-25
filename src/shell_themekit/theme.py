#!/usr/bin/env python
#
#
# options:
#   --format -- what format do you want the color in {hex, rgb, escape codes)
#   --theme -- can be specified here, if not, uses $THEME_DIR environment
#              variable
#
#   --default -- if the scope isn't present in the theme
#     use this instead, or do we build this into the theme?
#

# approach
# - compile the theme file into a bunch of rich.style objects, with
#   a method get_style() that gets the style from the theme or parses
#   it from the input
# - make a custom python function for each type of rendered output
#    - ie fzf render type would create an options string for fzf
#      including --color, --border, --pointer, --prompt, --marker etc
#    - ls render type would create a LS_COLORS string
#    - envhex creates environment variables with hex codes in them for
#      each variable in the scope
# - create a scope that set an env variable, like to set BAT_THEME
#    - the theme file just contains the name of the bat theme to use when this
#      shell theme is selected
# - create a scope that knows how to set an emacs theme by name
#    - the theme file contains the name of the emacs theme


import tomllib
import os
import pathlib
import sys

import rich.color
import rich.console
import rich.style


class Theme:
    """parse and translate a theme file for various command line programs"""

    EXIT_SUCCESS = 0
    EXIT_ERROR = 1

    def __init__(self, prog, console=None):
        """Construct a new Theme() object"""

        self.prog = prog
        if console:
            self.console = console
        else:
            self.console = rich.console.Console()

        self.definition = {}
        self.styles = {}

        self.loads()

    def load(self, theme_file=None):
        """Load a theme from a directory

        :raises:

        """
        if theme_file:
            fname = theme_file
        else:
            try:
                fname = pathlib.Path(os.environ["THEME_DIR"]) / "theme.toml"
            except KeyError:
                self.console.print(f"{self.prog}: $THEME_DIR not set")
                sys.exit(self.EXIT_ERROR)

        with open(fname, "rb") as file:
            self.definition = tomllib.load(file)

        self._parse_styles()

    def loads(self, tomlstring=None):
        """Load a theme from a given string"""
        if tomlstring:
            toparse = tomlstring
        else:
            toparse = ""
        self.definition = tomllib.loads(toparse)
        self._parse_styles()

    def _parse_styles(self):
        """parse the styles section of the theme and put it into self.styles dict"""
        self.styles = {}
        try:
            for key, value in self.definition["styles"].items():
                self.styles[key] = rich.style.Style.parse(value)
        except KeyError:
            pass

    def domain_styles(self, domain):
        "Get all the styles for a given domain, or an empty dict of there are none"
        styles = {}
        try:
            raw_styles = self.definition["domain"][domain]["style"]
            # parse out the Style objects for each definition
            for key, value in raw_styles.items():
                styles[key] = self.get_style(value)
        except KeyError:
            pass
        return styles

    def domain_attributes(self, domain):
        "Get the non-style attributes of a domain"
        attributes = {}
        try:
            attributes = self.definition["domain"][domain].copy()
            # strip out the style subtable
            del attributes["style"]
        except KeyError:
            pass
        return attributes

    def get_style(self, styledef):
        """convert a string into rich.style.Style object"""
        try:
            style = self.styles[styledef]
        except KeyError:
            style = None
        if not style:
            style = rich.style.Style.parse(styledef)
        return style

    def render(self, domain=None):
        """render the output for a given domain, or all domains if none supplied

        output is suitable for bash eval $()
        """
        attribs = self.domain_attributes(domain)
        # we must have a type attribute so we know how to render it
        try:
            typ = attribs["type"]
            if typ == "fzf":
                return self._fzf_render(attribs, self.domain_styles(domain))
            return None
        except KeyError:
            return None

    def _fzf_render(self, attribs, styles):
        """render attribs into a shell statement to set an environment variable"""
        optstr = ""

        # process all the command line options
        try:
            opts = attribs["opt"]
        except KeyError:
            opts = {}

        for key, value in opts.items():
            if isinstance(value, str):
                optstr += f" --{key}={value}"
            elif isinstance(value, bool) and value:
                optstr += f" --{key}"

        # process all the styles
        colors = []
        # then add them back
        for name, style in styles.items():
            colors.append(self._fzf_from_style(name, style))
        # turn off all the colors, and add our color strings
        colorstr = f" --color=bw:{','.join(colors)}"

        # figure out which environment variable to put it in
        try:
            varname = attribs["varname"]
        except KeyError:
            varname = "FZF_DEFAULT_OPTS"
        return f"export {varname}='{optstr}{colorstr}'"

    def _fzf_from_style(self, name, style):
        """turn a rich.style into a valid fzf color"""
        fzf = []
        if name == "text":
            # turn this into fg and bg color names
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"fg:{fzfc}{fzfa}")
            if style.bgcolor:
                fzfc = self._fzf_color_from_rich_color(style.bgcolor)
                fzf.append(f"bg:{fzfc}")
        elif name == "current_line":
            # turn this into fg+ and bg+ color names
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"fg+:{fzfc}{fzfa}")
            if style.bgcolor:
                fzfc = self._fzf_color_from_rich_color(style.bgcolor)
                fzf.append(f"bg+:{fzfc}")
        elif name == "preview":
            # turn this into fg+ and bg+ color names
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"preview-fg:{fzfc}{fzfa}")
            if style.bgcolor:
                fzfc = self._fzf_color_from_rich_color(style.bgcolor)
                fzf.append(f"preview-bg:{fzfc}")
        else:
            # no special processing for foreground and background
            if style.color:
                fzfc = self._fzf_color_from_rich_color(style.color)
                fzfa = self._fzf_attribs_from_style(style)
                fzf.append(f"{name}:{fzfc}{fzfa}")

        return ",".join(fzf)

    def _fzf_color_from_rich_color(self, color):
        """turn a rich.color into it's fzf equivilent"""
        fzf = ""
        if not color:
            return

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
        attribs = ""
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