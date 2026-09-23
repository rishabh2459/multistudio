"""Shared base class for all data-model types."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base model for every persisted/exchanged type.

    * ``extra="forbid"``: unknown fields are an error, so typos never pass silently.
    * ``validate_assignment``: mutations are validated too.
    * ``json_schema_serialization_defaults_required``: in the exported schema, fields
      with defaults are still marked required, because serialized output always
      contains them. This gives the TypeScript side non-optional types.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_schema_serialization_defaults_required=True,
    )
