#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Created By  : Jason Schultz
# Created Date: 2024-08-05
# version ='1.0'
# ---------------------------------------------------------------------------
"""a_short_project_description"""
# ---------------------------------------------------------------------------
import sys
from mppt.squidstat import SquidstatMppt, BASIC_P_AND_O, METASTABLE_P_AND_O
from mppt.kiethley import KeithleyMppt, GPIB
from mppt.mppt import CONST_V_STATE, MPPT_STATE
from PySide6.QtWidgets import QApplication


def keithley_main():
    app = QApplication()
    manager = KeithleyMppt(
        GPIB = GPIB,
        year = "2025",
        date = "07-15",
        fabricator = "Elnaz",
        cell_name = "08u",
        cell_area = 0.16,
        solar_irradiance = 100
    )
    manager.set_JV_parameters_with_time_step(
        high_voltage = 1.2,
        low_voltage = -0.2,
        step_voltage_mV = 10,
        step_time_ms = 300,
        averages = 2
    )
    manager.set_mppt_parameters(
        mpp_duration = 30
    )
    manager.perform_JV_scans()
    # manager.perturb_and_observe(starting_voltage = 0.5)
    # manager.perturb_and_observe_metastable_psc(starting_voltage = 0.5, tolerance = 1, delay_time = 0.1)
    sys.exit(app.exec())


def squid_main():
    app = QApplication()
    manager = SquidstatMppt(
        device_name = "Prime2809",
        port = "COM11",
        year = "2025",
        date = "07-24",
        fabricator = "Elnaz",
        channel_names = [
            "07-24-epfl",
            ],
        cell_area = 0.16,
        solar_irradiance = 100,
        main_state = MPPT_STATE
    )
    manager.set_JV_parameters(
        high_voltage = 1.2,
        low_voltage = -0.2,
        step_voltage_mV = 10,
        step_time_ms = 100,
        jv_sample_rate_modifier = 1
    )
    manager.set_const_voltage_parameters(
        duration = 30,
        sample_interval = 1
    )
    manager.set_mppt_parameters(
        mppt_duration = 30,
        mppt_step_voltage_mV = 10,
        mppt_step_time_ms = 300,
        mppt_type = BASIC_P_AND_O
    )
    manager.start_JV_scans()

    sys.exit(app.exec())


if __name__ == "__main__":
    squid_main()
