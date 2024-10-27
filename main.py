#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Created By  : Jason Schultz
# Created Date: 2024-08-05
# version ='1.0'
# ---------------------------------------------------------------------------
"""a_short_project_description"""
# ---------------------------------------------------------------------------
import numpy as np
import matplotlib.pyplot as plt


def ideal_diode_eqn(V):
    J_o = 0.009
    k = 1
    T = 1
    J_L = 4446*J_o
    q = 7

    return -J_o*(np.exp(q*V/(k*T)) - 1) + J_L


def mppt_test():
    V_oc = 1.2
    V_plot = np.linspace(0, V_oc, 50)
    J_plot = ideal_diode_eqn(V_plot)
    P_plot = V_plot*J_plot

    dV = 0.05
    V0 = 0
    J = ideal_diode_eqn(V0)
    P0 = V0*J
    direction = 1

    while True:
        V = V0 + direction*dV
        J = ideal_diode_eqn(V)
        P = V*J
        if P > P0:
            if V > V0:
                direction = 1
            else:
                direction = -1
            P0 = P
            V0 = V
        else:
            if V > V0:
                direction = -1
            else:
                direction = 1
            P0 = P
            V0 = V 


        fig, ax1 = plt.subplots()
        ax1.plot(V_plot, J_plot, label = "Current Density")
        ax1.plot(V, J, "bo")
        ax1.set_xlabel("Voltage ($V$)")
        ax1.set_ylabel("Current Density ($mA/cm^{2}$)")

        ax2 = ax1.twinx()
        ax2.set_ylabel("Power Density ($mW/cm^{2}$)")
        ax2.plot(V_plot, P_plot, "r--", label = "Power Density")
        ax2.plot(V, P, "ro")
        plt.show()


def main():
    print("hello")


if __name__ == "__main__":
    mppt_test()
