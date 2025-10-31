# Programmable Payment PoC - สรุปสถาปัตยกรรมและแนวทาง

## ภาพรวมโครงการ

**เป้าหมาย**: R&D PoC สำหรับระบบ programmable payment ที่อนุญาตให้ควบคุมการไหลของเงินด้วย rules และ checklist

**Use Cases หลัก**:
- เงินเยียวยาจากรัฐ (จำกัดใช้ได้เฉพาะประเภทสินค้า)
- Escrow payment สำหรับ freelance (จ่ายเมื่องานเสร็จ)
- Conditional transfer (โอนเงินตามเงื่อนไข)

---

## สถาปัตยกรรมระบบ

### High-Level Architecture

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│  Client App  │────────▶│  Backend API     │────────▶│  PostgreSQL  │
│  (Web/Mobile)│         │  (FastAPI/NestJS)│         │              │
└──────────────┘         └──────────────────┘         └──────────────┘
                                  │
                                  ├─ Rules Engine (in-memory)
                                  ├─ Event Handler
                                  └─ Mock Payment Processor
```

### ตำแหน่งของ เรา ในระบบจริง

```
User A → Bank A → [เรา + Rules Engine] → Bank B → User B
                         ↑
                  Verify & Enforce ตรงนี้
```

---



---

## Rules Engine

### สิ่งที่ Rule Layer ตรวจได้เอง

#### 1. Transaction Metadata
```python
# ข้อมูลที่อยู่ใน transaction
{
    "amount": 500,
    "merchant_category": "food",
    "merchant_id": "m001",
    "timestamp": "2025-10-31T10:00:00Z"
}

# ตรวจได้ทันที
✓ Amount limit
✓ Merchant category whitelist/blacklist
✓ Time-based restrictions
```

#### 2. Historical Data
```python
# Query จาก database
✓ Daily spending limit
✓ Transaction frequency
✓ Pattern detection
```

#### 3. Checklist State
```python
# State ที่เก็บไว้
✓ Checklist ครบหรือยัง
✓ ใครเป็นคน complete
✓ Timeline ของการ complete
```

### สิ่งที่ Rule Layer ตรวจไม่ได้เอง (ต้องพึ่งภายนอก)

```python
❌ สินค้าถูกส่งจริงไหม → ต้องมี proof หรือ logistics API
❌ Merchant ถูกต้องตาม category ไหม → ต้องมี registry
❌ External events (ฝนตก, อุณหภูมิ) → ต้องมี oracle/API
```

---

## Rule Engine Implementation

### Core Logic

```python
class RuleEngine:
    def verify(self, transaction, rules):
        """Main verification logic แบ่งเป็น 3 ระดับ"""
        
        # Level 1: Self-verifiable (ไม่ต้องรอใคร)
        if not self._check_basic_rules(transaction, rules):
            return "REJECT"
        
        # Level 2: Need user input (รอ checklist)
        if not self._check_checklist(transaction):
            return "HOLD"
        
        # Level 3: External verification (optional)
        if rules.get("require_external_verification"):
            if not self._check_external(transaction):
                return "HOLD"
        
        return "APPROVE"
    
    def _check_basic_rules(self, txn, rules):
        """ตรวจได้ทันที"""
        # Amount limit
        if txn.amount > rules.get("max_amount", float('inf')):
            return False
        
        # Category whitelist
        allowed = rules.get("allowed_categories", [])
        if allowed and txn.merchant_category not in allowed:
            return False
        
        # Daily limit
        daily_total = self._get_daily_total(txn.from_user)
        if daily_total + txn.amount > rules.get("daily_limit", float('inf')):
            return False
        
        return True
    
    def _check_checklist(self, txn):
        """ตรวจว่า user complete ครบหรือยัง"""
        items = db.get_checklist_items(txn.id)
        return all(item.is_completed for item in items)
    
    def _check_external(self, txn):
        """Mock external verification"""
        # ใน PoC สามารถ mock ได้
        return True
