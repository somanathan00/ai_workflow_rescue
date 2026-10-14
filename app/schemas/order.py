
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import OrderStatus


class OrderCreate(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=1000)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    product_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime



class OrderAcceptedResponse(BaseModel):
    order_id: UUID
    workflow_id: UUID
    status: OrderStatus
    message: str