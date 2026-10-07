from datetime import datetime
from typing import Optional
import os, re
import httpx
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, String, DateTime, Text, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./buyerreach.db"
    HUNTER_API_KEY: str = ""
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "BuyerReach <onboarding@resend.dev>"
    APP_ORIGIN: str = "http://127.0.0.1:5173"
    class Config: env_file = ".env"

settings = Settings()
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase): pass
class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(50))
    website: Mapped[str] = mapped_column(String(300), default="")
    email: Mapped[str] = mapped_column(String(180), default="")
    phone: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(60), default="Demo")
    score: Mapped[int] = mapped_column(Integer, default=70)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
app = FastAPI(title="BuyerReach API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.APP_ORIGIN, "http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

def db():
    s = SessionLocal()
    try: yield s
    finally: s.close()

class SearchRequest(BaseModel):
    city: str = "New York"
    state: str = "NY"
    category: str = "home decor"
    radius: int = 15

class EmailRequest(BaseModel):
    lead_ids: list[int]
    subject: str
    body: str
    reply_to: Optional[EmailStr] = None

DEMO = [
    ("Hearth & Haven Studio", "Interior Design Studio", "New York", "NY", "hello@hearthhaven.example", "https://hearthhaven.example", 94),
    ("The Modern Nest", "Home Furnishing Store", "New York", "NY", "buyers@themodernnest.example", "https://themodernnest.example", 91),
    ("Cedar & Clay Collective", "Boutique Home Store", "Brooklyn", "NY", "contact@cedarclay.example", "https://cedarclay.example", 88),
    ("Lumen Living Co.", "Interior Design Studio", "Austin", "TX", "studio@lumenliving.example", "https://lumenliving.example", 86),
    ("Sage House Interiors", "Home Decor Retailer", "Chicago", "IL", "team@sagehouse.example", "https://sagehouse.example", 82),
    ("Woven Room", "Furniture & Decor", "Los Angeles", "CA", "info@wovenroom.example", "https://wovenroom.example", 79),
]

@app.get("/api/health")
def health(): return {"status": "ok", "mode": "live" if settings.HUNTER_API_KEY or settings.RESEND_API_KEY else "demo"}

@app.get("/api/stats")
def stats(s: Session = Depends(db)):
    leads = s.query(Lead).all()
    return {"total": len(leads), "verified": sum(x.verified for x in leads), "emails": sum(bool(x.email) for x in leads), "sent": 0}

@app.post("/api/search")
async def search(req: SearchRequest, s: Session = Depends(db)):
    # Overpass is intentionally best-effort; demo data keeps the interview project usable offline.
    found = []
    query = f'''[out:json][timeout:12];area["ISO3166-2"="US-{req.state}"]->.a;(nwr["shop"~"furniture|interior_decoration|houseware"](area.a);nwr["craft"="interior_decoration"](area.a););out center tags;'''
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            data = (await client.post("https://overpass-api.de/api/interpreter", content=query)).json()
        for item in data.get("elements", [])[:20]:
            tags = item.get("tags", {}); name = tags.get("name")
            if name: found.append((name, tags.get("shop", "Home decor business"), req.city, req.state, tags.get("email", ""), tags.get("website", ""), 72))
    except Exception: pass
    if not found: found = [x for x in DEMO if req.state == "NY" or x[3] == req.state] or DEMO
    created = []
    for name, cat, city, state, email, web, score in found:
        exists = s.query(Lead).filter(Lead.business_name == name).first()
        if exists: created.append(exists); continue
        lead = Lead(business_name=name, category=cat, city=city, state=state, email=email, website=web, score=score, verified=bool(email), source="Overpass" if email or web else "Demo")
        s.add(lead); created.append(lead)
    s.commit()
    return {"leads": [serialize(x) for x in created], "provider": "Overpass/OpenStreetMap" if found and found[0][0] not in [x[0] for x in DEMO] else "Demo fallback"}

@app.get("/api/leads")
def leads(s: Session = Depends(db)): return [serialize(x) for x in s.query(Lead).order_by(Lead.score.desc()).all()]

@app.post("/api/enrich/{lead_id}")
async def enrich(lead_id: int, s: Session = Depends(db)):
    lead = s.get(Lead, lead_id)
    if not lead: raise HTTPException(404, "Lead not found")
    if settings.HUNTER_API_KEY and lead.website:
        domain = re.sub(r"https?://(www\\.)?", "", lead.website).split("/")[0]
        async with httpx.AsyncClient(timeout=15) as client:
            data = (await client.get("https://api.hunter.io/v2/domain-search", params={"domain": domain, "api_key": settings.HUNTER_API_KEY})).json()
        emails = data.get("data", {}).get("emails", [])
        if emails: lead.email = emails[0].get("value", lead.email); lead.verified = True; lead.source = "Hunter"
    elif not lead.email: lead.email = f"hello@{lead.business_name.lower().replace(' ', '')}.example"
    lead.score = min(99, lead.score + 5); s.commit()
    return serialize(lead)

@app.post("/api/send")
async def send_email(req: EmailRequest, s: Session = Depends(db)):
    selected = s.query(Lead).filter(Lead.id.in_(req.lead_ids)).all(); recipients = [x.email for x in selected if x.email]
    if not recipients: raise HTTPException(400, "Selected leads have no email addresses")
    if settings.RESEND_API_KEY:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"}, json={"from": settings.RESEND_FROM_EMAIL, "to": recipients, "subject": req.subject, "html": req.body.replace("\n", "<br>")})
        if response.status_code >= 400: raise HTTPException(response.status_code, response.text)
        mode = "Resend"
    else: mode = "Demo preview (add RESEND_API_KEY to send)"
    return {"sent": len(recipients), "recipients": recipients, "provider": mode}

def serialize(x):
    return {"id": x.id, "business_name": x.business_name, "category": x.category, "city": x.city, "state": x.state, "website": x.website, "email": x.email, "phone": x.phone, "source": x.source, "score": x.score, "verified": x.verified}
