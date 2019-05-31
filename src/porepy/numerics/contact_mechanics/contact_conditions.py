#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 13 08:53:05 2019

@author: eke001
"""
import numpy as np
import scipy.sparse as sps

import porepy as pp


class ColoumbContact:
    def __init__(self, keyword, ambient_dimension):
        self.keyword = keyword

        self.dim = ambient_dimension

        self.surface_variable = "mortar_u"
        self.contact_variable = "contact_force"

        self.friction_parameter_key = "friction"
        self.surface_parameter_key = "surface"

        self.traction_discretization = "traction_discretization"
        self.displacement_discretization = "displacement_discretization"
        self.rhs_discretization = "contact_rhs"

    def _key(self):
        return self.keyword + "_"

    def _discretization_key(self):
        return self._key() + pp.keywords.DISCRETIZATION

    def ndof(self, g):
        return g.num_cells * self.dim

    def discretize(self, g_h, g_l, data_h, data_l, data_edge):
        """ Discretize the contact conditions using a semi-smooth Newton
        approach.

        The function relates the contact forces, represented on the
        lower-dimensional grid, to the jump in displacement between the two
        adjacent mortar grids. The function provides a (linearized)
        disrcetizaiton of the contact conditions, as described in Berge et al.

        The discertization is stated in the coordinate system defined by the
        projection operator associated with the surface. The contact forces
        should be interpreted as tangential and normal to this plane.

        NOTE: Quantities stated in the global coordinate system (e.g.
        displacements on the adjacent mortar grids) must be projected to the
        local system, using the same projection operator, when paired with the
        produced discretization (that is, in the global assembly).

        Assumptions and other noteworthy aspects:  TODO: Rewrite this when the
        implementation is ready.
            * The contact surface is planar, so that all cells on the surface can
            be described by a single normal vector.
            * The contact forces are represented directly in the local
            coordinate system of the surface. The first self.dim - 1 elements
            of the contact vector are the tangential components of the first
            cell, then the normal component, then tangential of the second cell
            etc.

        """

        # CLARIFICATIONS NEEDED:
        #   1) Do projection and rotation commute on non-matching grids? The
        #   gut feel says yet, but I'm not sure.

        # Process input
        parameters_l = data_l[pp.PARAMETERS]
        friction_coefficient = parameters_l[self.friction_parameter_key][
            "friction_coefficient"
        ]

        if np.asarray(friction_coefficient).size == 1:
            friction_coefficient = friction_coefficient * np.ones(g_l.num_cells)

        # Numerical parameter, value and sensitivity is currently unknown.
        # The thesis of Huber is probably a good place to look for information.
        c_num = 100

        mg = data_edge["mortar_grid"]

        # TODO: Implement a single method to get the normal vector with right sign
        # thus the right local coordinate system.

        # Pick the projection operator (defined elsewhere) for this surface.
        # IMPLEMENATION NOTE: It is paramount that this projection is used for all
        # operations relating to this surface, or else directions of normal vectors
        # will get confused.
        projection = data_edge["tangential_normal_projection"]

        # The contact force is already computed in local coordinates
        contact_force = data_l[self.contact_variable]

        # Pick out the tangential and normal direction of the contact force.
        # The contact force of the first cell is in the first self.dim elements
        # of the vector, second cell has the next self.dim etc.
        # By design the tangential force is the first self.dim-1 components of
        # each cell, while the normal force is the last component.
        normal_indices = np.arange(self.dim - 1, contact_force.size, self.dim)
        tangential_indices = np.setdiff1d(np.arange(contact_force.size), normal_indices)
        contact_force_normal = contact_force[normal_indices]
        contact_force_tangential = contact_force[tangential_indices].reshape(
            (self.dim - 1, g_l.num_cells), order="F"
        )

        # The displacement jump (in global coordinates) is found by switching the
        # sign of the second mortar grid, and then sum the displacements on the
        # two sides (which is really a difference since one of the sides have
        # its sign switched).
        displacement_jump_global_coord = (
            mg.mortar_to_slave_avg(nd=self.dim)
            * mg.sign_of_mortar_sides(nd=self.dim)
            * data_edge[self.surface_variable]
        )

        # Rotated displacement jumps. these are in the local coordinates, on
        # the lower-dimensional grid
        displacement_jump_normal = (
            projection.project_normal(g_l.num_cells) * displacement_jump_global_coord
        )
        # The jump in the tangential direction is in g_l.dim columns, one per
        # dimension in the tangential direction.
        displacement_jump_tangential = (
            projection.project_tangential(g_l.num_cells)
            * displacement_jump_global_coord
        ).reshape((self.dim - 1, g_l.num_cells), order="F")

        # The friction bound is computed from the previous state of the contact
        # force and normal component of the displacement jump.
        # Note that the displacement jump is rotated before adding to the contact force
        friction_bound = friction_coefficient * np.clip(
            -contact_force_normal + c_num * displacement_jump_normal, 0, np.inf
        )

        num_cells = friction_coefficient.size

        # Find contact and sliding region

        # Contact region is determined from the normal direction, stored in the
        # last row of the projected stress and deformation.
        penetration_bc = self._penetration(
            contact_force_normal, displacement_jump_normal, c_num
        )
        sliding_bc = self._sliding(
            contact_force_tangential,
            displacement_jump_tangential,
            friction_bound,
            c_num,
        )

        # Structures for storing the computed coefficients.
        displacement_weight = []  # Multiplies displacement jump
        traction_weight = []  # Multiplies the normal forces
        rhs = np.array([])  # Goes to the right hand side.

        # Zero vectors of the size of the tangential space and the full space,
        # respectively. These are needed to complement the discretization
        # coefficients to be determined below.
        zer = np.array([0] * (self.dim - 1))
        zer1 = np.array([0] * (self.dim))
        zer1[-1] = 1

        # Loop over all mortar cells, discretize according to the current state of
        # the contact
        # The loop computes three parameters:
        # L will eventually multiply the displacement jump, and be associated with
        #   the coefficient in a Robin boundary condition (using the terminology of
        #   the mpsa implementation)
        # r is the right hand side term

        for i in range(num_cells):
            if sliding_bc[i] & penetration_bc[i]:  # in contact and sliding
                # The equation for the normal direction is computed from equation
                # (24)-(25) in Berge et al.
                # Compute coeffecients L, r, v
                loc_displacement_tangential, r, v = self._L_r(
                    contact_force_tangential[:, i],
                    displacement_jump_tangential[:, i],
                    friction_bound[i],
                    c_num,
                )

                # There is no interaction between displacement jumps in normal and
                # tangential direction
                L = np.hstack((loc_displacement_tangential, np.atleast_2d(zer).T))
                loc_displacement_weight = np.vstack((L, zer1))
                # Right hand side is computed from (24-25). In the normal
                # direction, zero displacement is enforced.
                # This assumes that the original distance, g, between the fracture
                # walls is zero.
                r = np.vstack((r + friction_bound[i] * v, 0))
                # Unit contribution from tangential force
                loc_traction_weight = np.eye(self.dim)
                # Contribution from normal force
                loc_traction_weight[:-1, -1] = -friction_coefficient[i] * v.ravel()

            elif ~sliding_bc[i] & penetration_bc[i]:  # In contact and sticking
                # Weight for contact force computed according to (23)
                loc_traction_tangential = (
                    -friction_coefficient[i]
                    * displacement_jump_tangential[:, i].ravel("F")
                    / friction_bound[i]
                )
                # Unit coefficient for all displacement jumps
                loc_displacement_weight = np.eye(self.dim)

                # Tangential traction dependent on normal one
                loc_traction_weight = np.zeros((self.dim, self.dim))
                loc_traction_weight[:-1, -1] = loc_traction_tangential

                r = np.hstack((displacement_jump_tangential[:, i], 0)).T

            elif ~penetration_bc[i]:  # not in contact
                # This is a free boundary, no conditions on displacement
                loc_displacement_weight = np.zeros((self.dim, self.dim))

                # Free boundary conditions on the forces.
                loc_traction_weight = np.eye(self.dim)
                r = np.zeros(self.dim)

            else:  # should never happen
                raise AssertionError("Should not get here")

            # Scale equations (helps iterative solver)
            # TODO: Find out what happens here
            w_diag = np.diag(loc_displacement_weight) + np.diag(loc_traction_weight)
            W_inv = np.diag(1 / w_diag)
            loc_displacement_weight = W_inv.dot(loc_displacement_weight)
            loc_traction_weight = W_inv.dot(loc_traction_weight)
            r = r.ravel() / w_diag

            # Append to the list of global coefficients.
            displacement_weight.append(loc_displacement_weight)
            traction_weight.append(loc_traction_weight)
            rhs = np.hstack((rhs, r))

        traction_discretization_coefficients = sps.block_diag(traction_weight)
        displacement_discretization_coefficients = sps.block_diag(displacement_weight)

        data_l[pp.DISCRETIZATION_MATRICES][self.keyword][
            self.traction_discretization
        ] = traction_discretization_coefficients
        data_l[pp.DISCRETIZATION_MATRICES][self.keyword][
            self.displacement_discretization
        ] = displacement_discretization_coefficients
        data_l[pp.DISCRETIZATION_MATRICES][self.keyword][self.rhs_discretization] = rhs

    def assemble_matrix_rhs(self, g, data):
        # Generate matrix for the coupling. This can probably be generalized
        # once we have decided on a format for the general variables
        traction_coefficient = data[pp.DISCRETIZATION_MATRICES][self.keyword][
            self.traction_discretization
        ]
        displacement_coefficient = data[pp.DISCRETIZATION_MATRICES][self.keyword][
            self.displacement_discretization
        ]

        rhs = data[pp.DISCRETIZATION_MATRICES][self.keyword][self.rhs_discretization]

        return traction_coefficient, displacement_coefficient, rhs

    # Active and inactive boundary faces
    def _sliding(self, Tt, ut, bf, ct):
        """ Find faces where the frictional bound is exceeded, that is, the face is
        sliding.

        Arguments:
            Tt (np.array, nd-1 x num_faces): Tangential forces.
            u_hat (np.array, nd-1 x num_faces): Displacements in tangential
                direction.
            bf (np.array, num_faces): Friction bound.
            ct (double): Numerical parameter that relates displacement jump to
                tangential forces. See Huber et al for explanation.

        Returns:
            boolean, size num_faces: True if |-Tt + ct*ut| > bf for a face

        """
        # Use thresholding to not pick up faces that are just about sticking
        # Not sure about the sensitivity to the tolerance parameter here.
        return self._l2(-Tt + ct * ut) - bf > 1e-10

    def _penetration(self, Tn, un, cn):
        """ Find faces that are in contact.

        Arguments:
            Tn (np.array, num_faces): Normal forces.
            un (np.array, num_faces): Displament in normal direction.
            ct (double): Numerical parameter that relates displacement jump to
                normal forces. See Huber et al for explanation.

        Returns:
            boolean, size num_faces: True if |-Tt + ct*ut| > bf for a face

        """
        # Not sure about the sensitivity to the tolerance parameter here.
        tol = 1e-8 * cn
        return (-Tn + cn * un) > tol

    # Below here are different help function for calculating the Newton step
    def _ef(self, Tt, cut, bf):
        # Compute part of (25) in Berge et al.
        return bf / self._l2(-Tt + cut)

    def _Ff(self, Tt, cut, bf):
        # Implementation of the term Q involved in the calculation of (25) in Berge
        # et al.
        numerator = -Tt.dot((-Tt + cut).T)

        # Regularization to avoid issues during the iterations to avoid dividing by
        # zero if the faces are not in contact durign iterations.
        denominator = max(bf, self._l2(-Tt)) * self._l2(-Tt + cut)

        return numerator / denominator

    def _M(self, Tt, cut, bf):
        """ Compute the coefficient M used in Eq. (25) in Berge et al.
        """
        Id = np.eye(Tt.shape[0])
        return self._ef(Tt, cut, bf) * (Id - self._Ff(Tt, cut, bf))

    def _hf(self, Tt, cut, bf):
        return self._ef(Tt, cut, bf) * self._Ff(Tt, cut, bf).dot(-Tt + cut)

    def _L_r(self, Tt, ut, bf, c):
        """
        Compute the coefficient L, defined in Eq. (25) in Berge et al.

        Arguments:
            Tt: Tangential forces. np array, two or three elements
            ut: Tangential displacement. Same size as Tt
            bf: Friction bound for this mortar cell.
            c: Numerical parameter


        """
        if Tt.ndim <= 1:
            Tt = np.atleast_2d(Tt).T
            ut = np.atleast_2d(ut).T

        cut = c * ut
        # Identity matrix
        Id = np.eye(Tt.shape[0])

        # Shortcut if the friction coefficient is effectively zero.
        # Numerical tolerance here is likely somewhat arbitrary.
        if bf <= 1e-10:
            return (
                0 * Id,
                bf * np.ones((Id.shape[0], 1)),
                (-Tt + cut) / self._l2(-Tt + cut),
            )

        # Compute the coefficient M
        coeff_M = self._M(Tt, cut, bf)

        # Regularization during the iterations requires computations of parameters
        # alpha, beta, delta
        alpha = -Tt.T.dot(-Tt + cut) / (self._l2(-Tt) * self._l2(-Tt + cut))
        delta = min(self._l2(-Tt) / bf, 1)

        if alpha < 0:
            beta = 1 / (1 - alpha * delta)
        else:
            beta = 1

        # The expression (I - beta * M)^-1
        IdM_inv = np.linalg.inv(Id - beta * coeff_M)

        v = IdM_inv.dot(-Tt + cut) / self._l2(-Tt + cut)

        return c * (IdM_inv - Id), -IdM_inv.dot(self._hf(Tt, cut, bf)), v

    def _l2(self, x):
        x = np.atleast_2d(x)
        return np.sqrt(np.sum(x ** 2, axis=0))
