import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from datetime import datetime


FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def convert_timestamp_to_datetime(timestamp: np.ndarray) -> list:
    new_timestamp = []
    for t in timestamp:
        new_timestamp.append(datetime.strptime(t, FORMAT))
    return new_timestamp


def plot_mppt(directory: str) -> None:
    data = pd.read_csv(f"{directory}/mppt_data.csv")
    timestamp = convert_timestamp_to_datetime(np.array(data["Timestamp"]))

    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    line1 = ax1.scatter(timestamp, data["Voltage (V)"], color = "blue", label = "Voltage")
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Voltage (V)")
    line2 = ax2.scatter(timestamp, data["PCE (%)"], color = "orange", label = "PCE")
    ax2.set_ylabel("PCE (%)")
    ax2.legend(handles = [line1, line2])
    plt.show()


def split_JV_scans(data: pd.DataFrame) -> list[pd.DataFrame]:
    first_column = data.columns[0]
    index = data.index[data[first_column] == 0].to_list()
    split_points = [0] + index + [len(data)]
    scans = [
        data.iloc[split_points[i] : split_points[i+1]]
        for i in range(len(split_points) - 1)
        if not data.iloc[split_points[i] + 1 : split_points[i+1]].empty
    ]
    return scans


def plot_JV_scans(directory: str) -> None:
    fdata = pd.read_csv(f"{directory}/forward_scan.csv")
    rdata = pd.read_csv(f"{directory}/reverse_scan.csv")

    fscans = split_JV_scans(fdata)
    rscans = split_JV_scans(rdata)

    # fscans = fscans[int(len(fscans)/2):len(fscans)]
    # rscans = rscans[int(len(rscans)/2):len(rscans)]

    for (i, f) in enumerate(fscans):
        plt.plot(f["Voltage (V)"], f["Current Density (mA/cm2)"], label = f"FS {i+1}")
    for (i, f) in enumerate(rscans):
        plt.plot(f["Voltage (V)"], f["Current Density (mA/cm2)"], ls = "--", label = f"RS {i+1}")
    plt.xlim([-0.2, 1.2])
    plt.xlabel("Voltage (V)")
    plt.ylabel("Current Density ($mA/cm^{2}$)")
    plt.legend()
    plt.show()


def plot_compiled_results(directory: str) -> None:
    data = pd.read_csv(f"{directory}/compiled_data.csv")
    fdata = data.loc[data["Direction"] == "Forward"]
    rdata = data.loc[data["Direction"] == "Reverse"]

    ftimestamp = convert_timestamp_to_datetime(np.array(fdata["Timestamp"]))
    rtimestamp = convert_timestamp_to_datetime(np.array(rdata["Timestamp"]))

    plt.scatter(ftimestamp, fdata["PCE (%)"], color = "blue", label = "FS")
    plt.scatter(rtimestamp, rdata["PCE (%)"], color = "orange", label = "RS")
    plt.xlabel("Time")
    plt.ylabel("PCE (%)")
    plt.legend()
    plt.show()


if __name__ == "__main__":
    fabricator = "Elnaz"
    year = "2025"
    date = "08-14"
    cell_name = "06u-epfl"
    directory = f"./output/{fabricator}/{year}/{date}/{cell_name}"

    plot_mppt(directory)
    # plot_JV_scans(directory)
    # plot_compiled_results(directory)