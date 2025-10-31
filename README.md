# Programmable Payment PoC

Streamlit demo + FastAPI backend ที่จำลอง programmable payment platform ตามแนวทางใน `Agents.md`

## โครงสร้าง

- `backend/` – FastAPI application + file-backed JSON datastore + rules engine
- `streamlit_app.py` – Streamlit UI สำหรับเดโม flow (create program, trigger transaction, manage checklist)
- `frontend/` – SvelteKit guided UI (มีคำแนะนำทีละขั้นและ error handling เชิงมนุษย์)
- `requirements.txt` – dependencies สำหรับ backend + frontend

## เริ่มต้นใช้งาน

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### รัน Backend

```bash
uvicorn backend.main:app --reload --port 8000
```

*Endpoint หลัก*:

- `GET /health`
- `GET/POST/PATCH/DELETE /api/programs`
- `GET/POST /api/transactions`
- `POST /api/transactions/{id}/cancel`
- `GET /api/transactions/{id}/checklist`
- `POST /api/checklist/{item_id}/complete|uncomplete`
- `GET /api/merchants`
- `GET/POST /api/users`

### รัน Streamlit UI

ในอีก terminal:

```bash
streamlit run streamlit_app.py
```

เมื่อเปิด UI:

1. Dashboard แสดง balances และสถานะธุรกรรม
2. Programs – ดู/สร้าง payment program พร้อม rules & checklist
3. Transactions – ยิงธุรกรรมเพื่อทดสอบ rules engine + escrow
4. Checklists – กด complete/undo เพื่อ trigger rule evaluation และ release เงิน

> ใน sidebar สามารถเปลี่ยน API base URL และ admin user ID ได้

### รัน SvelteKit Frontend

```bash
cd frontend
npm install
npm run dev -- --open
```

> หน้านี้มีคู่มือทีละขั้นสำหรับผู้ใช้ใหม่ สามารถเปลี่ยน API URL ได้จากส่วน “STEP 0” บนหน้าจอหลัก

## Seed Data

เมื่อ backend start จะมี

- Users: `user_a`, `user_b`, `user_c`, `gov_wallet`
- Merchants: m001–m004 (food, entertainment, medical, retail)
- Programs: Freelance Escrow, Government Stimulus

สามารถใช้ Streamlit UI เพื่อเพิ่ม users/programs/transactions เพิ่มเติมได้

## Access Control

- ทุกโปรแกรมมี `created_by` และ `allowed_users`
- เฉพาะผู้ที่อยู่ใน `allowed_users` เท่านั้นที่สร้างธุรกรรมผ่านโปรแกรมนั้นได้
- ลบโปรแกรมได้เฉพาะ `admin` (ผ่าน API `/api/programs/{id}?actor_id=admin`)

## Local Storage

- ข้อมูลทั้งหมดถูกเก็บไว้ในไฟล์ `data/store.json`
- ลบไฟล์ดังกล่าวเพื่อรีเซ็ตระบบเป็นค่าเริ่มต้น (จะ seed ใหม่ในครั้งถัดไปรัน backend)
- ไฟล์ถูก ignore จาก git เพื่อไม่ให้ข้อมูลเดโมหลุดขึ้น repo

## หมายเหตุ

- Datastore ใช้ไฟล์ JSON เดียวสำหรับ demo เพื่อความง่าย ไม่เหมาะกับ production
- Rule engine รองรับ amount limit, daily limit, category whitelist/blacklist, checklist enforcement และ mock external verification (always pass)
- ฟังก์ชัน release/settle funds ทำแบบง่าย ๆ ผ่าน balance ของผู้ใช้ใน datastore
