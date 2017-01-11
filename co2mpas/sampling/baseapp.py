#!/usr/bin/env python
#
# Copyright 2014-2016 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
A *traitlets*[#]_ framework for building hierarchical :class:`Cmd` line tools delegating to backend- :class:`Spec`.

To run a base command, use this code::

    app = MainCmd.instance(**app_init_kwds)
    app.initialize(argv or None) ## Uses `sys.argv` if `argv` is `None`.
    return app.start()

To run nested commands, use :func:`baseapp.chain_cmds()` like that::

    app = chain_cmds(MainCmd, Project, Project.List)
    return app.start()

## Configuration and Initialization guidelines for *Spec* and *Cmd* classes

0. The configuration of :class:`HasTraits` instance gets stored in its ``config`` attribute.
1. A :class:`HasTraits` instance receives its configuration from 3 sources, in this order:

  a. code specifying class-attributes or running on constructors;
  b. configuration files (*json* or ``.py`` files);
  c. command-line arguments.

2. Constructors must allow for properties to be overwritten on construction; any class-defaults
   must function as defaults for any constructor ``**kwds``.

3. Some utility code depends on trait-defaults (i.e. construction of help-messages), so for certain properties
   (e.g. description), it is preferable to set them as traits-with-defaults on class-attributes.

.. [#] http://traitlets.readthedocs.io/
"""
from collections import OrderedDict
import copy
import io
import logging
import os
from typing import Sequence, Text, Any, Tuple, List  # @UnusedImport

from boltons.setutils import IndexedSet as iset
from ipython_genutils.text import indent, wrap_paragraphs, dedent
from toolz import dicttoolz as dtz, itertoolz as itz

import itertools as itt
import os.path as osp
import pandalone.utils as pndlu
import traitlets as trt
import traitlets.config as trtc

from . import CmdException
from .. import (__version__, __updated__, __uri__, __copyright__, __license__)  # @UnusedImport
from ..__main__ import init_logging


## INFO: Modify the following variables on a different application.
APPNAME = 'co2dice'
CONFIG_VAR_NAME = '%s_CONFIG_PATH' % APPNAME.upper()
PERSIST_VAR_NAME = '%s_PERSIST_PATH' % APPNAME.upper()

try:
    _mydir = osp.dirname(__file__)
except:
    _mydir = '.'


def default_config_fname():
    """The config-file's basename (no path or extension) to search when not explicitly specified."""
    return '%s_config' % APPNAME


def default_config_dir():
    """The folder of to user's config-file."""
    return pndlu.convpath('~/.%s' % APPNAME)


def default_config_fpaths():
    """The full path of to user's config-file, without extension."""
    return [osp.join(default_config_dir(), default_config_fname()),
            osp.join(pndlu.convpath(_mydir), default_config_fname())]


def default_persist_fpath():
    """The full path of to user's persistent config-file, without extension."""
    return osp.join(default_config_dir(), '%s_runtime' % APPNAME)


class PeristentMixin:
    """
    A *cmd* and *spec* mixin to support storing of *persistent* traits into external file.

    *Persistent traits (ptrais)* are those tagged with `config` + `persist` boolean metadata.

    This is the lifecycle of *persistent* traits (*ptraits*):

    1. On app-init, invoke :meth:`load_pconfig()` to read runtime-params from disk
        and populate the global :attr:`_pconfig` (and attr:`_pconfig_orig`).

    2. Merge pconfig with any regular config-values (preferably overriding them).

    3. On each *cmd* or *spec* construction:
       B. Ensure :meth:`trtc.Configurable.update_config()` is invoked and then
       C. invoke :meth:`observe_ptraits()` to mirror any ptrait-changes
          on global :attr:`_pconfig`.

    4. On observed changes, indeed the global :attr:`_pconfig` gets updated.

    5. On app-exit, remember to invoke :meth:`store_pconfig()`
       to store any changes on disk.

    """

    #: The "global" CLASS-property that dynamically receives changes from
    #: *cmd* and *spec* traits with *peristent* traits.
    #: NOTE: not to be modified by mixed-in classes.
    _pconfig = trtc.Config()

    #: A "global" CLASS-property holding persistent-trait values as loaded,
    #: to be checked for inequality and decide if changes need storing.
    _pconfig_orig = trtc.Config()

    @classmethod
    def load_pconfig(cls, fpath: Text):
        """
        Load persistent config into global :attr:`_pconfig` & :attr:`_pconfig_orig`.

        :param cls:
            This mixin where updated ptrait-values are to be stored *globally*.
        :return:
            A tuple ``(fpath, Config())`` with the read persistent config parameters.
            Config might be `None` if file not found.
        :raise:
            Any exception while reading json and converting it
            into :class:`trtc.Config`, unless file does not exist.

        .. Note::
            It does not apply the loaded configs - you have to
            invoke :meth:`trtc.Configurable.update_config()`.

            Currently both methods invoked by the final *Cmd* on :meth:`Cmd.initialize()`.
            You have to invoke them for "stand-alone" *Specs* or pass
            an already merged :class:`trtc.Config` instance.
        """
        import json

        cfg = None
        fpath = pndlu.ensure_file_ext(fpath, '.json')
        try:
            with io.open(fpath, 'rt', encoding='utf-8') as finp:
                cfg = json.load(finp)
        except FileNotFoundError:
            pass
        else:
            cfg = trtc.Config(cfg)

            cls._pconfig = cfg
            cls._pconfig_orig = copy.deepcopy(cfg)

        return fpath, cfg

    @classmethod
    def store_pconfig(cls, fpath: Text):
        """
        Stores ptrait-values from the global :attr:`_pconfig`into `fpath` as JSON.

        :param cls:
            This mixin where updated ptrait-values are to be stored *globally*.
        """
        cfg = cls._pconfig
        if cfg and cfg != cls._pconfig_orig:
            import json

            fpath = pndlu.ensure_file_ext(fpath, '.json')
            with io.open(fpath, 'wt', encoding='utf-8') as fout:
                json.dump(cfg, fout, indent=2)

    def _ptrait_observed(self, change):
        """The observe-handler for *persistent* traits."""
        cls = type(self)
        cls_name = cls.__name__
        name = change['name']
        value = change['new']

        cls._pconfig[cls_name][name] = value

    def check_unconfig_ptraits(self):
        for name, tr in self.traits(persist=True).items():
            if tr.metadata.get('config') is not True:
                raise trt.TraitError("Persistent trait %r not tagged as 'config'!" % name)

    def observe_ptraits(self: trt.HasTraits):
        """
        Establishes observers for all *persistent* traits to update :attr:`persistent_config` class property.

        Invoke this after regular config-values have been installed.
        """
        self.check_unconfig_ptraits()
        ptraits = self.trait_names(config=True, persist=True)
        if ptraits:
            self.observe(self._ptrait_observed, ptraits)


###################
##     Specs     ##
###################

class Spec(trtc.LoggingConfigurable, PeristentMixin):
    """Common properties for all configurables."""
    ## See module documentation for developer's guidelines.

    @trt.default('log')
    def _log(self):
        return logging.getLogger(type(self).__name__)

    # The log level for the application
    log_level = trt.Enum((0, 10, 20, 30, 40, 50, 'DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                         default_value=logging.WARN,
                         help="Set the log level by value or name.").tag(config=True)

    @trt.observe('log_level')
    def _log_level_changed(self, change):
        """Adjust the log level when log_level is set."""
        new = change['new']
        if isinstance(new, str):
            new = getattr(logging, new)
            self.log_level = new
        self.log.setLevel(new)

    verbose = trt.Union(
        (trt.Integer(0), trt.Bool(False)),
        ## INFO: Add verbose flag explanations here.
        help="""
        Make various sub-commands increase their verbosity (not to be confused with --debug):
        Can be a boolean or 0, 1(==True), 2, ....

        - project list  : List project with the "long" format.
        - project infos : Whether to include also info about the repo-configuration (when 2).
        """).tag(config=True)

    force = trt.Bool(
        False,
        ## INFO: Add force flag explanations here.
        help="""
        Force various sub-commands to perform their duties without complaints.

        - project backup: Whether to overwrite existing archives or to create intermediate folders.
        """).tag(config=True)

    user_name = trt.Unicode(
        '<Name Surname>',
        help="""The Name & Surname of the default user invoking the app.  Must not be empty!"""
    ).tag(config=True)

    user_email = trt.Unicode(
        '<email-address>',
        help="""The email address of the default user invoking the app. Must not be empty!"""
    ).tag(config=True)

    @trt.validate('user_name', 'user_email')
    def _valid_user(self, proposal):
        value = proposal['value']
        if not value:
            raise trt.TraitError('%s.%s must not be empty!'
                                 % (proposal['owner'].name, proposal['trait'].name))
        return value

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.observe_ptraits()


###################
##    Commands   ##
###################


def cmd_class_short_help(app_class):
    desc = app_class.description
    return pndlu.first_line(isinstance(desc, str) and desc or app_class.__doc__)


def class2cmd_name(cls):
    name = cls.__name__
    if name.lower().endswith('cmd') and len(name) > 3:
        name = name[:-3]
    return pndlu.camel_to_cmd_name(name)


def build_sub_cmds(*subapp_classes):
    """Builds an ordered-dictionary of ``cmd-name --> (cmd-class, help-msg)``. """

    return OrderedDict((class2cmd_name(sa), (sa, cmd_class_short_help(sa)))
                       for sa in subapp_classes)


class Cmd(trtc.Application, PeristentMixin):
    """Common machinery for all (sub-)commands. """
    ## INFO: Do not use it directly; inherit it.
    # See module documentation for developer's guidelines.

    @trt.default('name')
    def _name(self):
        name = class2cmd_name(type(self))
        return name

    force = trt.Bool(
        False,
        help="""Force overwriting config-file, even if it already exists."""
    ).tag(config=True)

    config_paths = trt.List(
        trt.Unicode(),
        None, allow_none=True,
        help="""
        Absolute/relative path(s) to read "static" configurable parameters from.

        If false, and no `{confvar}` envvar is defined, defaults to:
            {default}
        Multiple values may be given, and each value may be a single or multiple paths
        separated by '{pathsep}'.  All paths collected are considered in descending order
        (1st one overrides the rest).
        For paths resolving to folders, the filename `{appname}_config.[json | py]` is appended;
        otherwise, any file-extensions are ignored, and '.py' and/or '.json' are loaded (in this order).


        Tip:
            Use `config init` sub-command to produce a skeleton of the config-file.

        Note:
            A value in configuration files are ignored!  Set this from command-line
            (or in code, before invoking :meth:`Cmd.initialize()`).
            Any command-line values take precedence over the `{confvar}` envvar.

        Examples:
            To read and apply, in descending order `~/my_conf`, `/tmp/conf.py`  `~/.co2dice.json`
            issue:
                <cmd> --config-paths=~/my_conf:/tmp/conf.py  --config-paths=~/.co2dice.json  ...



        """.format(appname=APPNAME, confvar=CONFIG_VAR_NAME,
                   default=default_config_fpaths(), pathsep=osp.pathsep)
    ).tag(config=True)

    persist_path = trt.Unicode(
        None, allow_none=True,
        help="""
        Absolute/relative path to read/write persistent parameters on runtime, if `{confvar}` envvar is not defined.

        If false, and no `{confvar}` envvar is defined, defaults to:
            {default}
        If path resolves to a folder, the filename `{appname}_runtime.json` is appended;
        otherwise, the file-extensions is assumed to be `.json`.
        Persistent-parameters override "static" ones.

        Tip:
            Use `config init` sub-command to produce a skeleton of the config-file.

        Note:
            A value in configuration files are ignored!  Set this from command-line
            (or in code, before invoking :meth:`Cmd.initialize()`).
            Any command-line values take precedence over the `{confvar}` envvar.
        """.format(appname=APPNAME, confvar=PERSIST_VAR_NAME,
                   default=default_persist_fpath())
    ).tag(config=True)

    @trt.default('log')
    def _log(self):
        ## Use a regular logger.
        return logging.getLogger(type(self).__name__)

    #: A list of loaded config-files in descending order
    #: (1st overrides rest), to answer inquires afterwards.
    loaded_config_files = []

    def _derive_config_fpaths(self, path: Text) -> List[Text]:
        """Return multiple *existent* fpaths for each config-file path (folder/file)."""
        new_paths = []

        def try_json_and_py(basepath):
            found = False
            for ext in ('.py', '.json'):
                f = pndlu.ensure_file_ext(basepath, ext)
                if osp.isfile(f):
                    new_paths.append(f)
                    found = True

            return found

        for p in path.split(os.pathsep):
            p = pndlu.convpath(p)
            if osp.isdir(p):
                try_json_and_py(osp.join(p, default_config_fname()))
            else:
                found = try_json_and_py(p)
                ## Do not strip ext if has matched WITH ext.
                if not found:
                    try_json_and_py(osp.splitext(p)[0])

        return new_paths

    def _collect_static_fpaths(self):
        env_paths = os.environ.get(CONFIG_VAR_NAME)
        env_paths = env_paths and [env_paths]
        config_paths = (self.config_paths or
                        env_paths or
                        default_config_fpaths())
        config_paths = list(iset(itt.chain(
            existing_fpaths
            for cf in config_paths
            for existing_fpaths in self._derive_config_fpaths(cf))))

        return config_paths

    def _read_config_from_json_or_py(self, cfpath: Text):
        """
        :param cfpath:
            The absolute config-file path with either ``.py`` or ``.json`` ext.
        """
        log = self.log
        loaders = {
            '.py': trtc.PyFileConfigLoader,
            '.json': trtc.JSONFileConfigLoader,
        }
        ext = osp.splitext(cfpath)[1]
        loader = loaders.get(str.lower(ext))
        assert loader, cfpath  # Must exist.

        config = None
        try:
            config = loader(cfpath, path=None, log=log).load_config()
        except trtc.ConfigFileNotFound:
            ## Config-file deleted between collecting its name and reading it.
            pass
        except Exception as ex:
            if self.raise_config_file_errors:
                raise
            log.error("Skipped loading config-file '%s' due to: %s",
                      cfpath, ex, exc_info=True)
        else:
            log.debug("Loaded config-file: %s", cfpath)

        return config

    def _read_config_from_static_files(self):
        """
        Sideffect: Updates also the :attr:`loaded_config_files` list.
        """
        config_paths = self._collect_static_fpaths()

        new_config = trtc.Config()
        ## Registry to detect collisions.
        loaded = {}  # type: Dict[Text, Config]

        for cfpath in config_paths[::-1]:
            config = self._read_config_from_json_or_py(cfpath)
            if config:
                self.loaded_config_files.append(cfpath)

                for filename, earlier_config in loaded.items():
                    collisions = earlier_config.collisions(config)
                    if collisions:
                        import json
                        self.log.warning(
                            "Collisions detected in %s and %s config files."
                            " %s has higher priority: %s",
                            filename, cfpath, cfpath,
                            json.dumps(collisions, indent=2)
                        )
                loaded[cfpath] = config

                new_config.merge(config)

        return new_config

    def _read_config_from_persist_file(self):
        """
        Sideffect: Updates also the :attr:`loaded_config_files` list.
        """
        persist_path = (self.persist_path or
                        os.environ.get(PERSIST_VAR_NAME) or
                        default_persist_fpath())
        persist_path = pndlu.convpath(persist_path)
        try:
            persist_path, config = self.load_pconfig(persist_path)
        except Exception as ex:
            if self.raise_config_file_errors:
                raise
            self.log.error("Skipped loading persist-file '%s' due to: %s",
                           persist_path, ex, exc_info=True)
        else:
            if not config:
                self.log.info("No persist-file found in: %s", persist_path)
            else:
                self.log.debug("Loaded persist-file: %s", persist_path)
                self.loaded_config_files.append(persist_path)

                return config

    def load_configurables_from_files(self) -> Tuple[trtc.Config, trtc.Config]:
        """
        Load :attr:`config_paths`, :attr:`persist_path` and maintain :attr:`loaded_config_files` list.

        :return:
            A 2 tuple ``(static_config, persist_config)``, where the 2nd might be `None`.

        Configuration files are read and merged in descending orders:

        1. Persistent parameters from ``.json`` files, either in:
           - :envvar:`<APPNAME>_PERSIST_PATH`, or if not set,
           - :attr:`persist_path` (see its default-value);

        2. Static parameters from ``.json`` and/or ``.py`` files, either in:
           - :envvar:`<APPNAME>_CONFIG_PATHS`, or if not set,
           - :attr:`config_paths` (see its default-value).

        Code adapted from :meth:`load_config_file` & :meth:`Application._load_config_files`.
        """
        self.loaded_config_files = []
        try:
            static_config = self._read_config_from_static_files()
            persist_config = self._read_config_from_persist_file()
        finally:
            ## To be consistent, even in errors.
            self.loaded_config_files = self.loaded_config_files[::-1]

        return static_config, persist_config

    def write_default_config(self, config_file=None, force=False):
        if not config_file:
            config_file = default_config_fpaths()[0]
        else:
            config_file = pndlu.convpath(config_file)
            if osp.isdir(config_file):
                config_file = osp.join(config_file, default_config_fname())
        config_file = pndlu.ensure_file_ext(config_file, '.py')

        is_overwrite = osp.isfile(config_file)
        if is_overwrite and not force:
            raise CmdException("Config-file %r already exists!\n  Specify `--force` to overwrite." %
                               config_file)

        op = 'Over-writting' if is_overwrite else 'Writting'
        self.log.info('%s config-file %r...', op, config_file)
        pndlu.ensure_dir_exists(os.path.dirname(config_file), 0o700)
        config_text = self.generate_config_file()
        with io.open(config_file, mode='wt') as fp:
            fp.write(config_text)

    def print_subcommands(self):
        """Print the subcommand part of the help."""
        ## Overridden, to print "default" sub-cmd.
        if not self.subcommands:
            return

        lines = ["Subcommands"]
        lines.append('=' * len(lines[0]))
        for p in wrap_paragraphs(self.subcommand_description.format(
                app=self.name)):
            lines.append(p)
        lines.append('')
        for subc, (cls, hlp) in self.subcommands.items():
            if self.default_subcmd == subc:
                subc = '%s[*]' % subc
            lines.append(subc)

            if hlp:
                lines.append(indent(dedent(hlp.strip())))
        if self.default_subcmd:
            lines.append('')
            lines.append("""Note: The asterisk '[*]' marks the "default" sub-command to run when none specified.""")
        lines.append('')
        print(os.linesep.join(lines))

    ## Needed because some sub-cmd name clash and
    #  *argparse* screams about conflicts.
    #  See https://github.com/ipython/traitlets/pull/360
    def _create_loader(self, argv, aliases, flags, classes):
        return trtc.KVArgParseConfigLoader(
            argv, aliases, flags, classes=classes,
            log=self.log, conflict_handler='resolve')

    default_subcmd = trt.Unicode(
        None, allow_none=True,
        help="The name of the sub-command to use if unspecified.")

    conf_classes = trt.List(
        trt.Type(trtc.Configurable), default_value=[],
        help="""
        Any *configurables* found in this prop up the cmd-chain are merged,
        along with any subcommands, into :attr:`classes`.
        """)

    cmd_aliases = trt.Dict(
        {},
        help="Any *flags* found in this prop up the cmd-chain are merged into :attr:`aliases`. """)

    cmd_flags = trt.Dict(
        {},
        help="Any *flags* found in this prop up the cmd-chain are merged into :attr:`flags`. """)

    def my_cmd_chain(self):
        """Return the chain of cmd-classes starting from my self or subapp."""
        cmd_chain = []
        pcl = self.subapp if self.subapp else self
        while pcl:
            cmd_chain.append(pcl)
            pcl = pcl.parent

        return cmd_chain

    @trt.observe('parent', 'conf_classes', 'cmd_aliases', 'cmd_flags', 'subapp', 'subcommands')
    def _inherit_parent_cmd(self, change):
        """ Inherit config-related stuff from up the cmd-chain. """
        if self.parent:
            ## Collect parents, ordered like that:
            #    subapp, self, parent1, ...
            #
            cmd_chain = self.my_cmd_chain()

            ## Collect separately and merge  SPECs separately,
            #  to prepend them before SPECs at the end.
            #
            conf_classes = list(itz.concat(cmd.conf_classes for cmd in cmd_chain))

            ## Merge aliases/flags reversed.
            #
            cmd_aliases = dtz.merge(cmd.cmd_aliases for cmd in cmd_chain[::-1])
            cmd_flags = dtz.merge(cmd.cmd_flags for cmd in cmd_chain[::-1])
        else:
            ## We are root.

            cmd_chain = [self]
            conf_classes = list(self.conf_classes)
            cmd_aliases = self.cmd_aliases
            cmd_flags = self.cmd_flags

        cmd_classes = [type(cmd) for cmd in cmd_chain]
        self.classes = list(iset(cmd_classes + conf_classes))
        self.aliases.update(cmd_aliases)
        self.flags.update(cmd_flags)

    @trt.observe('log_level')
    def _init_logging(self, change):
        log_level = change['new']
        if isinstance(log_level, str):
            log_level = getattr(logging, log_level)

        init_logging(level=log_level)

    def __init__(self, **kwds):
        cls = type(self)
        dkwds = {
            ## Traits defaults are always applied...??
            #
            'name': class2cmd_name(cls),

            ## Set some nice defaults for root-CMDs.
            #
            'cmd_aliases': {
                'config-paths': 'Cmd.config_paths',
            },
            'cmd_flags': {
                ('d', 'debug'): (
                    {
                        'Application': {'log_level': 0},
                        'Spec': {'log_level': 0},
                        'Cmd': {
                            'raise_config_file_errors': True,
                            'print_config': True,
                        },
                    },
                    "Log more logging, fail on configuration errors, "
                    "and print configuration on each cmd startup."
                ),
                ('v', 'verbose'): (
                    {
                        'Spec': {'verbose': True},
                    },
                    pndlu.first_line(Spec.verbose.help)
                ),
                ('f', 'force'): (
                    {
                        'Spec': {'force': True},
                        'Cmd': {'force': True},
                    },
                    pndlu.first_line(Spec.force.help)
                )
            },
        }
        if cls.__doc__ and not isinstance(cls.description, str):
            dkwds['description'] = cls.__doc__
        dkwds.update(kwds)
        super().__init__(**dkwds)

    def _check_non_encrypted_in_config_files(self, static_config, persist_config,
                                             all_configurables):
        """
        For all configurable-classes, scan *static-configs* for non-encrypted values.

        Must be invoked before reading peristent config file.
        """
        from . import crypto

        for cls in all_configurables:
            clsname = cls.__name__
            for ctraitname, ctrait in cls.class_traits(config=True).items():
                if not isinstance(ctrait, crypto.Cipher):
                    continue
                key = '%s.%s' % (clsname, ctraitname)
                if key not in static_config:
                    continue
                val = static_config[clsname][ctraitname]
                if crypto.is_pgp_encrypted(val):
                    continue
                if self.raise_config_file_errors:
                    raise trt.TraitError(
                        "Found non-encrypted param '%s.%s' in static-configs!" %
                        (clsname, ctraitname))
                self.log.error(
                    "Found non-encrypted param '%s.%s' in static-configs!",
                    clsname, ctraitname)

    def _is_dispatching(self):
        """True if dispatching to another command."""
        return bool(self.subapp)

    @trtc.catch_config_error
    def initialize(self, argv=None):
        """
        Invoked after __init__() by Cmd.launch_instance() to read & validate configs.

        It parses cl-args before file-configs, to detect sub-commands
        and update any :attr:`config_paths`, then it reads all file-configs, and
        then re-apply cmd-line configs as overrides (trick copied from `jupyter-core`).

        It also validates config-values for :class:`crypto.Cipher` traits.
        """
        self.parse_command_line(argv)
        if self._is_dispatching():
            ## Only the final child reads file-configs.
            #  Also avoid contaminations with user if generating-config.
            return

        ## NOTE: Dependency to specific app BELOW!
        #  Cannot use :attr:`conf_classes` because not all commands need all of them,
        #  besides, *argparse* complains with same-named subcmds.
        #
        from . import dice
        all_configurables = dice.all_configurables()

        static_config, persist_config = self.load_configurables_from_files()
        self._check_non_encrypted_in_config_files(static_config, persist_config,
                                                  all_configurables)

        if persist_config:
            static_config.merge(persist_config)
        static_config.merge(self.cli_config)

        self.update_config(static_config)
        self.observe_ptraits()

    print_config = trt.Bool(
        False,
        help="""Enable it to print the configurations before launching any command."""
    ).tag(config=True)

    def start(self):
        """Dispatches into sub-cmds (if any), and then delegates to :meth:`run().

        If overriden, better invoke :func:`super()`, but even better
        to override :meth:``run()`.
        """
        if self.print_config:
            self.log.info('Running cmd %r with config: \n  %s', self.name, self.config)

        if self.subapp is not None:
            pass
        elif self.default_subcmd:
            self.initialize_subcommand(self.default_subcmd, self.argv)
        else:
            return self.run(*self.extra_args)

        return self.subapp.start()

    def run(self, *args):
        """Leaf sub-commands must inherit this instead of :meth:`start()` without invoking :func:`super()`.

        By default, screams about using sub-cmds, or about doing nothing!

        :param args: Invoked by :meth:`start()` with :attr:`extra_args`.
        """
        if self.subcommands:
            cmd_line = ' '.join(cl.name
                                for cl in reversed(self.my_cmd_chain()))
            raise CmdException("Specify one of the sub-commands: "
                               "\n    %s\nor type: \n    %s -h"
                               % (', '.join(self.subcommands.keys()), cmd_line))
        assert False, "Override run() method in cmd subclasses."


## Disable logging-format configs, because their observer
#    works on on loger's handlers, which might be null.
Cmd.log_format.tag(config=False)
Cmd.log_datefmt.tag(config=False)

## So that dynamic-default rules apply.
#
Cmd.description.default_value = None
Cmd.name.default_value = None

## Expose `raise_config_file_errors` instead of relying only on
#  :envvar:`TRAITLETS_APPLICATION_RAISE_CONFIG_FILE_ERROR`.
trtc.Application.raise_config_file_errors.tag(config=True)
Cmd.raise_config_file_errors.help = 'Whether failing to load config files should prevent startup.'


def chain_cmds(app_classes: Sequence[type(trtc.Application)],
               argv: Sequence[Text]=None,
               **root_kwds):
    """
    Instantiate(optionally) a list of ``[cmd, subcmd, ...]`` and link each one as child of its predecessor.

    TODO: FIX `chain_cmds()`, argv not working!

    :param argv:
        cmdline args for the the 1st cmd.
        Make sure they do not specify some cub-cmds.
        Do NOT replace with `sys.argv` if none.
        Note: you have to "know" the correct nesting-order of the commands ;-)
    :return:
        the 1st cmd, to invoke :meth:`start()` on it
    """
    if not app_classes:
        raise ValueError("No cmds to chained passed in!")

    app_classes = list(app_classes)
    root = app = None
    for app_cl in app_classes:
        if not isinstance(app_cl, type(trtc.Application)):
                    raise ValueError("Expected an Application-class instance, got %r!" % app_cl)
        if not root:
            ## The 1st cmd is always orphan, and gets returned.
            root = app = app_cl(**root_kwds)
        else:
            app.subapp = app = app_cl(parent=app)
        app.initialize(argv or [])

    app_classes[0]._instance = app
    return root
