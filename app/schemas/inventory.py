from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime
from typing import Any


# ─── CONDITION ────────────────────────────────────────────────────────────────
class PartConditionOut(BaseModel):
    id:          UUID
    name:        str
    description: str | None = None
    sort_order:  int = 0

    model_config = {"from_attributes": True}


# ─── MEDIA ────────────────────────────────────────────────────────────────────
class PartMediaOut(BaseModel):
    id:             UUID
    media_type:     str
    storage_path:   str
    thumbnail_path: str | None = None
    is_main:        bool = False
    sort_order:     int  = 0
    display_url:    str  = ""

    model_config = {"from_attributes": True}

    @field_validator("display_url", mode="before")
    @classmethod
    def set_display_url(cls, v, info):
        data = info.data
        return data.get("thumbnail_path") or data.get("storage_path") or ""

    @field_validator("media_type", mode="before")
    @classmethod
    def media_type_value(cls, v):
        return v.value if hasattr(v, "value") else v


# ─── PART LIST ITEM (vista galería/lista) ─────────────────────────────────────
class PartListItem(BaseModel):
    id:            UUID
    part_key:      str
    vehicle_id:    UUID
    branch_id:     UUID
    branch_name:   str = ""
    name:          str
    brand:         str
    model:         str
    year_from:     int | None = None
    year_to:       int | None = None
    condition:     str | None = None    # nombre de la condición
    status:        str
    sale_price:    float
    main_photo_url:str | None = None
    has_video:     bool = False
    vehicle_key:   str | None = None
    qr_url:        str | None = None

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def status_value(cls, v):
        return v.value if hasattr(v, "value") else v

    @field_validator("condition", mode="before")
    @classmethod
    def condition_name(cls, v):
        if v is None:
            return None
        return v.name if hasattr(v, "name") else str(v)


# ─── PART DETAIL (ficha completa) ─────────────────────────────────────────────
class PartDetail(BaseModel):
    id:             UUID
    part_key:       str
    vehicle_id:     UUID
    branch_id:      UUID
    branch_name:    str = ""
    name:           str
    brand:          str
    model:          str
    year_from:      int | None = None
    year_to:        int | None = None
    specifications: str | None = None
    observations:   str | None = None
    condition:      PartConditionOut | None = None
    status:         str
    sale_price:     float
    has_warranty:   bool = False
    warranty_days:  int | None = None
    media:          list[PartMediaOut] = []
    main_photo_url: str | None = None
    vehicle_key:    str | None = None
    qr_url:         str | None = None
    created_at:     datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def status_value(cls, v):
        return v.value if hasattr(v, "value") else v


# ─── PART CREATE ──────────────────────────────────────────────────────────────
class PartCreate(BaseModel):
    vehicle_id:     UUID
    branch_id:      UUID
    name:           str
    brand:          str
    model:          str
    year_from:      int | None = None
    year_to:        int | None = None
    specifications: str | None = None
    observations:   str | None = None
    condition_id:   UUID | None = None
    sale_price:     float
    has_warranty:   bool = False
    warranty_days:  int | None = None


# ─── PART UPDATE ──────────────────────────────────────────────────────────────
class PartUpdate(BaseModel):
    name:           str | None = None
    specifications: str | None = None
    observations:   str | None = None
    condition_id:   UUID | None = None
    sale_price:     float | None = None
    has_warranty:   bool | None = None
    warranty_days:  int | None = None


# ─── PAGINATED RESPONSE ───────────────────────────────────────────────────────
class PaginatedParts(BaseModel):
    total: int
    page:  int
    limit: int
    items: list[PartListItem]

class VehicleCreate(BaseModel):
    branch_id:         UUID
    brand:             str
    model:             str
    year:              int
    color:             str | None = None
    purchase_origin:   str        = "private"
    purchase_cost:     float      = 0.0
    purchase_date:     datetime   | None = None
    general_condition: str | None = None
    notes:             str | None = None
    seller_name:       str | None = None
    seller_phone:      str | None = None

class VehicleOut(BaseModel):
    id:           UUID
    vehicle_key:  str
    branch_id:    UUID
    brand:        str
    model:        str
    year:         int
    color:        str | None = None
    status:       str
    purchase_cost:float
    purchase_date:datetime
    notes:        str | None = None
    qr_url:       str | None = None
    created_at:   datetime

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def status_value(cls, v):
        return v.value if hasattr(v, "value") else v