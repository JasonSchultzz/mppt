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
from mppt.kiethley import KeithleyMppt, GPIB
from PySide6.QtWidgets import QApplication
from mppt.squidstat import SquidstatMppt, CONST_V_STATE, P_AND_O_STATE, META_P_AND_O_STATE
from mppt.mppt import InputData
from PySide6.QtCore import QTimer
import time

CONFIG = "./config/input.toml"


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
    input_data = InputData(CONFIG)
    manager = SquidstatMppt(input_data)
    manager.start_JV_scans()
    sys.exit(app.exec())


if __name__ == "__main__":
    squid_main()