```

### Rules Format (JSONB)

```json
{
    "allowed_categories": ["food", "medical", "retail"],
    "blocked_categories": ["entertainment", "gambling"],
    "max_amount": 500,
    "daily_limit": 3000,
    "require_checklist": true,
    "checklist_template": [
        {
            "description": "ส่งใบเสร็จ",
            "required_by": "receiver"
        },
        {
            "description": "ยืนยันการรับสินค้า",
            "required_by": "sender"
        }
    ],
    "require_external_verification": false
}
```

---

## Transaction Flow

### Scenario: Escrow Payment

```
1. User A สร้าง payment program
   POST /api/programs
   {
       "name": "จ้างทำเว็บไซต์",
       "rules": {
           "max_amount": 10000,
           "checklist_template": [
               {"description": "ส่ง mockup", "required_by": "receiver"},
               {"description": "ส่งงานเสร็จ", "required_by": "receiver"},
               {"description": "ทดสอบและยืนยัน", "required_by": "sender"}
           ]
       }
   }

2. User A สร้าง transaction
   POST /api/transactions
   {
       "program_id": "xxx",
       "to_user": "user_b",
       "amount": 10000
   }
   
   → Rule Engine ตรวจ:
      ✓ amount ไม่เกิน max_amount
      ✗ checklist ยังไม่ครบ
   → Status: HELD (เงินค้างใน escrow)

3. User B กดส่ง mockup
   POST /api/checklist/{item_id}/complete
   
   → Update checklist[0] = completed
   → Re-evaluate rules
   → Status: ยัง HELD (ยังขาด 2 items)

4. User B กดส่งงานเสร็จ
   → Update checklist[1] = completed
   → Status: ยัง HELD (ยังขาด 1 item)

5. User A ทดสอบและกดยืนยัน
   → Update checklist[2] = completed
   → Rule Engine ตรวจ:
      ✓ ทุกอย่าง pass
   → Status: COMPLETED
   → เงินไหลจาก User A → User B
```

---

## Mock Components สำหรับ PoC

### 1. Mock Merchant Registry

```python
class MockMerchantRegistry:
    """จำลองว่า เรา มีข้อมูล merchant จริง"""
    MERCHANTS = {
        "m001": {"category": "food", "name": "ร้านส้มตำป้าแดง"},
        "m002": {"category": "entertainment", "name": "ผับริมทาง"},
        "m003": {"category": "medical", "name": "โรงพยาบาลกรุงเทพ"},
        "m004": {"category": "retail", "name": "7-Eleven"},
    }
    
    @classmethod
    def get_category(cls, merchant_id):
        return cls.MERCHANTS.get(merchant_id, {}).get("category")
    
    @classmethod
    def is_valid(cls, merchant_id):
        return merchant_id in cls.MERCHANTS
```

### 2. Mock External Verifiers (Optional)

```python
class MockLogisticsAPI:
    """จำลอง webhook จาก logistics"""
    @staticmethod
    def verify_delivery(tracking_id):
        return {
            "delivered": True,
            "timestamp": "2025-10-31T14:30:00Z",
            "signature": "base64_signature"
        }

class MockWeatherAPI:
    """จำลอง external condition"""
    @staticmethod
    def check_condition(location):
        import random
        return {"rain": random.choice([True, False])}
