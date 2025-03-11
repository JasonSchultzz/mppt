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
import pyqtgraph as pg
from datetime import datetime
from PySide6.QtCore import QIODevice, QDataStream, QByteArray, QThread, QObject, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
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

JV_SWEEP_STATE = 0
MPP_STATE = 1
DEAD_STATE = 2

class MpptManager:
    def __init__(
            self,
            path: str,
            port: str,
            device_name: str,
            channel_names: list[str]
    ) -> None:
        assert(len(channel_names) <= 4)
        self.channel_data: list[MpptData] = []
        for channel_name in channel_names:
            self.channel_data.append(MpptData(channel_name))

        self.path = path
        self.tracker = AisDeviceTracker.Instance()
        self.tracker.newDeviceConnected.connect(lambda deviceName: print("Device is Connected: %s" % deviceName))
        self.tracker.connectToDeviceOnComPort(port)
        self.handler = self.tracker.getInstrumentHandler(device_name)

        self.handler.experimentNewElementStarting.connect(lambda channel, data: self.experiment_started(channel))
        self.handler.activeDCDataReady.connect(
            lambda channel, data: self.channel_data[channel].append_JV_sweep_data(
                                        data.workingElectrodeVoltage,
                                        data.current
                                    )
        )
        self.handler.experimentStopped.connect(lambda channel : self.experiment_finished(channel))


    def set_mppt_testing_parameters(
            self,
            low_voltage: float,
            high_voltage: float,
            sweep_data_points: int,
            step_time: float,
            scan_time: float,
            cell_area: float,
            solar_irradiance: float,
            constant_voltage_duration: float,
            constant_voltage_sampling_interval: float = 10
    ) -> None:
        self.cell_area = cell_area
        self.solar_irradiance = solar_irradiance
        step_voltage = (high_voltage - low_voltage)/sweep_data_points
        self.constant_voltage_duration = constant_voltage_duration
        self.constant_voltage_sampling_interval = constant_voltage_sampling_interval

        self.experiment = AisExperiment()
        self.forwardJVSweep = AisSteppedVoltageElement(
            low_voltage,
            high_voltage,
            step_voltage,
            step_time,
            scan_time
        )
        self.reverseJVSweep = AisSteppedVoltageElement(
            high_voltage,
            low_voltage,
            step_voltage,
            step_time,
            scan_time
        )
        
        self.experiment.appendElement(self.forwardJVSweep)
        self.experiment.appendElement(self.reverseJVSweep)
        

    def start_JVsweep(self) -> None:
        # Ensure list is not empty -> at least one channel is used
        assert(self.channel_data)
        for (i, _) in enumerate(self.channel_data):
            self.handler.uploadExperimentToChannel(i, self.experiment)
            self.handler.startUploadedExperiment(i)


    # Possibly deprecated?
    # def start_JVsweep(self, channel: int) -> None:
    #     assert(isinstance(channel, int))
    #     assert(channel >= 0)
    #     assert(channel < len(self.channel_data))
    #     self.handler.uploadExperimentToChannel(channel, self.experiment)
    #     self.handler.startUploadedExperiment(channel)


    def start_MPP(self) -> None:
        assert(self.channel_data)
        for (i, channel) in enumerate(self.channel_data):
            constant_potential = AisConstantPotElement(
                channel.Vmpp,
                self.constant_voltage_sampling_interval,
                self.constant_voltage_duration
            )
            constant_potential_experiment = AisExperiment()
            constant_potential_experiment.appendElement(constant_potential)
            self.handler.uploadExperimentToChannel(i, constant_potential_experiment)
            self.handler.startUploadedExperiment(i)


    def output_JV_data_to_csv(self, channel: int) -> float:
        return self.channel_data[channel].format_results(
            self.cell_area,
            self.solar_irradiance,
            self.path
        )


    def experiment_started(self, channel: int) -> None:
        if self.channel_data[channel].state == JV_SWEEP_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: JV sweep started")
            self.channel_data[channel].store()
        elif self.channel_data[channel].state == MPP_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: MPP started at {self.channel_data[channel].Vmpp:.2f}")
        else:  # Dead state
            print(f"Time: {datetime.now()}, Channel {channel}: DEAD STATE - SHOULD NOT BE STARTING AN EXPERIMENT")


    def experiment_finished(self, channel: int) -> None:
        if self.channel_data[channel].state == JV_SWEEP_STATE:
            self.channel_data[channel].store()
            self.output_JV_data_to_csv(channel)
            print(f"Time: {datetime.now()}, Channel {channel}: JV sweep complete")
            if self.confirm_all_matching_states(MPP_STATE):
                self.start_MPP()

        elif self.channel_data[channel].state == MPP_STATE:
            self.channel_data[channel].state = JV_SWEEP_STATE
            print(f"Time: {datetime.now()}, Channel {channel}: MPP duration elapsed")
            if self.confirm_all_matching_states(JV_SWEEP_STATE):
                self.start_JVsweep()

        else:  # Dead state
            # Need to check that every other channel has reached dead state to quit
            app.quit()


    def confirm_all_matching_states(self, state: int) -> bool:
        for channel in self.channel_data:
            if channel.state != state:
                return False
        return True
        

