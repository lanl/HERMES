"""Print one section of the HERMES config: each field's type, default, limits
and meaning, read from the installed HERMES.

    pixi run python show_config_fields.py <section>
"""

from __future__ import annotations

import argparse
import json
import textwrap
import types
import typing

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from hermes.state.models.acquisition.serval import ServalAcquisitionConfig
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    HermesTpx3EventReconstruction,
    HermesTpx3PhotonReconstruction,
    Tpx3Unpacking,
)
from hermes.state.models.environment import DirectoryState, RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo

# Each section: where its fields go in the config file, and its model.
SECTIONS = {
    "measurement_info": ("measurement_info:", MeasurementInfo),
    "environment": ("environment:", RuntimeEnvironment),
    "acquisition": (
        "acquisition: (mode: serval, the default)\n  config:",
        ServalAcquisitionConfig,
    ),
    "analysis": ("analysis: (mode: hermes is required)", HermesTpx3AnalysisState),
    "unpacking": ("analysis:\n  unpacking:", Tpx3Unpacking),
    "photon_reconstruction": (
        "analysis:\n  photon_reconstruction:",
        HermesTpx3PhotonReconstruction,
    ),
    "event_reconstruction": (
        "analysis:\n  event_reconstruction:",
        HermesTpx3EventReconstruction,
    ),
}

# The analysis section names its stages without listing their fields; each
# stage is a section of its own.
STAGES = {
    model: name
    for name, (_, model) in SECTIONS.items()
    if name in ("unpacking", "photon_reconstruction", "event_reconstruction")
}

# Fields HERMES fills in while it runs; a config does not set them.
FILLED_IN_BY_HERMES = {"results"}

LIMITS = {
    "gt": "> {}",
    "ge": ">= {}",
    "lt": "< {}",
    "le": "<= {}",
    "min_length": "at least {} long",
    "max_length": "at most {} long",
    "pattern": "matches {}",
}


def type_text(annotation: object) -> str:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return type_text(args[0])
    if origin is typing.Literal:
        return " | ".join(json.dumps(value) for value in args)
    if origin in (typing.Union, types.UnionType):
        return " | ".join(type_text(arg) for arg in args)
    if origin is not None:
        return f"{origin.__name__}[{', '.join(type_text(arg) for arg in args)}]"
    if annotation is type(None):
        return "null"
    # A folder field takes a plain path.
    if annotation is DirectoryState:
        return "path"
    return getattr(annotation, "__name__", str(annotation))


def sub_model(annotation: object) -> type[BaseModel] | None:
    """The model a field holds, alone or with null; None for anything else."""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        others = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(others) != 1:
            return None
        annotation = others[0]
    if (
        isinstance(annotation, type)
        and issubclass(annotation, BaseModel)
        and annotation is not DirectoryState
    ):
        return annotation
    return None


def print_fields(model: type[BaseModel], indent: str) -> None:
    for name, field in model.model_fields.items():
        if name in FILLED_IN_BY_HERMES:
            continue
        notes = []
        if field.is_required():
            notes.append("required")
        elif field.default is not PydanticUndefined:
            notes.append(f"default {json.dumps(field.default, default=str)}")
        for limit in field.metadata:
            for key, text in LIMITS.items():
                value = getattr(limit, key, None)
                if value is not None:
                    notes.append(text.format(value))
        label = name if field.alias is None else f"{name} (or {field.alias})"
        line = f"{indent}{label}: {type_text(field.annotation)}"
        if notes:
            line += f" ({'; '.join(notes)})"
        print(line)
        if field.description:
            print(
                textwrap.fill(
                    field.description,
                    width=88,
                    initial_indent=indent + "    ",
                    subsequent_indent=indent + "    ",
                )
            )
        model_inside = sub_model(field.annotation)
        if model_inside in STAGES:
            stage = STAGES[model_inside]
            print(f"{indent}    Its fields: run this script with {stage}.")
        elif model_inside is not None:
            print_fields(model_inside, indent + "  ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("section", choices=SECTIONS)
    section = parser.parse_args().section
    where, model = SECTIONS[section]
    print(where)
    print_fields(model, "  " * (where.count("\n") + 1))


if __name__ == "__main__":
    main()
