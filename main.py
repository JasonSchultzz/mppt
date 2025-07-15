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
        cell_name = "08u",
        cell_area = 0.16,
        solar_irradiance = 100
    )
    manager.set_JV_parameters_with_time_step(
        high_voltage = 1.2,
        low_voltage = -0.2,
        step_voltage_mV = 10,
        step_time_ms = 100,
        averages = 1
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
        path = "./output",
        port = "COM11",
        device_name = "Prime2809",
        channel_names = [
            "2025-06-26-Elnaz-08d-epfl-100mV/s",
            ]
    )
    manager.set_mppt_testing_parameters(
        low_voltage = -0.2,         # V
        high_voltage = 1.2,         # V
        step_voltage = 10,          # mV
        scan_speed = 100,           # mV/s
        jv_sample_rate_modifier = 1,
        mpp_duration = 30,          # s
        mpp_sample_interval = 1,    # s
        cell_area = 0.16,           # cm2
        solar_irradiance = 100      # mW/cm2
    )
    manager.start_JVsweep()

    sys.exit(app.exec())


if __name__ == "__main__":
    keithley_main()
