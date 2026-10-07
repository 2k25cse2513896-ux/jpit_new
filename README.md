# BuyerReach

BuyerReach is a polished full-stack internship project for US home decor sellers.
It discovers relevant buyer businesses, enriches public professional emails, and prepares/sends outreach campaigns.

## Stack

- React + Vite frontend
- FastAPI + SQLAlchemy backend
- PostgreSQL-ready database (SQLite is the zero-setup fallback)
- Overpass/OpenStreetMap buyer discovery
- Hunter Domain Search email enrichment
- Resend transactional email delivery

## One-command run

On Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\\start.ps1
```

The script creates the Python virtual environment, installs dependencies, starts FastAPI and the Vite UI, and opens the app.

Copy `backend/.env.example` to `backend/.env` and add API keys for live integrations. Without keys, the app runs in Demo mode with realistic seeded buyers.

## Production notes

Set `DATABASE_URL` to a PostgreSQL URL for deployment. The app uses a clear provider adapter boundary so additional lead providers can be added without changing the UI.
