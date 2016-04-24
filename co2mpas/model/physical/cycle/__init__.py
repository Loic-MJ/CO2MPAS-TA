#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2014 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

"""
It provides the model to calculate theoretical times, velocities, and gears.

Sub-Modules:

.. currentmodule:: co2mpas.model.physical.cycle

.. autosummary::
    :nosignatures:
    :toctree: cycle/

    NEDC
    WLTP

"""

from co2mpas.dispatcher import Dispatcher
import co2mpas.dispatcher.utils as dsp_utl


def is_nedc(kwargs):
    for k, v in kwargs.items():
        if ':cycle_type' in k or 'cycle_type' == k:
            return v == 'NEDC'
    return False


def is_wltp(kwargs):
    for k, v in kwargs.items():
        if ':cycle_type' in k or 'cycle_type' == k:
            return v == 'WLTP'
    return False


def cycle():
    """
    Defines the cycle model.

    .. dispatcher:: dsp

        >>> dsp = cycle()

    :return:
        The cycle model.
    :rtype: Dispatcher
    """

    dsp = Dispatcher(
        name='Cycle model',
        description='Returns the theoretical times, velocities, and gears.'
    )

    from .NEDC import nedc_cycle
    dsp.add_dispatcher(
        include_defaults=True,
        dsp=nedc_cycle(),
        inputs={
            'cycle_type': dsp_utl.SINK,
            'k1': 'k1',
            'k2': 'k2',
            'k5': 'k5',
            'max_gear': 'max_gear',
            'time_sample_frequency': 'time_sample_frequency',
            'gear_box_type': 'gear_box_type',
            'times': 'times'
        },
        outputs={
            'times': 'times',
            'velocities': 'velocities',
            'gears': 'gears'
        },
        input_domain=is_nedc
    )

    from .WLTP import wltp_cycle
    dsp.add_dispatcher(
        include_defaults=True,
        dsp=wltp_cycle(),
        inputs={
            'cycle_type': dsp_utl.SINK,
            'time_sample_frequency': 'time_sample_frequency',
            'gear_box_type': 'gear_box_type',
            'times': 'times',
            'velocities': 'velocities',
            'accelerations': 'accelerations',
            'motive_powers': 'motive_powers',
            'gear_box_ratios': 'gear_box_ratios',
            'idle_engine_speed': 'idle_engine_speed',
            'inertial_factor': 'inertial_factor',
            'downscale_phases': 'downscale_phases',
            'climbing_force':'climbing_force',
            'full_load_curve': 'full_load_curve',
            'downscale_factor': 'downscale_factor',
            'downscale_factor_threshold': 'downscale_factor_threshold',
            'vehicle_mass': 'vehicle_mass',
            'driver_mass': 'driver_mass',
            'road_loads': 'road_loads',
            'engine_max_power': 'engine_max_power',
            'engine_max_speed_at_max_power': 'engine_max_speed_at_max_power',
            'max_velocity': 'max_velocity',
            'wltp_class': 'wltp_class'
        },
        outputs={
            'times': 'times',
            'velocities': 'velocities',
            'gears': 'gears'
        },
        input_domain=is_wltp
    )

    return dsp