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
from mppt.squidstat import SquidstatMppt
from mppt.kiethley import KeithleyMppt, GPIB
from PySide6.QtWidgets import QApplication


def keithley_main():
    app = QApplication()
    manager = KeithleyMppt(
        GPIB = GPIB,
        year = "2025",
        fabricator = "Elnaz",
        cell_name = "07-15-08u",
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
        fabricator = "Elnaz",
        channel_names = [
            "07-16-08u-epfl",
            ],
        cell_area = 0.16,
        solar_irradiance = 100
    )
    manager.set_JV_parameters(
        high_voltage = 1.2,
        low_voltage = -0.2,
        step_voltage_mV = 10,
        step_time_ms = 100,
        jv_sample_rate_modifier = 1
    )
    manager.set_mppt_parameters(
        mpp_duration = 30,
        mpp_sample_interval = 1
    )
    manager.start_JVsweep()

    sys.exit(app.exec())


if __name__ == "__main__":
    squid_main()
