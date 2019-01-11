import numpy as np
import porepy as pp

import examples.papers.flow_upscaling.solvers as solvers
from examples.papers.flow_upscaling.import_grid import grid, square_grid

def main(file_geo, param, mesh_args, tol):

    # import the grid and the domain
    gb, param["domain"] = grid(file_geo, mesh_args, tol)

    # solve the pressure problem
    model_flow = solvers.flow(gb, param)

    solvers.adv(gb, param, model_flow)

if __name__ == "__main__":

    theta_ref = 80. * pp.CELSIUS
    fluid = pp.Water(theta_ref)
    rock = pp.Granite(theta_ref)

    n_steps = 500

    mu = fluid.dynamic_viscosity()

    folder_fractures = "../fracture_networks/"

    id_fracs = np.arange(8)

    for id_frac in id_fracs:

        if id_frac == 0:
            h = 0.25*1e-2
            file_geo = folder_fractures + "Algeroyna_1to1.csv"
            tol = {"geo": 2.5*1e-3, "snap": 0.75*2.5*1e-3}
            folder = "algeroyna_1to1"

            delta_x = 0.13
            bc_flow = pp.BAR

            aperture = pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 5 * 1e3

        elif id_frac == 1:
            h = 0.0390625
            file_geo = folder_fractures + "Algeroyna_1to10.csv"
            tol = {"geo": 1e-8, "snap": 1e-3}
            folder = "algeroyna_1to10"

            delta_x = 2.8
            bc_flow = 5 * pp.BAR

            aperture = pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 1e5

        elif id_frac == 2:
            h = 0.25
            file_geo = folder_fractures + "Algeroyna_1to100.csv"
            tol = {"geo": 1e-2, "snap": 1e-2}
            folder = "algeroyna_1to100"

            delta_x = 15.5
            bc_flow = 15 * pp.BAR

            aperture = 2 * pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 1e6

        elif id_frac == 3:
            h = 5
            file_geo = folder_fractures + "Algeroyna_1to1000.csv"
            tol = {"geo": 1e-2, "snap": 1e-2}
            folder = "algeroyna_1to1000"

            delta_x = 245
            bc_flow = 20 * pp.BAR

            aperture = 20 * pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 1e7

        elif id_frac == 4:
            h = 30
            file_geo = folder_fractures + "Algeroyna_1to10000.csv"
            tol = {"geo": 1e-3, "snap": 1e-3}
            folder = "algeroyna_1to10000"

            delta_x = 3160
            bc_flow = 50 * pp.BAR

            aperture = 100 * pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 1e8

        elif id_frac == 5:
            h = 0.75*1e-1
            file_geo = folder_fractures + "Vikso_1to10.csv"
            tol = {"geo": 1e-3, "snap": 0.75*1e-3}
            folder = "vikso_1to10"

            delta_x = 4
            bc_flow = 5 * pp.BAR
            km = 1e-14

            aperture = pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 1e5

        elif id_frac == 6:
            h = 0.375
            file_geo = folder_fractures + "Vikso_1to100.csv"
            tol = {"geo": 1e-3, "snap": 0.75*1e-3}
            folder = "vikso_1to100"

            delta_x = 30
            bc_flow = 15 * pp.BAR

            aperture = 2 * pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 1e6

        elif id_frac == 7:
            h = 2.5
            file_geo = folder_fractures + "/Vikso_1to1000.csv"
            tol = {"geo": 1e-2, "snap": 1e-2}
            folder = "vikso_1to1000"

            delta_x = 295
            bc_flow = 20 * pp.BAR

            aperture = 20 * pp.MILLIMETER
            kf = aperture * aperture / 12
            km = 1e-5 * kf

            t_max = 1e7

        # split_branch is 1
        mesh_args = {'mesh_size_frac': h, "mesh_size_min": h/2, "split_branch": 1}

        # select the permeability depending on the selected test case
        param = {
            "aperture": aperture,
            "kf": kf,
            "km": km,
            "porosity_f": 0.85,
            "time_step": t_max/n_steps,
            "n_steps": n_steps,
            "fluid": fluid,
            "rock": rock,
            "tol": tol["geo"],
            "folder": folder,
            "bc_flow": bc_flow,
            "initial_adv": theta_ref,
            "bc_adv": 20 * pp.CELSIUS
        }

        main(file_geo, param, mesh_args, tol)
