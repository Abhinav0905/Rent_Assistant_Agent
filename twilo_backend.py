# A backend for Twilio API 

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from twilio.rest import Client
from twilio.request_validator import RequestValidator
import os
import json
import logging
from dotenv import load_dotenv
from query_engine import query_agreement
from query_detection import QueryDetection
import uvicorn
import time
from datetime import datetime
import requests
from models import (
    MaintenanceTicketRequest, 
    MaintenanceTicketResponse,
    MaintenanceTicketDB,
    TicketCategory,
    TicketPriority,
    TicketStatus
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("twilio-backend")

app = FastAPI(
    title="Rental Agreement Assistant API",
    description="API for querying rental agreements via WhatsApp",
    version="1.0.0"
)
load_dotenv()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Twilio credentials
account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "your_account_sid")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "your_auth_token")
twilio_phone_number = os.environ.get("TWILIO_PHONE_NUMBER", "your_twilio_whatsapp_number")

# Initialize Twilio client
client = Client(account_sid, auth_token)
validator = RequestValidator(auth_token)

# Whitelist of approved phone numbers (your society members)
# Read from environment variable if available, otherwise use default
# APPROVED_NUMBERS_STR = os.environ.get("APPROVED_WHATSAPP_NUMBERS", "+1 510 954 9624")
# APPROVED_NUMBERS = [number.strip() for number in APPROVED_NUMBERS_STR.split(",")]


def normalize_phone_number(phone: str) -> str:
    """Normalize phone number to a standard format by removing spaces and prefixes"""
    # Remove any whatsapp: prefix
    phone = phone.replace("whatsapp:", "")
    # Remove all spaces
    phone = phone.replace(" ", "")
    # If number doesn't have country code but is US number (10 digits), add +1
    if len(phone) == 10 and phone.isdigit():
        phone = "+1" + phone
    # If number starts with 1 but no +, add +
    elif phone.startswith("1") and not phone.startswith("+"):
        phone = "+" + phone
    return phone


# Rate limiting
RATE_LIMIT = {}
MAX_REQUESTS = 10  # Maximum requests per time window
TIME_WINDOW = 60 * 10  # 10 minutes in seconds


def validate_twilio_request(request: Request):
    """Validate that the request is coming from Twilio"""
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    form_data = request.form()
    
    if not validator.validate(url, form_data, signature):
        logger.warning(f"Invalid Twilio signature from {request.client.host}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")


def check_rate_limit(phone_number: str):
    """Check if the user has exceeded rate limits"""
    current_time = time.time()
    
    # Clean up old entries
    for num in list(RATE_LIMIT.keys()):
        if current_time - RATE_LIMIT[num]["timestamp"] > TIME_WINDOW:
            del RATE_LIMIT[num]
    
    if phone_number not in RATE_LIMIT:
        RATE_LIMIT[phone_number] = {"count": 100, "timestamp": current_time}
        return
    
    if RATE_LIMIT[phone_number]["count"] >= MAX_REQUESTS:
        logger.warning(f"Rate limit exceeded for {phone_number}")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    RATE_LIMIT[phone_number]["count"] += 1


@app.get("/health")
async def health_check():
    """Health check endpoint to verify the service is running"""
    return {"status": "healthy", "service": "rental-agreement-assistant"}


# @app.get("/approved-numbers")
# async def get_approved_numbers():
#     """Return list of approved phone numbers (only for debugging)"""
#     return {"approved_numbers": APPROVED_NUMBERS}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming HTTP requests"""
    logger.info(f"Request received: {request.method} {request.url.path}")
    try:
        # Try to log form data for POST requests
        if request.method == "POST" and "application/x-www-form-urlencoded" in request.headers.get("content-type", ""):
            form = await request.form()
            request.state.form_data = form  # store form data for later reuse
            logger.info(f"Form data: {dict(form)}")
    except:
        pass
    response = await call_next(request)
    return response


@app.get("/debug")
async def debug():
    """Test endpoint to verify server is responding"""
    logger.info("Debug endpoint called")
    return {"status": "online", "time": time.time()}


def split_long_message(message: str, limit: int = 1500) -> list:
    """Split a long message into smaller chunks that fit Twilio's limit"""
    if len(message) <= limit:
        return [message]
        
    # Split on paragraph breaks first
    parts = []
    paragraphs = message.split('\n\n')
    current_part = ""
    
    for paragraph in paragraphs:
        if len(current_part) + len(paragraph) + 2 <= limit:
            current_part += (paragraph + '\n\n')
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = paragraph + '\n\n'
    
    if current_part:
        parts.append(current_part.strip())
    
    # Add part numbers if there are multiple parts
    if len(parts) > 1:
        parts = [f"Part {i+1}/{len(parts)}:\n{part}" for i, part in enumerate(parts)]
    
    return parts

