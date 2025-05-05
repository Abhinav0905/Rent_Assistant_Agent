from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class TicketCategory(str, Enum):
    """Categories for maintenance tickets based on your existing database schema"""
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    APPLIANCE = "appliance"
    STRUCTURAL = "structural"
    PEST = "pest"
    LOCKSMITH = "locksmith"
    CLEANING = "cleaning"
    OTHER = "other"


class TicketPriority(str, Enum):
    """Priority levels for tickets based on your existing database"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


class TicketStatus(str, Enum):
    """Status options for tickets in your system"""
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# INCOMING REQUEST SCHEMA
class MaintenanceTicketRequest(BaseModel):
    """Maps to your existing database fields for ticket creation"""
    description: str
    tenant_phone: str
    category: Optional[TicketCategory] = TicketCategory.OTHER
    priority: Optional[TicketPriority] = TicketPriority.NORMAL
    tenant_name: Optional[str] = None
    apartment_number: Optional[str] = None
    requested_date: Optional[datetime] = None
    access_instructions: Optional[str] = None
    has_images: bool = False
    
    class Config:
        """Configuration for the model"""
        use_enum_values = True


# DATABASE MODEL (matches your existing DB structure)
class MaintenanceTicketDB(MaintenanceTicketRequest):
    """Full database model that extends the request with system fields"""
    ticket_id: str
    status: TicketStatus = TicketStatus.NEW
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    estimated_completion: Optional[datetime] = None
    image_paths: List[str] = []
    notes: List[Dict[str, Any]] = []
    
    class Config:
        """Configuration for the model"""
        use_enum_values = True


# RESPONSE SCHEMA
class MaintenanceTicketResponse(BaseModel):
    """Response schema sent back to user"""
    ticket_id: str
    confirmation_message: str
    status: str
    created_at: datetime
    estimated_completion: Optional[datetime] = None
    next_steps: str
    
    class Config:
        """Configuration for the model"""
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }


# INTERNAL STATUS UPDATE MODEL
class TicketUpdateRequest(BaseModel):
    """Model for internal status updates"""
    status: TicketStatus
    note: Optional[str] = None
    assigned_to: Optional[str] = None
    estimated_completion: Optional[datetime] = None
    notify_tenant: bool = True
    
    class Config:
        """Configuration for the model"""
        use_enum_values = True