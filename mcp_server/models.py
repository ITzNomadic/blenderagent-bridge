"""Data models and Pydantic schemas for BlenderAgent Bridge MCP Server."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional context or diagnostics")


class ResponseEnvelope(BaseModel):
    status: Literal["success", "error"] = Field(..., description="Outcome of the operation")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Payload data returned by the operation")
    error: Optional[ErrorDetail] = Field(default=None, description="Error information if status is 'error'")
    message: str = Field(..., description="Summary status message")
    request_id: Optional[str] = Field(default=None, description="Traceability request ID")


# --- Input Parameter Schemas ---

class CreatePrimitiveInput(BaseModel):
    type: Literal["cube", "sphere", "cylinder", "plane", "cone", "torus", "monkey"] = Field(
        ..., description="Supported 3D primitive mesh type"
    )
    name: Optional[str] = Field(default=None, description="Optional custom name for the created object")
    location: Optional[List[float]] = Field(
        default=[0.0, 0.0, 0.0], description="[x, y, z] 3D coordinates in meters"
    )
    scale: Optional[List[float]] = Field(
        default=[1.0, 1.0, 1.0], description="[sx, sy, sz] scaling factors"
    )

    @field_validator("location", "scale")
    @classmethod
    def validate_3d_vector(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 3:
            raise ValueError("Vector must have exactly 3 float coordinates [x, y, z].")
        return v


class TransformObjectInput(BaseModel):
    name: str = Field(..., description="Name of the object to transform")
    location: Optional[List[float]] = Field(
        default=None, description="New [x, y, z] coordinates in meters"
    )
    rotation: Optional[List[float]] = Field(
        default=None, description="New [rx, ry, rz] Euler rotation angles in DEGREES"
    )
    scale: Optional[List[float]] = Field(
        default=None, description="New [sx, sy, sz] scale factors"
    )

    @field_validator("location", "rotation", "scale")
    @classmethod
    def validate_3d_transform(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 3:
            raise ValueError("Transform vector must contain exactly 3 floats.")
        return v


class SetMaterialInput(BaseModel):
    name: str = Field(..., description="Target object name to receive the material")
    color: List[float] = Field(
        ..., description="RGB or RGBA normalized floats [0.0 - 1.0], e.g. [0.1, 0.4, 0.9]"
    )
    metallic: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Metallic reflectance factor [0.0 = dielectric, 1.0 = metal]"
    )
    roughness: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Surface roughness [0.0 = mirror-smooth, 1.0 = diffuse-rough]"
    )
    material_name: Optional[str] = Field(
        default=None, description="Optional custom identifier for the material"
    )

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: List[float]) -> List[float]:
        if len(v) not in (3, 4):
            raise ValueError("Color must be a list of 3 (RGB) or 4 (RGBA) floats.")
        for c in v:
            if not (0.0 <= c <= 1.0):
                raise ValueError("Color components must be in normalized range [0.0, 1.0].")
        return v


class SetCameraInput(BaseModel):
    location: Optional[List[float]] = Field(
        default=None, description="Camera [x, y, z] position in meters"
    )
    rotation: Optional[List[float]] = Field(
        default=None, description="Camera [rx, ry, rz] Euler rotation angles in DEGREES"
    )
    camera_name: Optional[str] = Field(default="Camera", description="Name of the camera object")
    focal_length: Optional[float] = Field(
        default=50.0, ge=1.0, le=500.0, description="Lens focal length in millimeters"
    )
    make_active: Optional[bool] = Field(default=True, description="Whether to make this the active scene camera")


class RenderPreviewInput(BaseModel):
    width: Optional[int] = Field(
        default=640, ge=64, le=4096, description="Output image width in pixels"
    )
    height: Optional[int] = Field(
        default=480, ge=64, le=4096, description="Output image height in pixels"
    )
    samples: Optional[int] = Field(
        default=32, ge=1, le=512, description="Render sampling count"
    )
    output_filename: Optional[str] = Field(
        default="renders/preview.png", description="Relative path within workspace (PNG or JPG)"
    )


class SaveProjectInput(BaseModel):
    filename: str = Field(..., description="Target .blend filename relative to authorized workspace")
    overwrite: Optional[bool] = Field(
        default=False, description="Must be true to overwrite an existing .blend file"
    )
