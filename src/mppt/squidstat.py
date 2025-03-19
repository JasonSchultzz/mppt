import sys
import os
import struct
import numpy as np
import pandas as pd
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

        self.window = LivePlotter()
        self.window.show()

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
        self.handler.experimentStopped.connect(lambda channel: self.experiment_finished(channel))


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
                self.window.update_plot_data(self.channel_data)
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

        # Initial recorded values as tuples: (forward, reverse)
        self.initial_voltages = (None, None)
        self.initial_current_densities = (None, None)
        self.recent_voltages = (None, None)
        self.recent_current_densities = (None, None)
        self.initial_timestamps = (None, None)
        self.initial_efficiencies = (None, None)
        self.forward_relative_efficiencies = []
        self.reverse_relative_efficiencies = []
        self.forward_durations = []
        self.reverse_durations = []

        self.Vmpp = None
        self.first: bool = True


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

            mpp_index = np.argmax(power_density)
            Vmpp = voltage[mpp_index]
            Jsc = np.interp(0, voltage, current_density)
            Jmpp = current_density[mpp_index]
            mpp_efficiency = efficiency[mpp_index]

            if i == 0:
                direction = "Forward"
                Voc = np.interp(0, current_density, voltage)
                self.Vmpp = Vmpp
                if self.first:
                    initial_forward_voltage = voltage
                    initial_forward_current_density = current_density
                    relative_efficiency = 1
                    self.forward_relative_efficiencies.append(relative_efficiency)
                    initial_forward_timestamp = datetime.now()
                    duration = 0
                    self.forward_durations.append(duration)
                    initial_forward_efficiency = mpp_efficiency
                else:
                    recent_forward_voltage = voltage
                    recent_forward_current_density = current_density
                    initial_forward_timestamp, _ = self.initial_timestamps
                    initial_forward_efficiency, _ = self.initial_efficiencies
                    relative_efficiency = mpp_efficiency/initial_forward_efficiency
                    self.forward_relative_efficiencies.append(relative_efficiency)
                    duration = (datetime.now() - initial_forward_timestamp).seconds/60
                    self.forward_durations.append(duration)
                    

            elif i == 1:
                direction = "Reverse"
                Voc = np.interp(0, current_density[::-1], voltage[::-1])
                if self.first:
                    initial_reverse_voltage = voltage
                    initial_reverse_current_density = current_density
                    relative_efficiency = 1
                    self.reverse_relative_efficiencies.append(relative_efficiency)
                    initial_reverse_timestamp = datetime.now()
                    duration = 0
                    self.reverse_durations.append(duration)
                    initial_reverse_efficiency = mpp_efficiency
                else:
                    recent_reverse_voltage = voltage
                    recent_reverse_current_density = current_density
                    _, initial_reverse_timestamp = self.initial_timestamps
                    _, initial_reverse_efficiency = self.initial_efficiencies
                    relative_efficiency = mpp_efficiency/initial_reverse_efficiency
                    self.reverse_relative_efficiencies.append(relative_efficiency)
                    duration = (datetime.now() - initial_reverse_timestamp).seconds/60
                    self.reverse_durations.append(duration)

            FF = Vmpp*Jmpp*100/(Voc*Jsc)

            compiled_data = pd.DataFrame({
                "Duration": [duration],
                "Direction": [direction],
                "Normalized PCE": [relative_efficiency],
                "PCE (%)": [mpp_efficiency],
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

        self.state = MPP_STATE
        self.sweep_data_list = []

        if self.first:
            self.initial_voltages = (initial_forward_voltage, initial_reverse_voltage)
            self.initial_current_densities = (initial_forward_current_density, initial_reverse_current_density)
            self.initial_timestamps = (initial_forward_timestamp, initial_reverse_timestamp)
            self.initial_efficiencies = (initial_forward_efficiency, initial_reverse_efficiency)
            self.first = False
        else:
            self.recent_voltages = (recent_forward_voltage, recent_reverse_voltage)
            self.recent_current_densities = (recent_forward_current_density, recent_reverse_current_density)


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
            ax.plot()
            if i == 4:
                ax.set_xlabel("Duration")
                ax.set_ylabel("Normalized PCE")
                ax.set_title("MPPT")
            else:
                ax.set_xlabel("Voltage (V)")
                ax.set_ylabel("Current Density ($mA/cm^{2}$)")
                ax.set_title(f"Channel {i+1} JV Data")


    def update_plot_data(self, channel_data: list[MpptData]) -> None:
        # Update each plot
        self.axes[4].clear()
        mppt_channel_colors = ["r", "b", "g", "m"]
        for i, data in enumerate(channel_data):
            ax = self.axes[i]
            ax.clear()  # Clear the old plot
            forward_voltage, reverse_voltage = data.initial_voltages
            forward_current_density, reverse_current_density = data.initial_current_densities

            # Plot the initial JV sweep
            ax.plot(forward_voltage, forward_current_density, color = 'b', label = "Initial Forward")
            ax.plot(reverse_voltage, reverse_current_density, color = 'r', label = "Initial Reverse")

            if (all(x is not None for x in data.recent_voltages)) and (all(y is not None for y in data.recent_current_densities)):
                forward_voltage, reverse_voltage = data.recent_voltages
                forward_current_density, reverse_current_density = data.recent_current_densities

                # Plot the latest JV sweep
                ax.plot(forward_voltage, forward_current_density, ls = ":", color = 'b', label = "Recent Forward")
                ax.plot(reverse_voltage, reverse_current_density, ls = ":", color = 'r', label = "Recent Reverse")

            # Set plots lables
            ax.set_xlabel("Voltage (V)")
            ax.set_ylabel("Current Density ($mA/cm^{2}$)")
            ax.set_title(f"Channel {i+1} JV Data")
            ax.set_ylim(0)
            ax.legend()

            # Update MPPT plot
            self.axes[4].plot(data.forward_durations, data.forward_relative_efficiencies, color = mppt_channel_colors[i], label = f"Forward {i+1}")
            self.axes[4].plot(data.reverse_durations, data.reverse_relative_efficiencies, color = mppt_channel_colors[i], ls = ":", label = f"Reverse {i+1}")
        
        self.axes[4].set_xlabel("Duration")
        self.axes[4].set_ylabel("Normalized PCE")
        self.axes[4].set_title("MPPT")
        self.axes[4].legend()

        # Refresh the canvas to reflect the changes
        for canvas_item in self.canvas:
            canvas_item.draw()


app = QApplication()
manager = MpptManager(
    path = "./output",
    port = "COM4",
    device_name = "Prime2809",
    channel_names = [
        "2025-03-18-Si1",
        "2025-03-18-Si2",
        "2025-03-18-Si3",
        "2025-03-18-Si4",
        ]
)
manager.set_mppt_testing_parameters(
    low_voltage = 0,     # V
    high_voltage = 0.6,     # V
    sweep_data_points = 120,
    step_time = 0.10,       # s
    scan_time = 0.08,       # s
    cell_area = 6,       # cm2
    solar_irradiance = 25,  # mW/cm2,
    constant_voltage_duration = 30  # s
)
manager.start_JVsweep()

sys.exit(app.exec())