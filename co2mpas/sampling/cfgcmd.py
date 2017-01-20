#!/usr/bin/env pythonw
#
# Copyright 2014-2016 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""Dice traitlets sub-commands for manipulating configurations"""

from . import baseapp, CmdException
from typing import Sequence, Text, List, Tuple    # @UnusedImport

import os.path as osp
import pandalone.utils as pndlu
import traitlets as trt
import traitlets.config as trtc


class ConfigCmd(baseapp.Cmd):
    """
    Commands to manage configuration-options loaded from filesystem.

    Read also the help message for `--config-paths` generic option.
    """

    class InitCmd(baseapp.Cmd):
        """
        Store config defaults into specified path(s); '{confpath}' assumed if none specified.

        - If a path resolves to a folder, the filename '{appname}_config.py' is appended.
        - It OVERWRITES any pre-existing configuration file(s)!

        SYNTAX
            co2dice config init [<config-path-1>] ...
        """

        ## Class-docstring CANNOT contain string-interpolations!
        description = trt.Unicode(__doc__.format(
            confpath=baseapp.default_config_fpaths()[0],
            appname=baseapp.APPNAME))

        examples = trt.Unicode("""
            Generate a config-file at your home folder:
                co2dice config init ~/my_conf

            To re-use this custom config-file alone, use:
                co2dice --config-paths=~/my_conf  ...
            """)

        def run(self, *args):
            ## Prefer to modify `classes` after `initialize()`, or else,
            #  the cmd options would be irrelevant and fatty :-)
            self.classes = self.all_app_configurables()
            args = args or [None]
            for fpath in args:
                self.write_default_config(fpath, self.force)

    class PathsCmd(baseapp.Cmd):
        """List search-paths and actual config-files loaded in descending order."""
        def run(self, *args):
            if len(args) > 0:
                raise CmdException('Cmd %r takes no arguments, received %d: %r!'
                                   % (self.name, len(args), args))

            sep = osp.sep

            def format_tuple(path, files: List[Text]):
                endpath = sep if path[-1] != sep else ''
                return '%s%s: %s' % (path, endpath, files or '')

            return (format_tuple(p, f) for p, f in self.loaded_config_files)

    class ShowCmd(baseapp.Cmd):
        """
        Print configurations (defaults | ondisk | TODO:merged) before any validations.

        Alternatively, you may use the `--Cmd.print_config=True` global option on each command.

        Warning:
            Running this command before encrypting sensitive persistent parameters,
            will print them plaintext!
        """

        onfiles = trt.Bool(
            False,
            help="""Show only configuration parameters stored on disk files."""
        ).tag(config=True)

        def __init__(self, **kwds):
                kwds.setdefault('cmd_flags', {
                    'onfiles': ({
                        'ShowCmd': {'onfiles': True}},
                        pndlu.first_line(ConfigCmd.ShowCmd.onfiles.help)
                    )
                })
                super().__init__(**kwds)

        def initialize(self, argv=None):
            self.parse_command_line(argv)
            static_config, persist_config = self.load_configurables_from_files()
            if persist_config:
                static_config.merge(persist_config)
            static_config.merge(self.cli_config)
            ## Stop from applying file-configs - or any validations will scream.

            self._loaded_config = static_config

        def _yield_file_configs(self, config):
            for k, v in config.items():
                yield k
                try:
                    for kk, vv in v.items():
                        yield '  +--%s = %s' % (kk, vv)
                except:
                    yield '  +--%s' % v

        def _yield_configs_and_defaults(self, config):
            ## Prefer to modify `classes` after `initialize()`, or else,
            #  the cmd options would be irrelevant and fatty :-)
            self.classes = self.all_app_configurables()
            for cls in self._classes_with_config_traits():
                clsname = cls.__name__
                cls_printed = False

                cls_traits = (cls.class_traits(config=True)
                              if self.verbose else
                              cls.class_own_traits(config=True))
                for name, trait in sorted(cls_traits.items()):
                    key = '%s.%s' % (clsname, name)
                    if key in config:
                        val = config[clsname][name]
                    else:
                        val = trait.default_value_repr()

                    if not cls_printed:
                        yield clsname
                        cls_printed = True
                    yield '  +--%s = %s' % (name, val)

        def run(self, *args):
            if len(args) > 0:
                raise CmdException('Cmd %r takes no arguments, received %d: %r!'
                                   % (self.name, len(args), args))

            config = self._loaded_config
            yield from (self._yield_file_configs(config)
                        if self.onfiles else
                        self._yield_configs_and_defaults(config))

    def __init__(self, **kwds):
            dkwds = {'subcommands': baseapp.build_sub_cmds(*config_subcmds)}
            dkwds.update(kwds)
            super().__init__(**dkwds)


config_subcmds = (
    ConfigCmd.InitCmd,
    ConfigCmd.PathsCmd,
    ConfigCmd.ShowCmd,
)