# Programmable Payment Frontend (SvelteKit)

หน้าเว็บ SvelteKit สำหรับเดโม programmable payment โดยออกแบบให้ผู้ใช้มือใหม่ที่สุดก็ทำตามได้ทีละขั้น

## ไฮไลต์

- แท็บ Onboarding → Programs → Transactions → Checklists → Reference พร้อมคำอธิบายที่จำง่าย
- เทมเพลตโปรแกรมยอดนิยม เติมค่าลงฟอร์มอัตโนมัติแล้วปรับต่อได้ทันที
- แบบฟอร์มมีคำแนะนำทุกฟิลด์ พร้อมพรีวิว checklist และข้อความ error ที่อ่านง่าย
- หน้า Transactions แสดงผลลัพธ์ล่าสุด บอกขั้นตอนถัดไป (เช่น ไปแท็บ Checklists เมื่อสถานะ HELD)
- แสดงผู้ที่ได้รับสิทธิ์ใช้งานโปรแกรมและ whitelist/blacklist ชัดเจน ลดโอกาสยิงพลาด

## เริ่มใช้งาน

```bash
cd frontend
npm install
npm run dev -- --open
```

> อย่าลืมรัน FastAPI backend (`uvicorn backend.main:app --reload`) ก่อน เพื่อให้ UI ดึงข้อมูลได้

### ขั้นตอนเดโม 4 สเต็ป (15 นาที)

1. **Onboarding** – ดู users/merchants ที่ seed ไว้และอ่าน flow คร่าว ๆ
2. **Programs** – เลือกเทมเพลตหรือสร้างโปรแกรมใหม่ (ระบบบอกว่าแต่ละฟิลด์ทำเพื่ออะไร)
3. **Transactions** – เลือกโปรแกรม + ผู้จ่าย/ผู้รับ + merchant แล้วยิงธุรกรรม
4. **Checklists** – ถ้าธุรกรรมถูก HOLD ให้มากด Complete ทีละข้อ เพื่อปล่อยเงินไปยังผู้รับ

แท็บ Reference จะรวบรวมวิธีแก้ error ที่พบบ่อย เช่น user ไม่มีสิทธิ์หรือหมวดไม่ตรง whitelist

## โครงสร้างสำคัญ

- `src/routes/+page.svelte` – UI หลักพร้อมคำอธิบายทีละขั้นและเมนูนำทาง
- `src/lib/api.ts` – ฟังก์ชันเรียก FastAPI และจัดการ error message ให้อ่านง่าย
- `src/lib/types.ts` – type ที่ตรงกับ backend เพื่อให้โค้ดอ่านเข้าใจ
- `src/app.css` – ธีม / card / banner ที่ช่วยให้ผู้ใช้เห็นขั้นตอนถัดไปชัดเจน

## เคล็ดลับเพิ่มเติม

- หากเพิ่ม users/merchants/โปรแกรมใหม่ผ่าน API ให้กดปุ่ม “เชื่อมต่อและโหลดข้อมูล” เพื่อ refresh
- ลบไฟล์ `data/store.json` และรีสตาร์ท backend หากอยากรีเซ็ตสถานะทั้งหมด
- ถ้าเจอ error 403 หรือ REJECT UI จะอธิบายให้ว่าเกิดจากอะไร เช่น ผู้ใช้ไม่อยู่ใน allowed list หรือหมวดไม่ตรง whitelist

สนุกกับการเดโม programmable payment ได้เลย ✨
