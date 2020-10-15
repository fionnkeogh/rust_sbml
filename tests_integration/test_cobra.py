import cobra
import pytest
from collections import defaultdict
import rust_sbml


def sbml_to_model(path, number=float, set_missing_bounds=False, **kwargs):
    """Creates cobra model from SBMLDocument.
    Parameters
    ----------
    doc: libsbml.SBMLDocument
    number: data type of stoichiometry: {float, int}
        In which data type should the stoichiometry be parsed.
    f_replace : dict of replacement functions for id replacement
    set_missing_bounds : flag to set missing bounds
    Returns
    -------
    cobra.core.Model
    """
    # SBML model
    model = rust_sbml.Model(path)
    if model is None:
        raise cobra.CobraSBMLError("No SBML model detected in file.")
    cobra_model = cobra.Model("my_model")
    cobra_model.name = "kai model"

    # FIXME: update with new compartments
    compartments = {}
    for compartment in model.getListOfCompartments():
        cid = compartment.id
        compartments[cid] = compartment.name
    cobra_model.compartments = compartments

    # Species
    metabolites = []

    for specie in model.getListOfSpecies():  # type: rust_sbml.Specie
        sid = specie.id

        met = cobra.Metabolite(sid)
        met.name = specie.id

        met.compartment = specie.getCompartment()

        metabolites.append(met)

    cobra_model.add_metabolites(metabolites)

    reactions = []
    for reaction in model.getListOfReactions():  # type: rust_sbml.Reaction
        rid = reaction.id
        cobra_reaction = cobra.Reaction(rid)
        cobra_reaction.name = reaction.name

        # set bounds
        p_ub, p_lb = None, None
        lb_id = reaction.getLowerFluxBound()
        if lb_id:
            p_lb = model.getParameter(lb_id)  # type: rust_sbml.Parameter
            print(p_lb)
            if p_lb and p_lb.getConstant() and (p_lb.getValue() is not None):
                print(p_lb.getValue())
                cobra_reaction.lower_bound = p_lb.getValue()
            else:
                raise cobra.CobraSBMLError(
                    "No constant bound '%s' for "
                    "reaction: %s" % (p_lb, reaction)
                )

        ub_id = reaction.getUpperFluxBound()
        if ub_id:
            p_ub = model.getParameter(ub_id)  # type: rust_sbml.PyParam
            if p_ub and p_ub.getConstant() and (p_ub.getValue() is not None):
                cobra_reaction.upper_bound = p_ub.getValue()
            else:
                raise cobra.CobraSBMLError(
                    "No constant bound '%s' for "
                    "reaction: %s" % (p_ub, reaction)
                )

        if p_lb is None:
            lower_bound = -1000
            cobra_reaction.lower_bound = lower_bound

        if p_ub is None:
            upper_bound = 1000
            cobra_reaction.upper_bound = upper_bound

        # add reaction
        reactions.append(cobra_reaction)

        # parse equation
        stoichiometry = defaultdict(lambda: 0)
        for (
            sref
        ) in (
            reaction.getListOfReactants()
        ):  # noqa: E501 type: rust_sbml.SpeciesReference
            sid = sref.id

            stoichiometry[sid] -= sref.getStoichiometry()

        for (
            sref
        ) in (
            reaction.getListOfProducts()
        ):  # noqa: E501 type: rust_sbml.SpeciesReference
            sid = sref.id

            stoichiometry[sid] += sref.getStoichiometry()

        # convert to metabolite objects
        object_stoichiometry = {}
        for met_id in stoichiometry:
            metabolite = cobra_model.metabolites.get_by_id(met_id)
            object_stoichiometry[metabolite] = stoichiometry[met_id]
        cobra_reaction.add_metabolites(object_stoichiometry)

    cobra_model.add_reactions(reactions)

    # Objective
    obj_direction = "max"
    coefficients = {}
    try:
        objective_reaction = cobra_model.reactions.get_by_id(
            "R_BIOMASS_Ecoli_core_w_GAM"
        )
    except KeyError:
        raise cobra.CobraSBMLError("Objective reaction not found")
    try:
        coefficients[objective_reaction] = 1.0
    except ValueError as e:
        print(f"problemwithcoeff: {e}")

    cobra.io.sbml.set_objective(cobra_model, coefficients)
    cobra_model.solver.objective.direction = obj_direction

    return cobra_model


def test_integration():
    model = sbml_to_model("examples/EcoliCore.xml")
    model.optimize()


def test_consistency():
    model = sbml_to_model("examples/EcoliCore.xml")
    res = model.slim_optimize()
    model = cobra.io.read_sbml_model("examples/EcoliCore.xml")
    expr = model.slim_optimize()
    assert round(res, 4) == round(expr, 4)