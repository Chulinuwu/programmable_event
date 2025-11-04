from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
import streamlit as st


st.set_page_config(page_title="Programmable Payment PoC", layout="wide")


DEFAULT_API_BASE = "http://localhost:8000"


if "api_base" not in st.session_state:
    st.session_state.api_base = DEFAULT_API_BASE

if "admin_user" not in st.session_state:
    st.session_state.admin_user = "admin"


def api_request(method: str, path: str, **kwargs) -> Any:
    base_url = st.session_state.api_base.rstrip("/") + "/"
    url = urljoin(base_url, path.lstrip("/"))
    try:
        response = requests.request(method, url, timeout=10, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{response.status_code} {response.text}")
        if response.content:
            return response.json()
        return None
    except requests.RequestException as exc:
        raise RuntimeError(f"API request failed: {exc}") from exc


def load_users() -> List[Dict[str, Any]]:
    return api_request("GET", "/api/users")


def load_programs() -> List[Dict[str, Any]]:
    return api_request("GET", "/api/programs")


def load_merchants() -> List[Dict[str, Any]]:
    return api_request("GET", "/api/merchants")


def load_transactions() -> List[Dict[str, Any]]:
    return api_request("GET", "/api/transactions")


def create_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    return api_request("POST", "/api/users", json=payload)


def create_program(payload: Dict[str, Any]) -> Dict[str, Any]:
    return api_request("POST", "/api/programs", json=payload)


def create_transaction(payload: Dict[str, Any]) -> Dict[str, Any]:
    return api_request("POST", "/api/transactions", json=payload)


def complete_checklist(item_id: str, actor: str, user_id: str) -> Dict[str, Any]:
    return api_request(
        "POST",
        f"/api/checklist/{item_id}/complete",
        json={"actor": actor, "user_id": user_id},
    )


def uncomplete_checklist(item_id: str, actor: str, user_id: str) -> Dict[str, Any]:
    return api_request(
        "POST",
        f"/api/checklist/{item_id}/uncomplete",
        json={"actor": actor, "user_id": user_id},
    )


def cancel_transaction(transaction_id: str) -> Dict[str, Any]:
    return api_request("POST", f"/api/transactions/{transaction_id}/cancel", json={})


def render_api_error(err: Exception) -> None:
    message = str(err)
    detail_text = None
    if "{" in message:
        try:
            json_fragment = message[message.index("{") :]
            parsed = json.loads(json_fragment)
            if isinstance(parsed, dict):
                detail = parsed.get("detail")
                if isinstance(detail, (list, dict)):
                    detail_text = json.dumps(detail, ensure_ascii=False)
                elif detail:
                    detail_text = str(detail)
        except (ValueError, json.JSONDecodeError, TypeError):
            detail_text = None
    st.error(detail_text or message)





st.title("Programmable Payment PoC")
st.caption("สาธิต programmable payment พร้อม rules engine และ checklist enforcement")


try:
    users = load_users()
    programs = load_programs()
    merchants = load_merchants()
    transactions = load_transactions()
except Exception as err:  # noqa: BLE001
    render_api_error(err)
    st.stop()

programs_by_id = {program["id"]: program for program in programs}

program_templates = {
    "Government Stimulus": {
        "summary": "จำกัดการใช้เงินเยียวยากับหมวดอาหาร/การแพทย์ และจำกัดวงเงินต่อวัน",
        "name": "Government Stimulus",
        "program_description": "จำกัดการใช้จ่ายกับหมวด merchant ที่กำหนด",
        "max_amount": 500,
        "daily_limit": 3000,
        "allowed_categories": ["food", "medical", "retail"],
        "blocked_categories": ["entertainment", "gambling"],
        "require_checklist": False,
        "checklist": [],
        "allowed_users": ["gov_wallet", "user_a", "user_b", "user_c"],
        "created_by": "gov_wallet",
    },
    "Freelance Escrow": {
        "summary": "เก็บเงินไว้ใน escrow จนกว่าฟรีแลนซ์จะส่งงานครบทุกขั้น",
        "name": "Freelance Escrow",
        "program_description": "Escrow program สำหรับจ่ายงานฟรีแลนซ์แบบ milestone",
        "max_amount": 10000,
        "daily_limit": 0,
        "allowed_categories": ["services"],
        "blocked_categories": [],
        "require_checklist": True,
        "checklist": [
            "ส่ง mockup | receiver",
            "ส่งงานเสร็จ | receiver",
            "ผู้ว่าจ้างยืนยันงาน | sender",
        ],
        "allowed_users": ["user_a", "user_b"],
        "created_by": "user_a",
    },
    "Conditional Bonus": {
        "summary": "โบนัสพนักงานที่จ่ายเมื่อผ่าน checklist (เช่น ยอดขาย, attendance)",
        "name": "Conditional Bonus",
        "program_description": "โปรแกรมโบนัสที่ต้องได้รับการยืนยันตามเงื่อนไขก่อนโอน",
        "max_amount": 0,
        "daily_limit": 0,
        "allowed_categories": ["payroll"],
        "blocked_categories": [],
        "require_checklist": True,
        "checklist": [
            "ทีมขายยืนยันยอดถึงเป้า | admin",
            "HR ตรวจสอบสถานะการทำงาน | admin",
            "CFO อนุมัติการจ่าย | admin",
        ],
        "allowed_users": ["admin"],
        "created_by": "admin",
    },
}

category_options = sorted({m["category"] for m in merchants if m.get("category")})
template_category_pool = {
    category
    for template in program_templates.values()
    for category in [*(template["allowed_categories"] or []), *(template["blocked_categories"] or [])]
    if category
}
category_options = sorted(set(category_options) | template_category_pool)

user_id_to_label = {user["id"]: f"{user['display_name']} ({user['id']})" for user in users}
user_id_list = list(user_id_to_label.keys())

if "program_form_initialized" not in st.session_state:
    st.session_state.program_name = ""
    st.session_state.program_description = ""
    st.session_state.program_max_amount = 0
    st.session_state.program_daily_limit = 0
    st.session_state.program_allowed_categories = []
    st.session_state.program_blocked_categories = []
    st.session_state.program_require_checklist = False
    st.session_state.program_checklist_text = "ส่งใบเสร็จ | receiver\nยืนยันโดยผู้จ่าย | sender"
    st.session_state.program_template_choice = "(none)"
    st.session_state.program_allowed_users = []
    st.session_state.program_created_by = user_id_list[0] if user_id_list else "admin"
    st.session_state.program_form_initialized = True

if st.session_state.program_created_by not in st.session_state.program_allowed_users:
    st.session_state.program_allowed_users.append(st.session_state.program_created_by)
st.session_state.program_allowed_users = list(dict.fromkeys(st.session_state.program_allowed_users))


tab_dashboard, tab_programs, tab_transactions, tab_checklists = st.tabs(
    ["Dashboard", "Programs", "Transactions", "Checklists"]
)

# ----------------------- Dashboard -----------------------------------------
with tab_dashboard:
    st.markdown(
        """
        #### วิธีใช้งาน PoC แบบเร็ว

        1. ตรวจยอดคงเหลือของผู้ใช้ด้านล่างเพื่อเลือกกระเป๋าที่จะใช้ทดลอง
        2. ไปที่แท็บ `Programs` เพื่อดูหรือสร้างกฎใหม่ (amount limit, checklist ฯลฯ)
        3. ที่แท็บ `Transactions` เลือกโปรแกรม + ผู้จ่าย/ผู้รับ แล้วกด `Create transaction`
        4. ธุรกรรมที่ติดสถานะ `HELD` ต้องกลับมาที่แท็บ `Checklists` เพื่อกด `Complete`
        5. เมื่อ checklist ครบ ระบบจะปล่อยเงินและสถานะเปลี่ยนเป็น `COMPLETED`

        _Tip: สามารถกดปุ่ม “Reload data” ใน sidebar เพื่อดึงข้อมูลล่าสุดหลังแก้ไขจาก API ภายนอก_
        """
    )
    st.subheader("User Balances")
    if users:
        st.dataframe(
            [{"User ID": u["id"], "Name": u["display_name"], "Balance": u["balance"]} for u in users],
            hide_index=True,
            column_config={"Balance": st.column_config.NumberColumn("Balance", format="฿%d")},
        )
    else:
        st.info("ยังไม่มีผู้ใช้งานในระบบ")

    st.subheader("Recent Transactions")
    if transactions:
        table_rows = []
        for txn in sorted(transactions, key=lambda t: t["created_at"], reverse=True):
            table_rows.append(
                {
                    "Transaction": txn["id"],
                    "Program": txn["program_id"],
                    "From": txn["from_user"],
                    "To": txn["to_user"],
                    "Amount": txn["amount"],
                    "Status": txn["status"],
                    "Checklist Done": sum(1 for item in txn["checklist"] if item["is_completed"]),
                    "Checklist Total": len(txn["checklist"]),
                    "Created": txn["created_at"],
                }
            )
        st.dataframe(table_rows, hide_index=True)
    else:
        st.info("ยังไม่มีรายการธุรกรรม")


# ----------------------- Programs ------------------------------------------
with tab_programs:
    st.subheader("Existing Programs")
    if programs:
        for program in programs:
            with st.expander(f"{program['name']} ({program['id']})", expanded=False):
                st.write(program.get("description") or "-")
                owner_label = user_id_to_label.get(program.get("created_by"), program.get("created_by", "-"))
                allowed_labels = [
                    user_id_to_label.get(uid, uid) for uid in program.get("allowed_users", []) if uid
                ]
                allowed_display = ", ".join(allowed_labels) if allowed_labels else "ทุก user"
                st.caption(f"Owner: {owner_label} • Allowed users: {allowed_display}")
                st.json(program["rules"])
    else:
        st.info("ยังไม่มีโปรแกรม")

    st.divider()
    st.subheader("Create New Program")
    category_hint = ", ".join(category_options) if category_options else "ยังไม่มีหมวดในระบบ (เพิ่ม merchant ก่อน)"
    st.markdown(
        f"""
        สร้าง programmable payment rule ใหม่เพื่อควบคุมธุรกรรม:

        - **Program name / Description**: ตั้งชื่อและบอก context เพื่อให้ทีมอื่นเข้าใจว่า rules นี้ใช้กับ flow อะไร
        - **Max amount per transaction**: เพดานเงินต่อครั้ง ป้องกันการรูดเกินวงเงินหรือใช้ผิดประเภท (เช่น รัฐแจกเงิน 500 ต่อครั้ง)
        - **Daily limit**: กำหนดยอดรวมที่ใช้ได้ต่อวัน เช่น จำกัด 3,000 บาท/วันสำหรับโครงการกระตุ้นเศรษฐกิจ
        - **Program owner / Allowed users**: เลือกเจ้าของโปรแกรมและกำหนดว่าใครบ้างที่ยิงธุรกรรมได้ (อย่าลืมใส่ทั้งผู้โอนและผู้รับที่เกี่ยวข้อง)
        - **Allowed categories**: เลือกหมวด merchant ที่อนุญาต (ระบบรู้จัก: `{category_hint}`)
        - **Blocked categories**: หมวดที่ห้ามใช้ (จะถูก reject ทันที)
        - **Require checklist**: ติ๊กแล้วจะสร้าง workflow ให้ฝ่ายที่เกี่ยวข้องมากดรับรองก่อนปล่อยเงิน (เหมาะกับ escrow หรืองานที่ต้องตรวจรับ)
        - **Checklist**: ใส่ทีละบรรทัดในรูปแบบ `รายละเอียด | actor` โดย actor คือ `sender`, `receiver`, หรือ `admin`
        """
    )

    template_choice = st.selectbox(
        "เลือก template สำหรับเติมข้อมูลอัตโนมัติ",
        ["(none)"] + list(program_templates.keys()),
        key="program_template_choice",
    )
    if template_choice and template_choice != "(none)":
        template_meta = program_templates[template_choice]
        st.info(f"Template: {template_meta['summary']}")
        if st.button("Apply template values", key="apply_program_template"):
            st.session_state.program_name = template_meta["name"]
            st.session_state.program_description = template_meta["program_description"]
            st.session_state.program_max_amount = template_meta["max_amount"] or 0
            st.session_state.program_daily_limit = template_meta["daily_limit"] or 0
            st.session_state.program_allowed_categories = list(template_meta["allowed_categories"])
            st.session_state.program_blocked_categories = list(template_meta["blocked_categories"])
            st.session_state.program_require_checklist = template_meta["require_checklist"]
            st.session_state.program_checklist_text = "\n".join(template_meta["checklist"]) if template_meta["checklist"] else ""
            st.session_state.program_allowed_users = list(
                dict.fromkeys(template_meta.get("allowed_users", []))
            )
            st.session_state.program_created_by = template_meta.get("created_by", st.session_state.program_created_by)
            st.experimental_rerun()

    with st.form("create_program_form"):
        program_name = st.text_input("Program name", key="program_name")
        program_description = st.text_area("Description", height=60, key="program_description")
        col1, col2 = st.columns(2)
        with col1:
            max_amount = st.number_input(
                "Max amount per transaction (บาท)",
                min_value=0,
                value=st.session_state.program_max_amount,
                step=100,
                key="program_max_amount",
            )
            daily_limit = st.number_input(
                "Daily limit (บาท)",
                min_value=0,
                value=st.session_state.program_daily_limit,
                step=100,
                key="program_daily_limit",
            )
        with col2:
            allowed_categories = st.multiselect(
                "Allowed categories (เลือกได้หลายหมวด)",
                options=category_options,
                default=st.session_state.program_allowed_categories,
                key="program_allowed_categories",
            )
            blocked_categories = st.multiselect(
                "Blocked categories (หมวดที่ห้าม)",
                options=category_options,
                default=st.session_state.program_blocked_categories,
                key="program_blocked_categories",
            )

        st.caption("Tip: หมวดหมู่ต้องตรงกับ category ของ merchant (ดูรายชื่อได้จากแท็บ Dashboard → Merchants)")

        require_checklist = st.checkbox(
            "Require checklist before settlement",
            value=st.session_state.program_require_checklist,
            key="program_require_checklist",
        )
        checklist_text = st.text_area(
            "Checklist (ใช้รูปแบบ: คำอธิบาย | actor)",
            key="program_checklist_text",
            height=100,
            placeholder="ตัวอย่าง: ส่งใบเสร็จ | receiver",
        )
        preview_rows = []
        for line in checklist_text.splitlines():
            if "|" not in line:
                continue
            description, actor = [part.strip() for part in line.split("|", 1)]
            preview_rows.append({"รายละเอียด": description, "Actor": actor})
        if preview_rows:
            st.caption("Checklist preview (ระบบจะสร้างรายการตามนี้)")
            st.table(preview_rows)

        if user_id_list:
            created_by = st.selectbox(
                "Program owner (คนสร้างโปรแกรมนี้)",
                options=user_id_list,
                format_func=lambda uid: user_id_to_label.get(uid, uid),
                key="program_created_by",
            )
            if st.session_state.program_created_by not in st.session_state.program_allowed_users:
                st.session_state.program_allowed_users.append(st.session_state.program_created_by)
            st.session_state.program_allowed_users = list(dict.fromkeys(st.session_state.program_allowed_users))
            allowed_user_values = [
                uid for uid in st.session_state.program_allowed_users if uid in user_id_to_label
            ]
            st.multiselect(
                "Allowed users (ผู้ที่ใช้โปรแกรมนี้ได้)",
                options=user_id_list,
                default=allowed_user_values,
                format_func=lambda uid: user_id_to_label.get(uid, uid),
                key="program_allowed_users",
            )
            st.caption("เพิ่ม user id ของผู้จ่าย ผู้รับ และ admin/approver ที่เกี่ยวข้อง เพื่อไม่ให้ธุรกรรมโดนปฏิเสธ")
        else:
            created_by = "admin"
            st.session_state.program_allowed_users = list(dict.fromkeys(st.session_state.program_allowed_users))

        submitted = st.form_submit_button("Create program")
        if submitted:
            try:
                max_amount_value = int(max_amount) if max_amount else None
                daily_limit_value = int(daily_limit) if daily_limit else None
                selected_allowed_users = list(dict.fromkeys(st.session_state.program_allowed_users))
                created_by = st.session_state.program_created_by if user_id_list else created_by
                if created_by not in selected_allowed_users:
                    selected_allowed_users.append(created_by)
                rules: Dict[str, Any] = {
                    "max_amount": max_amount_value,
                    "daily_limit": daily_limit_value,
                    "allowed_categories": allowed_categories,
                    "blocked_categories": blocked_categories,
                    "require_checklist": require_checklist,
                    "require_external_verification": False,
                }

                checklist_items: List[Dict[str, str]] = []
                if require_checklist:
                    for line in checklist_text.splitlines():
                        if not line.strip():
                            continue
                        try:
                            description, actor = [part.strip() for part in line.split("|", 1)]
                        except ValueError as exc:  # noqa: PERF203
                            raise RuntimeError(
                                f"Checklist format ผิด: '{line}'. ใช้รูปแบบ 'description | sender/receiver/admin'"
                            ) from exc
                        actor_lower = actor.lower()
                        if actor_lower not in {"sender", "receiver", "admin"}:
                            raise RuntimeError(f"actor '{actor_lower}' ไม่ถูกต้อง (sender/receiver/admin)")
                        checklist_items.append({"description": description, "required_by": actor_lower})
                    rules["checklist_template"] = checklist_items

                payload = {
                    "name": program_name,
                    "description": program_description,
                    "rules": rules,
                    "allowed_users": selected_allowed_users,
                    "created_by": created_by,
                }
                create_program(payload)
                st.success("สร้างโปรแกรมสำเร็จ")
                st.experimental_rerun()
            except Exception as err:  # noqa: BLE001
                render_api_error(err)


# ----------------------- Transactions --------------------------------------
with tab_transactions:
    st.subheader("Create Transaction")
    last_txn_feedback = st.session_state.pop("last_txn_feedback", None)
    if last_txn_feedback:
        st.success(f"สร้างธุรกรรมสำเร็จ (status: {last_txn_feedback['status']})")
        st.json(last_txn_feedback)
        if last_txn_feedback["status"] == "HELD":
            st.warning("สถานะ HELD: ไปที่แท็บ Checklists เพื่อกดยืนยันให้ครบทุกข้อ")
        elif last_txn_feedback["status"] == "REJECTED":
            st.error("สถานะ REJECTED: ตรวจสอบ amount/category/daily limit หรือ rule อื่น แล้วลองใหม่")
    st.markdown(
        """
        #### ขั้นตอนสร้างธุรกรรม

        1. เลือกโปรแกรมที่ต้องการใช้ (ดูให้แน่ใจว่า allowed users มีทั้งผู้จ่ายและผู้รับที่ต้องการ)
        2. เลือกผู้จ่าย (`From`) และผู้รับ (`To`) – ต้องเป็นคนที่อยู่ใน allow list ของโปรแกรม
        3. เลือก merchant ให้ตรงกับหมวดหมู่ที่ rule อนุญาต แล้วระบุจำนวนเงิน
        4. กด `Create transaction` เพื่อลองยิงธุรกรรม
        5. เช็คผลลัพธ์: ถ้าสถานะเป็น `HELD` ให้ไปที่แท็บ **Checklists** เพื่อกด Complete ขั้นตอนต่าง ๆ

        _สถานะที่เป็นไปได้_: `HELD` (รอ checklist), `COMPLETED`, `REJECTED` (ไม่ผ่าน rule), `CANCELLED`
        """
    )
    with st.form("create_transaction_form"):
        if not programs:
            st.warning("ยังไม่มีโปรแกรม ต้องสร้างก่อน")
        program_options = {f"{p['name']} ({p['id'][:6]})": p["id"] for p in programs}
        program_choice = st.selectbox("Program", list(program_options.keys())) if program_options else None
        user_options = {f"{u['display_name']} ({u['id']})": u["id"] for u in users}
        from_choice = st.selectbox("จาก (ผู้จ่าย)", list(user_options.keys())) if user_options else None
        to_choice = st.selectbox("ถึง (ผู้รับ)", list(user_options.keys())) if user_options else None
        amount = st.number_input("จำนวนเงิน", min_value=1, value=500)
        merchant_options = {f"{m['name']} ({m['category']})": m["id"] for m in merchants}
        merchant_choice = st.selectbox("Merchant", ["(none)"] + list(merchant_options.keys()))
        note = st.text_input("หมายเหตุ (optional)")

        if program_choice:
            selected_program_id = program_options[program_choice]
            selected_program = programs_by_id.get(selected_program_id)
            if selected_program:
                rules_meta = selected_program.get("rules", {}) or {}
                allowed_users_hint = selected_program.get("allowed_users", []) or []
                allowed_display = (
                    ", ".join(user_id_to_label.get(uid, uid) for uid in allowed_users_hint)
                    if allowed_users_hint
                    else "ทุก user"
                )
                allowed_categories_hint = rules_meta.get("allowed_categories") or ["ทั้งหมด"]
                blocked_categories_hint = rules_meta.get("blocked_categories") or []
                allowed_categories_display = ", ".join(allowed_categories_hint)
                blocked_categories_display = ", ".join(blocked_categories_hint) if blocked_categories_hint else "-"
                require_checklist_hint = rules_meta.get("require_checklist")
                st.caption(
                    f"สิทธิ์การใช้โปรแกรม: {allowed_display} • Allowed categories: {allowed_categories_display} • "
                    f"Blocked: {blocked_categories_display} • Checklist required: {'ใช่' if require_checklist_hint else 'ไม่ต้อง'}"
                )
                if require_checklist_hint:
                    st.caption("หลังยิงธุรกรรมแล้วอย่าลืมไปที่แท็บ Checklists เพื่อ complete ทุกรายการให้ครบ")

        st.caption("Note: ผู้จ่าย/ผู้รับต้องอยู่ใน allow list ของโปรแกรม ไม่งั้นระบบจะปฏิเสธอัตโนมัติ")

        submitted_txn = st.form_submit_button("Create transaction")
        if submitted_txn:
            if not program_choice or not from_choice or not to_choice:
                st.warning("กรุณาเลือก program, ผู้จ่าย และผู้รับ")
            else:
                try:
                    payload = {
                        "program_id": program_options[program_choice],
                        "from_user": user_options[from_choice],
                        "to_user": user_options[to_choice],
                        "amount": amount,
                        "note": note or None,
                    }
                    if merchant_choice and merchant_choice != "(none)":
                        payload["merchant_id"] = merchant_options[merchant_choice]
                    result = create_transaction(payload)
                    st.session_state["last_txn_feedback"] = result
                    st.experimental_rerun()
                except Exception as err:  # noqa: BLE001
                    render_api_error(err)

    st.divider()
    st.subheader("Transactions")
    if transactions:
        for txn in sorted(transactions, key=lambda t: t["created_at"], reverse=True):
            with st.expander(f"{txn['id']} • {txn['status']} • ฿{txn['amount']}", expanded=False):
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.write(f"Program: `{txn['program_id']}`")
                    st.write(f"From: `{txn['from_user']}` → `{txn['to_user']}`")
                with col_b:
                    if txn.get("merchant_id"):
                        st.write(f"Merchant: `{txn['merchant_id']}` ({txn.get('merchant_category','?')})")
                    st.write(f"Created: {txn['created_at']}")
                    st.write(f"Updated: {txn['updated_at']}")
                with col_c:
                    st.write(f"Checklist: {sum(1 for item in txn['checklist'] if item['is_completed'])} / {len(txn['checklist'])}")
                    if txn["status"] not in {"COMPLETED", "CANCELLED", "REJECTED"}:
                        if st.button("Cancel transaction", key=f"cancel_{txn['id']}"):
                            try:
                                cancel_transaction(txn["id"])
                                st.experimental_rerun()
                            except Exception as err:  # noqa: BLE001
                                render_api_error(err)
    else:
        st.info("ยังไม่มีธุรกรรม")


# ----------------------- Checklists ----------------------------------------
with tab_checklists:
    st.subheader("Checklist Progress")
    st.markdown(
        """
        #### วิธีจัดการ Checklist

        1. เลือกธุรกรรมที่สถานะเป็น `HELD` หรือยังไม่ปล่อยเงิน
        2. ดูว่าแต่ละรายการต้องการ actor ใด (`sender` = ผู้จ่าย, `receiver` = ผู้รับ, `admin` = เจ้าหน้าที่)
        3. คลิก `Complete` เพื่อยืนยันเมื่อขั้นตอนนั้นสำเร็จแล้ว ระบบจะ re-evaluate rule ให้อัตโนมัติ
        4. ถ้ายังไม่ครบทุกข้อ ระบบจะยังถือเงินไว้ (สถานะ `HELD`)
        5. สามารถกด `Undo` ได้ก่อนที่ธุรกรรมจะ settle หากต้องการให้กลับไปตรวจสอบใหม่

        _Tip: ดูรายละเอียดรายการ checklist เพิ่มเติมได้จาก Transaction expander ในแท็บ Transactions_
        """
    )
    if not transactions:
        st.info("ยังไม่มีธุรกรรม")
    else:
        txn_map = {f"{t['id']} • {t['status']}": t for t in transactions}
        selected_key = st.selectbox("เลือกธุรกรรม", list(txn_map.keys()))
        selected_txn = txn_map[selected_key]
        st.write(
            f"Program `{selected_txn['program_id']}` • "
            f"From `{selected_txn['from_user']}` → `{selected_txn['to_user']}` • "
            f"Amount ฿{selected_txn['amount']}"
        )

        if not selected_txn["checklist"]:
            st.info("ธุรกรรมนี้ไม่ต้องการ checklist")
        else:
            for item in selected_txn["checklist"]:
                container = st.container()
                cols = container.columns([4, 2, 2, 2])
                with cols[0]:
                    st.write(item["description"])
                with cols[1]:
                    st.write(f"Required: `{item['required_by']}`")
                with cols[2]:
                    status_label = "✅ Done" if item["is_completed"] else "⏳ Pending"
                    st.write(status_label)
                with cols[3]:
                    if not item["is_completed"]:
                        if st.button(
                            "Complete",
                            key=f"complete_btn_{item['id']}",
                        ):
                            actor = item["required_by"]
                            user_id = (
                                selected_txn["from_user"]
                                if actor == "sender"
                                else selected_txn["to_user"]
                                if actor == "receiver"
                                else st.session_state.admin_user
                            )
                            try:
                                complete_checklist(item["id"], actor, user_id)
                                st.experimental_rerun()
                            except Exception as err:  # noqa: BLE001
                                render_api_error(err)
                    else:
                        if st.button(
                            "Undo",
                            key=f"uncomplete_btn_{item['id']}",
                        ):
                            actor = item["required_by"]
                            user_id = (
                                selected_txn["from_user"]
                                if actor == "sender"
                                else selected_txn["to_user"]
                                if actor == "receiver"
                                else st.session_state.admin_user
                            )
                            try:
                                uncomplete_checklist(item["id"], actor, user_id)
                                st.experimental_rerun()
                            except Exception as err:  # noqa: BLE001
                                render_api_error(err)