```

---

## API Endpoints

### Programs

```
POST   /api/programs              # สร้าง payment program
GET    /api/programs              # ดู programs ทั้งหมด
GET    /api/programs/{id}         # ดูรายละเอียด program
PATCH  /api/programs/{id}         # แก้ไข rules
DELETE /api/programs/{id}         # ลบ program
```

### Transactions

```
POST   /api/transactions          # สร้าง transaction
GET    /api/transactions          # ดู transactions
GET    /api/transactions/{id}     # ดูรายละเอียด
POST   /api/transactions/{id}/cancel  # ยกเลิก
```

### Checklist

```
GET    /api/transactions/{id}/checklist      # ดู checklist
POST   /api/checklist/{item_id}/complete     # Complete item
POST   /api/checklist/{item_id}/uncomplete   # Undo complete
```

### Merchants (Mock)

```
GET    /api/merchants             # ดู merchant registry
GET    /api/merchants/{id}        # ดูข้อมูล merchant
```

---

## Trust Model & Verification Levels

### ระดับการ Verify

| Level | สิ่งที่ตรวจ | วิธีการ | Complexity |
|-------|------------|---------|------------|
| **Basic** | Amount, category, checklist | Self-verification + user confirm | ⭐ |
| **Moderate** | + Mock external API | Webhook simulation | ⭐⭐ |
| **Advanced** | + Real verification | AI/Blockchain/Oracle | ⭐⭐⭐⭐⭐ |

### สำหรับ PoC แนะนำ: Basic → Moderate

**Basic** (เริ่มต้น):
- Amount limits
- Category whitelist/blacklist
- User-confirmed checklist
- Mock merchant registry

**Moderate** (ถ้ามีเวลา):
- Mock webhook endpoints
- Simulated external verifiers
- Admin approval flow

---

## Trust Assumptions

### ใน PoC นี้เรา assume:

✓ **Backend เป็นผู้ตัดสิน** (centralized)
✓ **Merchant registry ถูกต้อง** (mock data)
✓ **User honest เมื่อ complete checklist** (no fraud detection)
✓ **เงินเป็น mock balance** (ไม่ใช่เงินจริง)

### ในระบบจริง (เรา) จะมี:

✓ Merchant verified by banks
✓ Transaction at payment rail layer
✓ Multi-party approval
✓ Audit trail & dispute resolution
✓ Regulatory compliance (BOT)

---

## Implementation Roadmap

### Phase 1: Core (สัปดาห์ที่ 1)
- [ ] Database schema
- [ ] User & balance management
- [ ] Basic rules engine
- [ ] Transaction CRUD

### Phase 2: Rules & Checklist (สัปดาห์ที่ 2)
- [ ] Rule evaluation logic
- [ ] Checklist management
- [ ] Transaction state machine
- [ ] Escrow mechanism

### Phase 3: UI & Demo (สัปดาห์ที่ 3)
- [ ] Web UI for users
- [ ] Create payment program flow
- [ ] Transaction visualization
- [ ] Checklist interface

### Phase 4: Polish (สัปดาห์ที่ 4)
- [ ] Audit logging
- [ ] Mock external verifiers
- [ ] Demo scenarios
- [ ] Documentation

---

## Demo Scenarios

### Scenario 1: Government Stimulus
```
รัฐแจกเงิน 3,000 บาท
Rules:
- ใช้ได้แค่ merchant category: food, medical, retail
- ไม่ใช้ได้กับ: entertainment, gambling
- จำกัด 500 บาท/ครั้ง
- จำกัด 3,000 บาท/วัน
```

### Scenario 2: Freelance Escrow
```
A จ้าง B ทำเว็บ 10,000 บาท
Checklist:
- B ส่ง mockup
- B ส่งงานเสร็จ
- A ทดสอบและยืนยัน
→ เมื่อครบ เงินไหลไป B
```

### Scenario 3: Conditional Transfer
```
บริษัทจ่ายโบนัส
Rules:
- ถ้ายอดขาย > target → โบนัส 20%
- ถ้ามาทำงานครบ → โบนัส +5%
- ถ้าไม่มีหนี้ค้าง → โอนเต็ม
```

---


### 🎯 Focus Points
1. แสดงให้เห็นว่า rules เป็น dynamic
2. แสดงว่า verification ทำงานยังไง
3. แสดงว่า เรา position มี advantage อะไร
4. ให้ user ลองเล่นได้จริง (multi-user)

## สรุป

นี่คือ PoC ที่ **realistic** แต่ไม่ **overcomplicated**

**Core Value Proposition**:
> "เรา สามารถทำ programmable payment ได้จริง เพราะอยู่ที่ payment rail layer และมี merchant data"

**Key Differentiator**:
- Enforcement ที่ payment layer (ไม่ใช่แค่ software)
- Trust model ที่พึ่ง existing infrastructure (banks)
- Dynamic rules without smart contract overhead

**Success Criteria**:
- มี user 2+ คนเล่นได้พร้อมกัน
- แสดง programmable payment concept ชัดเจน
- Demo ได้ใน 10-15 นาที
- Stakeholder เข้าใจ value proposition

