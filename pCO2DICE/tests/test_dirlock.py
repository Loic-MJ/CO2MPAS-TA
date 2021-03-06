#! python
# -*- coding: UTF-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
import logging
import tempfile
import time
import unittest

from co2dice.utils.logconfutils import init_logging
from co2dice import dirlock
import ddt

import multiprocessing as mp
import os.path as osp
import subprocess as sbp
import textwrap as tw
import threading as th


init_logging(level=logging.DEBUG)

log = logging.getLogger(__name__)

mydir = osp.dirname(__file__)

lock_duration = 2.


def lock_n_sleep(label, tdir, *,
                 lock_duration=lock_duration, **lock_kw):
    log.info('Started %s', label)
    with dirlock.locked_on_dir(tdir, 0.2, **lock_kw):
        time.sleep(lock_duration)


def cmd_task_factory(label, tdir, **lock_kw):
    prog_path = osp.join(osp.dirname(tdir), 'p.py')
    with open(prog_path, 'wt') as f:
        f.write(tw.dedent("""
            import time
            from co2dice import dirlock;

            lock_kw = %r
            with dirlock.locked_on_dir(%r, 0.2, **lock_kw):
                time.sleep(%s)
        """ % (lock_kw, tdir, lock_duration)))

    def task():
        log.info('Started %s.', label)
        p = sbp.run(['python', prog_path],
                    universal_newlines=True,
                    stdout=sbp.PIPE, stderr=sbp.PIPE)
        assert not p.returncode and not p.stdout and not p.stderr, (
            p.returncode, p.stdout, p.stderr)

    return task


def worker_factory(worker_type: "thread | proc", label, tdir, **lock_kw):
    label = '%s.%s' % (worker_type, label)
    if worker_type == 'cmd':
        worker = th.Thread(target=cmd_task_factory(label, tdir, **lock_kw),
                           daemon=True)
    elif worker_type == 'thread':
        worker = th.Thread(target=lock_n_sleep, args=(label, tdir), kwargs=lock_kw,
                           daemon=True)
    elif worker_type == 'proc':
        worker = mp.Process(target=lock_n_sleep, args=(label, tdir), kwargs=lock_kw,
                            daemon=True)
    else:
        assert False, worker_type

    return worker


@ddt.ddt
class TDirlock(unittest.TestCase):

    @ddt.data(
        ('thread', 1),
        ('thread', 2),
        ('thread', 5),

        ('proc', 1),
        ('proc', 2),
        ('proc', 5),

        ('cmd', 1),
        ('cmd', 2),
        ('cmd', 5),
    )
    def test_workers(self, case):
        worker_type, nprocs = case
        abort_sec = 1.5 * nprocs * lock_duration
        start_t = time.clock()
        with tempfile.TemporaryDirectory() as tdir:
            tdir = osp.join(tdir, 'L')
            workers = [worker_factory(worker_type, i, tdir, abort_sec=abort_sec)
                       for i in range(nprocs)]
            for w in workers:
                w.start()
            for w in workers:
                w.join()
        elapsed = time.clock() - start_t

        exp_total_duration = nprocs * (1.2 * lock_duration) + lock_duration  # setup-time
        assert elapsed < exp_total_duration

#     @ddt.data('thread', 'proc')
#     def test_timeout(self, worker_type):
#         with tempfile.TemporaryDirectory() as tdir:
#             tdir = osp.join(tdir, 'L1')
#             workers = [worker_factory(worker_type, i, tdir,
#                                       lock_duration=2, abort_sec=3)
#                        for i in range(2)]
#             for w in workers:
#                 w.start()
#             for w in workers:
#                 w.join()
