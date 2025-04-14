from typing import Optional, List
from pydantic import BaseModel, Field


class RequestSchema(BaseModel):
    """Schema for the incoming request"""
    phone_number: str = Field(..., description="Phone number of the user")
    message: str = Field(..., description="Message from the user")
    twilio_signature: str = Field(..., description="Twilio signature for validation")
    timestamp: Optional[str] = Field(None, description="Timestamp of the request")


class ResponseSchema(BaseModel):
    """Schema for the outgoing response"""
    status: str = Field(..., description="Status of the request")
    message: str = Field(..., description="Response message")
    data: Optional[List[str]] = Field(None, description="Additional data if any")