async def process_maintenance_request(message: str, from_number: str, media_urls: list, ticket_data: dict) -> str:
    """Process a maintenance request and return the response message"""
    try:
        # Generate ticket ID
        ticket_id = f"MAINT-{int(datetime.now().timestamp())}"
        
        # Extract location and symptoms from ticket_data
        location = ticket_data.get("location", "Not specified")
        symptoms = ticket_data.get("symptoms", message)
        
        # Format a detailed description
        description = (
            f"Location: {location}\n"
            f"Reported Issue: {symptoms}"
        )
        
        # Convert category and priority
        try:
            category = TicketCategory(ticket_data.get("category", "other").lower())
            priority = TicketPriority(ticket_data.get("priority", "normal").lower())
        except ValueError:
            category = TicketCategory.OTHER
            priority = TicketPriority.NORMAL
        
        # Create the ticket request
        ticket_request = MaintenanceTicketRequest(
            description=description,
            tenant_phone=normalize_phone_number(from_number),
            category=category,
            priority=priority,
            apartment_number=ticket_data.get("apartment_number"),
            access_instructions=ticket_data.get("access_instructions"),
            has_images=bool(media_urls)
        )
        
        # Create database record
        db_record = MaintenanceTicketDB(
            **ticket_request.dict(),
            ticket_id=ticket_id,
            status=TicketStatus.NEW,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            image_paths=[]
        )
        
        # Process images if any
        if media_urls:
            image_paths = []
            os.makedirs("tickets/images", exist_ok=True)
            
            for i, url in enumerate(media_urls):
                try:
                    response = requests.get(url)
                    if response.status_code == 200:
                        image_filename = f"ticket_{ticket_id}_img_{i+1}.jpg"
                        image_path = f"tickets/images/{image_filename}"
                        
                        with open(image_path, 'wb') as f:
                            f.write(response.content)
                        
                        image_paths.append(image_path)
                        logger.info(f"Saved image: {image_path}")
                except Exception as e:
                    logger.error(f"Error saving image: {e}")
            
            db_record.image_paths = image_paths
        
        # Save ticket to database
        os.makedirs("tickets", exist_ok=True)
        with open(f"tickets/{ticket_id}.json", "w") as f:
            json.dump(db_record.dict(), f, indent=2, default=str)
        
        # Generate response message
        priority_emoji = {
            TicketPriority.EMERGENCY: "🚨",
            TicketPriority.HIGH: "⚠️",
            TicketPriority.NORMAL: "✅",
            TicketPriority.LOW: "ℹ️"
        }
        
        emoji = priority_emoji.get(priority, "✅")
        
        response_text = (
            f"{emoji} Maintenance Ticket #{ticket_id}\n\n"
            f"Your request has been received and assigned status: NEW\n\n"
            f"Category: {category.name.capitalize()}\n"
            f"Priority: {priority.name.capitalize()}\n\n"
            f"Details:\n{description}\n\n"
            f"Images Attached: {'Yes' if media_urls else 'No'}\n\n"
            f"We'll review your request and provide updates.\n"
            f"For status updates, text 'status #{ticket_id}'"
        )
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error processing maintenance request: {e}", exc_info=True)
        return "Sorry, there was an error processing your maintenance request. Please try again."


@app.post("/")
async def root_webhook(request: Request) -> PlainTextResponse:
    """Handle webhooks at the root path"""
    try:
        form_data = getattr(request.state, "form_data", None) or await request.form()
        form_dict = dict(form_data)
        
        message_body = form_dict.get("Body", "").strip()
        from_number = form_dict.get("From", "")
        
        logger.info(f"Processing message: '{message_body}' from {from_number}")
        
        # Extract media information
        num_media = int(form_dict.get("NumMedia", "0"))
        media_urls = []
        for i in range(num_media):
            if f"MediaUrl{i}" in form_dict:
                media_urls.append(form_dict[f"MediaUrl{i}"])
        
        normalized_from = normalize_phone_number(from_number)
        
        # Process the query and get response
        query_result = await QueryDetection.query(message_body)
        logger.info(f"Query result: {query_result}")
        
        # Handle maintenance requests
        if isinstance(query_result, dict) and query_result.get("intent") == "maintenance":
            response_text = await process_maintenance_request(
                message=message_body,
                from_number=normalized_from,
                media_urls=media_urls,
                ticket_data=query_result.get("ticket_data", {})
            )
        else:
            # Handle regular queries
            if isinstance(query_result, str):
                response_text = query_result
            elif isinstance(query_result, dict):
                response_text = query_result.get('answer', str(query_result))
            else:
                if hasattr(query_result, 'content'):
                    response_text = query_result.content
                elif hasattr(query_result, 'response'):
                    response_text = query_result.response
                else:
                    response_text = str(query_result)

        logger.info(f"Final response text: {response_text}")
        
        # Split long messages
        message_parts = split_long_message(response_text)
        
        # Format WhatsApp numbers
        whatsapp_to = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
        whatsapp_from = f"whatsapp:{twilio_phone_number}" if not twilio_phone_number.startswith("whatsapp:") else twilio_phone_number
        
        # Send each part
        last_message = None
        for part in message_parts:
            last_message = client.messages.create(
                body=part,
                from_=whatsapp_from,
                to=whatsapp_to
            )
            logger.info(f"Message part sent with SID: {last_message.sid}")
        
        return PlainTextResponse(response_text)
        
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return PlainTextResponse(error_msg, status_code=500)


if __name__ == "__main__":
    logger.info("Starting Rental Agreement Assistant Server...")   
    uvicorn.run("twilo_backend:app", host="0.0.0.0", port=8080, reload=True)