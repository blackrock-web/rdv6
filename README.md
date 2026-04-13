---
title: RoadAI Enterprise
emoji: 🛣️
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# ROADAI v4.0 — Enterprise AI Road Analytics Platform 🛣️🤖

**ROADAI** is an advanced, full-stack intelligence platform designed for real-time road health monitoring, defect detection, and predictive maintenance. This repository is optimized for **Hugging Face Spaces** (Backend) and **Netlify** (Frontend).

## 🚀 Deployment Overview

### 1. Backend (Hugging Face Spaces)
- **SDK**: Docker
- **Port**: 7860
- **Environment Variables Needed**:
  - `MONGODB_URL`: Your MongoDB Atlas connection string.
  - `CORS_ORIGINS`: Set this to your Netlify URL (e.g., `https://your-app.netlify.app`).
  - `JWT_SECRET`: A secure string for authentication.

### 2. Frontend (Netlify)
- **Base Directory**: `frontend/`
- **Build Command**: `npm run build`
- **Publish Directory**: `frontend/dist/`
- **Environment Variables Needed**:
  - `VITE_API_BASE_URL`: Your Hugging Face Space URL (e.g., `https://user-space.hf.space`).

---

## 📂 Project Structure

```text
/RoadAI_HF_Netlify_Deployment
├── Dockerfile          # HF Optimized
├── README.md           # HF Metadata
├── backend/            # FastAPI Microservices
├── config/             # Configuration & Fallbacks
├── data/               # Static Data
├── database/           # DB Migrations (if any)
├── frontend/           # React 18 + Vite (Shadcn UI)
└── models/             # AI Weight Management
```

---

## 🛠️ Technology Stack
- **AI**: YOLOv8, DeepLabV3, MiDaS, XGBoost.
- **Backend**: Python 3.11, FastAPI, Motor.
- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS.
- **Database**: MongoDB Atlas.

Developed with ❤️ by the SNIGDHA & ROADAI Engineering Team.

