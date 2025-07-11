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
        path = "./output",
        GPIB = GPIB,
        cell_name = "2025-07-11-TEST"        
    )
    manager.set_mppt_testing_parameters(
        low_voltage = -0.2,         # V
        high_voltage = 1.2,         # V
        step_voltage = 30,          # mV
        scan_speed = 100,           # mV/s
        mpp_duration = 30,          # s
        mpp_sample_interval = 1,    # s
        cell_area = 0.16,           # cm2
        solar_irradiance = 100,     # mW/cm2
        averages = 5
    )
    # manager.perform_JV_scans()
    manager.perturb_and_observe_metastable_psc(starting_voltage = 0.5, tolerance = 1, delay_time = 0.1)
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
