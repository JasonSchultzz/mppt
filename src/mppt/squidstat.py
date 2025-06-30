import numpy as np
from datetime import datetime
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from SquidstatPyLibrary import AisDeviceTracker, AisExperiment, AisSteppedVoltageElement, AisConstantPotElement
from mppt.mppt import JV_SWEEP_STATE, MPP_STATE, DEAD_STATE, MpptData


class SquidstatMppt:
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

        # What occurs when a new expierment is started
        self.handler.experimentNewElementStarting.connect(lambda channel, data: self.experiment_started(channel))
        
        # What happens when data is recorded
        self.handler.activeDCDataReady.connect(
            lambda channel, data: self.channel_data[channel].append_data(
                                        data.workingElectrodeVoltage,
                                        data.current,
                                        datetime.now()
                                    )
        )

        # What happens when an experiment is finished
        self.handler.experimentStopped.connect(lambda channel: self.experiment_finished(channel))


    def set_mppt_testing_parameters(
            self,
            low_voltage: float,
            high_voltage: float,
            step_voltage: float,
            scan_speed: float,
            jv_sample_rate_modifier: float,
            mpp_duration: float,
            mpp_sample_interval: float,
            cell_area: float,
            solar_irradiance: float
    ) -> None:
        self.cell_area = cell_area
        self.solar_irradiance = solar_irradiance
        self.mpp_duration = mpp_duration
        self.mpp_sample_interval = mpp_sample_interval
        step_time = step_voltage/scan_speed
        sample_interval = step_time*jv_sample_rate_modifier
        step_voltage_in_volts = step_voltage/1000

        self.experiment = AisExperiment()
        self.forwardJVSweep = AisSteppedVoltageElement(
            low_voltage,
            high_voltage,
            step_voltage_in_volts,
            step_time,
            sample_interval
        )
        self.reverseJVSweep = AisSteppedVoltageElement(
            high_voltage,
            low_voltage,
            step_voltage_in_volts,
            step_time,
            sample_interval
        )
        
        self.experiment.appendElement(self.forwardJVSweep)
        self.experiment.appendElement(self.reverseJVSweep)
        

    def start_JVsweep(self) -> None:
        # Ensure list is not empty -> at least one channel is used
        assert(self.channel_data)
        for (i, _) in enumerate(self.channel_data):
            self.handler.uploadExperimentToChannel(i, self.experiment)
            self.handler.startUploadedExperiment(i)


    def start_MPP(self) -> None:
        assert(self.channel_data)
        for (i, channel) in enumerate(self.channel_data):
            constant_potential = AisConstantPotElement(
                channel.Vmpp,
                self.mpp_sample_interval,
                self.mpp_duration
            )
            constant_potential_experiment = AisExperiment()
            constant_potential_experiment.appendElement(constant_potential)
            self.handler.uploadExperimentToChannel(i, constant_potential_experiment)
            self.handler.startUploadedExperiment(i)


    def experiment_started(self, channel: int) -> None:
        if self.channel_data[channel].state == JV_SWEEP_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: JV sweep started")
            self.channel_data[channel].store()
        elif self.channel_data[channel].state == MPP_STATE:
            print(f"Time: {datetime.now()}, Channel {channel}: MPP started at {self.channel_data[channel].Vmpp:.2f}")
        else:  # Dead state
            print(f"Time: {datetime.now()}, Channel {channel}: DEAD STATE - SHOULD NOT BE STARTING AN EXPERIMENT")


    def experiment_finished(self, channel: int) -> None:
        # JV Sweeps finished. Compile data and proceed to held MPP state if all other channels are also finished.
        if self.channel_data[channel].state == JV_SWEEP_STATE:
            self.channel_data[channel].state = MPP_STATE
            self.channel_data[channel].store()
            self.channel_data[channel].format_results(
                self.cell_area,
                self.solar_irradiance,
                self.path,
            )
            print(f"Time: {datetime.now()}, Channel {channel}: JV sweep complete")
            if self.confirm_all_matching_states(MPP_STATE):
                self.window.update_plot_data(self.channel_data)
                self.start_MPP()

        # MPP duration elasped. Proceed to JV sweeps if all other channels are also finished.
        elif self.channel_data[channel].state == MPP_STATE:
            self.channel_data[channel].state = JV_SWEEP_STATE
            self.channel_data[channel].format_mpp_results(
                self.cell_area,
                self.solar_irradiance,
                self.path
            )
            print(f"Time: {datetime.now()}, Channel {channel}: MPP duration elapsed")
            if self.confirm_all_matching_states(JV_SWEEP_STATE):
                self.start_JVsweep()

        # Dead state
        else:  
            # Need to check that every other channel has reached dead state to quit
            # app.quit()
            pass


    def confirm_all_matching_states(self, state: int) -> bool:
        for channel in self.channel_data:
            if channel.state != state:
                return False
        return True
        

class LivePlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Plot Updates")
        self.setGeometry(0, 0, 1200, 700)

        # Create central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Set main layout to be a vertical box
        main_layout = QVBoxLayout(central_widget)

        # Create a grid layout for first 4 plots
        grid_layout = QGridLayout()

        # Create 5 subplots
        self.figures = [Figure(figsize = (5, 2.5)) for _ in range(5)]
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
            forward_voltage = data.initial_forward_voltage
            reverse_voltage = data.initial_reverse_voltage
            forward_current_density = data.initial_forward_current_density
            reverse_current_density = data.initial_reverse_current_density

            # Plot the initial JV sweep
            ax.plot(forward_voltage, forward_current_density, color = 'b', label = "Initial Forward")
            ax.plot(reverse_voltage, reverse_current_density, color = 'r', label = "Initial Reverse")

            forward_voltage = data.recent_forward_voltage
            reverse_voltage = data.recent_reverse_voltage
            forward_current_density = data.recent_forward_current_density
            reverse_current_density = data.recent_reverse_current_density
            if forward_voltage is not None and reverse_voltage is not None and forward_current_density is not None and reverse_current_density is not None:
                # Plot the latest JV sweep
                ax.plot(forward_voltage, forward_current_density, ls = ":", color = 'b', label = "Recent Forward")
                ax.plot(reverse_voltage, reverse_current_density, ls = ":", color = 'r', label = "Recent Reverse")

            # Set plots lables
            ax.set_xlabel("Voltage (V)")
            ax.set_ylabel("Current Density ($mA/cm^{2}$)")
            ax.set_title(f"Channel {i+1} JV Data")
            # ax.set_ylim((None, 0))  # View of Quadrant 4
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