class MpptData:
    def __init__(self, name: str) -> None:
        self.voltage = []
        self.current = []
        self.timestamp = []
        self.sweep_data_list = []
        self.name = name
        self.state = JV_SWEEP_STATE
        self.initial_efficiencies = (None, None)
        self.initial_timestamp = (None, None)
        self.Vmpp = None


    def append_JV_sweep_data(self, voltage: float, current: float):
        if self.state == JV_SWEEP_STATE:
            self.voltage.append(voltage)
            self.current.append(current)
            self.timestamp.append(datetime.now())
    

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
            current_density = -1*np.array(data["Current (A)"])*1000/cell_area  # mA/cm2
            power_density = voltage*current_density  # mW/cm2
            efficiency = power_density*100/solar_irradiance
            results.append(pd.DataFrame({
                "Timestamp": data["Timestamp"],
                "Voltage (V)": voltage,
                "Current Density (mA/cm2)": current_density,
                "Power Density (mW/cm2)": power_density,
                "PCE (%)": efficiency
            }))

            mpp_index = np.argmin(power_density)
            Vmpp = voltage[mpp_index]
            Jsc = np.interp(0, voltage, current_density)

            if i == 0:
                direction = "Forward"
                Voc = np.interp(0, current_density, voltage)
                self.Vmpp = Vmpp
            elif i == 1:
                direction = "Reverse"
                Voc = np.interp(0, current_density[::-1], voltage[::-1])
                
            Jmpp = current_density[mpp_index]
            FF = Vmpp*Jmpp*100/(Voc*Jsc)
            t = datetime.now()
            compiled_data = pd.DataFrame({
                "Time": [t],
                "Direction": direction,
                "PCE (%)": [power_density[mpp_index]*100/solar_irradiance],
                "FF (%)": [FF],
                "Vmpp (V)": [Vmpp],
                "Jmpp (mA/cm2)": [Jmpp],
                "Voc (V)": [Voc],
                "Jsc (mA/cm2)": [Jsc]
            })
            print(compiled_data)
            compiled_data.to_csv(f"{path}/compiled_data.csv", mode = "a", header = not os.path.exists(f"{path}/compiled_data.csv"))

        results[0].to_csv(f"{path}/forward_sweep_data.csv", mode = "a", header = not os.path.exists(f"{path}/forward_sweep_data.csv"))
        results[1].to_csv(f"{path}/reverse_sweep_data.csv", mode = "a", header = not os.path.exists(f"{path}/reverse_sweep_data.csv"))

        # Need to check that both max efficiencies are above initial efficiency
        self.state = MPP_STATE
        self.sweep_data_list = []


class LivePlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Plot Updates")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Set main layout to be a vertical box
        main_layout = QVBoxLayout(central_widget)

        # Create a grid layout for first 4 plots
        grid_layout = QGridLayout()

        # Create 5 subplots
        self.figures = [Figure(figsize = (5, 4)) for _ in range(5)]
        self.canvas = [FigureCanvas(fig) for fig in self.figures]

        # Create axes and plots
        self.axes = [fig.add_subplot(111) for fig in self.figures]

        # Create the grid for the first 4 plots
        for i, canvas_item in enumerate(self.canvas[:4]):
            row = i // 2  # 2 rows
            col = i % 2  # 2 columns
            grid_layout.addWidget(canvas_item, row, col)

        # Add the grid layout to the main layout
        main_layout.addLayout(grid_layout)

        # Create a separate layout for the 5th plot
        bottom_layout = QVBoxLayout()
        bottom_layout.addWidget(self.canvas[4])

        # Add the bottom plot layout to the main layout
        main_layout.addLayout(bottom_layout)

        # Initialize data for plotting
        self.x_data = np.linspace(0, 10, 100)
        self.y_data = [np.zeros_like(self.x_data) for _ in range(5)]

        # Create the intial plots
        for i, ax in enumerate(self.axes):
            ax.plot(self.x_data, self.y_data[i])
            if i == 4:
                ax.set_xlabel("Duration")
                ax.set_ylabel("Normalized PCE")
                ax.set_title("MPPT")
            else:
                ax.set_xlabel("Voltage (V)")
                ax.set_ylabel("Current Density ($mA/cm^{2}$)")
                ax.set_title(f"Channel {i+1} JV Data")


    def update_plot_data(self):
        # Simulate changing data
        self.y_data[0] = np.sin(self.x_data)

        # Update each plot
        for i, ax in enumerate(self.axes):
            ax.clear()  # Clear the old plot
            ax.plot(self.x_data, self.y_data[i])
            ax.set_title(f"Plot {i + 1}")  # Set plot title

        # Refresh the canvas to reflect the changes
        for canvas_item in self.canvas:
            canvas_item.draw()


app = QApplication()
window = LivePlotter()
window.show()
# manager = MpptManager(
#     path = "./output",
#     port = "COM3",
#     device_name = "Prime2809",
#     channel_names = ["test0", "test1", "test2", "test3"]
# )
# manager.set_mppt_testing_parameters(
#     low_voltage = -0.2,     # V
#     high_voltage = 1.2,     # V
#     sweep_data_points = 140,
#     step_time = 0.07,       # s
#     scan_time = 0.06,       # s
#     cell_area = 0.16,       # cm2
#     solar_irradiance = 100,  # mW/cm2,
#     constant_voltage_duration = 60  # s
# )
# manager.start_JVsweep()

sys.exit(app.exec())