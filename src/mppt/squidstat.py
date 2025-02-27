#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Created By  : Jason Schultz
# Created Date: 2024-08-05
# version ='1.0'
# ---------------------------------------------------------------------------
"""a_short_module_description"""
# ---------------------------------------------------------------------------

import sys
import os
import struct
import numpy as np
import pandas as pd
from datetime import datetime
from PySide6.QtCore import QIODevice, QDataStream, QByteArray, QThread, QObject, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo
from PySide6.QtWidgets import QApplication
from SquidstatPyLibrary import AisDeviceTracker
from SquidstatPyLibrary import AisCompRange
from SquidstatPyLibrary import AisDCData
from SquidstatPyLibrary import AisACData
from SquidstatPyLibrary import AisExperimentNode
from SquidstatPyLibrary import AisErrorCode
from SquidstatPyLibrary import AisExperiment
from SquidstatPyLibrary import AisInstrumentHandler
from SquidstatPyLibrary import AisSteppedVoltageElement
from SquidstatPyLibrary import AisConstantPotElement


class MpptManager:
    def __init__(
            self,
            path: str,
            port: str,
            device_name: str,
            channel_names: list[str]
    ) -> None:
        assert(len(channel_names) <= 4)
        self.channel_data = []
        for channel_name in channel_names:
            self.channel_data.append(MpptData(channel_name))

        self.path = path
        self.tracker = AisDeviceTracker.Instance()
        self.tracker.newDeviceConnected.connect(lambda deviceName: print("Device is Connected: %s" % deviceName))
        self.tracker.connectToDeviceOnComPort(port)
        self.handler = self.tracker.getInstrumentHandler(device_name)

        self.handler.experimentNewElementStarting.connect(
            lambda channel, data: (
                print("New Node beginning:", data.stepName, "step number: ", data.stepNumber, " step sub : ", data.substepNumber),
                self.channel_data[channel].store(),
            )
        )
        self.handler.activeDCDataReady.connect(
            lambda channel, data: (
                print("timestamp:", "{:.9f}".format(data.timestamp), "Voltage: ", "{:.9f}".format(data.workingElectrodeVoltage), "Current: ", "{:.9f}".format(data.current)),
                self.channel_data[channel].voltage.append(data.workingElectrodeVoltage),
                self.channel_data[channel].current.append(data.current),
                self.channel_data[channel].timestamp.append(datetime.now())
            )
        )
        # TODO: This needs to not quit the program after 1 experiment finishes
        self.handler.experimentStopped.connect(
            lambda channel : (
                print("Experiment Completed: %d" % channel),
                self.channel_data[channel].store(),
                self.output_JV_data_to_csv(channel),
                # app.quit()  # Currently quits if only 1 channel finishes
            )
        )


    def set_JVsweep_parameters(
            self,
            low_voltage: float,
            high_voltage: float,
            n_data_points: int,
            step_time: float,
            scan_time: float,
            cell_area: float,
            solar_irradiance: float
    ) -> None:
        self.cell_area = cell_area
        self.solar_irradiance = solar_irradiance
        step_voltage = (high_voltage - low_voltage)/n_data_points

        self.experiment = AisExperiment()
        forwardJVSweep = AisSteppedVoltageElement(
            low_voltage,
            high_voltage,
            step_voltage,
            step_time,
            scan_time
        )
        reverseJVSweep = AisSteppedVoltageElement(
            high_voltage,
            low_voltage,
            step_voltage,
            step_time,
            scan_time
        )
        
        self.experiment.appendElement(forwardJVSweep)
        self.experiment.appendElement(reverseJVSweep)
        

    def set_fixed_potential_parameters(
            self,
            voltage: float,
            sampling_interval: float,
            duration: float
    ) -> None:
        fixedPotential = AisConstantPotElement(
            voltage, sampling_interval, duration
        )
        # Should this get appended to experiment or does a new experiment get created?


    def start_JVsweep(self, channel: int) -> None:
        assert(isinstance(channel, int))
        assert(channel >= 0)
        assert(channel < len(self.channel_data))
        self.handler.uploadExperimentToChannel(channel, self.experiment)
        self.handler.startUploadedExperiment(channel)


    def output_JV_data_to_csv(self, channel: int) -> None:
        self.channel_data[channel].format_results(
            self.cell_area,
            self.solar_irradiance,
            self.path
        )


class MpptData:
    def __init__(self, name: str) -> None:
        self.voltage = []
        self.current = []
        self.timestamp = []
        self.sweep_data_list = []
        self.name = name


    def store(self) -> None:
        if self.voltage and self.current:  # Both are not empty
            self.sweep_data_list.append({
                "Timestamp": self.timestamp,
                "Voltage (V)": self.voltage,
                "Current (A)": self.current
                }
            )
            self.voltage = []
            self.current = []
            self.timestamp = []


    def format_results(
            self, cell_area: float,
            solar_irradiance: float,
            directory: str
    ) -> None:
        path = f"{directory}/{self.name}"
        if not os.path.exists(path):
            os.makedirs(path)

        results = []
        for (i, data) in enumerate(self.sweep_data_list):
            voltage = np.array(data["Voltage (V)"])  # V
            current_density = np.array(data["Current (A)"])/(cell_area*1000)  # mA/cm2
            power_density = voltage*current_density  # mW/cm2
            efficiency = power_density*100/solar_irradiance
            results.append(pd.DataFrame({
                "Timestamp": data["Timestamp"],
                "Voltage (V)": voltage,
                "Current Density (mA/cm2)": current_density,
                "Power Density (mW/cm2)": power_density,
                "PCE (%)": efficiency
            }))

            if i == 0:
                direction = "Forward"
            elif i == 1:
                direction = "Reverse"

            Jsc = np.interp(0, voltage, current_density)
            Voc = np.interp(0, current_density, voltage)
            mpp_index = np.argmin(power_density)
            Vmpp = voltage[mpp_index]
            Jmpp = current_density[mpp_index]
            FF = Vmpp*Jmpp*100/(Voc*Jsc)
            t = datetime.now()
            compiled_data = pd.DataFrame({
                "Time": [t],
                "Direction": direction,
                "Efficiency (%)": [power_density[mpp_index]*100/solar_irradiance],
                "Fill Factor (%)": [FF],
                "Vmpp (V)": [Vmpp],
                "Jmpp (mA/cm2)": [Jmpp],
                "Voc (V)": [Voc],
                "Jsc (mA/cm2)": [Jsc]
            })
            compiled_data.to_csv(f"{path}/compiled_data.csv", mode = "a", header = not os.path.exists(f"{path}/compiled_data.csv"))

        results[0].to_csv(f"{path}/forward_sweep_data.csv", mode = "a", header = not os.path.exists(f"{path}/forward_sweep_data.csv"))
        results[1].to_csv(f"{path}/reverse_sweep_data.csv", mode = "a", header = not os.path.exists(f"{path}/reverse_sweep_data.csv"))


def main():
    app = QApplication()
    manager = MpptManager(
        path = "./output",
        port = "COM3",
        device_name = "Prime2809",
        channel_names = ["test0", "test1", "test2", "test3"]
    )
    manager.set_JVsweep_parameters(
        low_voltage = -0.2,     # V
        high_voltage = 1.2,     # V
        n_data_points = 140,
        step_time = 0.05,       # s
        scan_time = 0.04,       # s
        cell_area = 0.16,       # cm2
        solar_irradiance = 100  # mW/cm2
    )
    manager.start_JVsweep(channel = 0)
    manager.start_JVsweep(channel = 1)
    manager.start_JVsweep(channel = 2)
    manager.start_JVsweep(channel = 3)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()