<script lang="ts">
	import { onMount } from 'svelte';
	import {
		cancelTransaction,
		completeChecklistItem,
		createProgram,
		createTransaction,
		fetchChecklist,
		fetchMerchants,
		fetchPrograms,
		fetchTransactions,
		fetchUsers,
		getApiBase,
		setApiBase,
		undoChecklistItem
	} from '$lib/api';
	import type {
		ChecklistActor,
		ChecklistItem,
		Merchant,
		Program,
		ProgramCreatePayload,
		Transaction,
		TransactionCreatePayload,
		User
	} from '$lib/types';

	const TABS = ['Onboarding', 'Programs', 'Transactions', 'Checklists', 'Reference'] as const;
	type Tab = (typeof TABS)[number];

	const programTemplates: Array<{
		id: string;
		name: string;
		summary: string;
		details: string;
		payload: ProgramCreatePayload;
	}> = [
		{
			id: 'stimulus',
			name: 'Government Stimulus (จำกัดหมวดและวงเงิน)',
			summary:
				'แจกเงินสวัสดิการที่ใช้ได้เฉพาะหมวดอาหาร/การแพทย์/ค้าปลีก จำกัด 500 ต่อครั้ง และ 3,000 ต่อวัน',
			details:
				'เหมาะกับสวัสดิการรัฐหรือองค์กรที่ต้องการควบคุมหมวดการใช้จ่ายให้ชัดเจน พร้อมเพดานรายวัน',
			payload: {
				name: 'Government Stimulus',
				description: 'จำกัดการใช้วงเงินเยียวยาตามหมวดหมู่และเพดานต่อวัน',
				created_by: 'gov_wallet',
				allowed_users: ['gov_wallet', 'user_a', 'user_b', 'user_c'],
				rules: {
					max_amount: 500,
					daily_limit: 3000,
					allowed_categories: ['food', 'medical', 'retail'],
					blocked_categories: ['entertainment', 'gambling'],
					require_checklist: false,
					require_external_verification: false,
					checklist_template: []
				}
			}
		},
		{
			id: 'escrow',
			name: 'Freelance Escrow (จ่ายเมื่อส่งงานครบ)',
			summary: 'จ่ายค่าจ้างฟรีแลนซ์เมื่อผ่าน milestone ตาม checklist ที่กำหนด',
			details: 'ใช้กับงานที่ต้องมีการรับส่งหลายขั้น เช่น mockup → ส่งงานจริง → ผู้ว่าจ้างตรวจรับ',
			payload: {
				name: 'Freelance Escrow',
				description: 'เก็บเงินไว้ใน escrow แล้วปล่อยเมื่อ checklist ครบทุกข้อ',
				created_by: 'user_a',
				allowed_users: ['user_a', 'user_b'],
				rules: {
					max_amount: 10000,
					daily_limit: null,
					allowed_categories: ['services'],
					blocked_categories: [],
					require_checklist: true,
					require_external_verification: false,
					checklist_template: [
						{ description: 'ฟรีแลนซ์ส่ง mockup', required_by: 'receiver' },
						{ description: 'ฟรีแลนซ์ส่งงานสมบูรณ์', required_by: 'receiver' },
						{ description: 'ผู้ว่าจ้างตรวจรับแล้ว', required_by: 'sender' }
					]
				}
			}
		},
		{
			id: 'bonus',
			name: 'Conditional Bonus (ต้องให้ฝ่ายอื่นอนุมัติ)',
			summary: 'โบนัสพนักงานที่ต้องผ่านทีมขาย HR และ CFO ก่อนโอน',
			details: 'สำหรับองค์กรที่ต้องการ multi-approval ก่อนปล่อยโบนัสหรือ incentive',
			payload: {
				name: 'Conditional Bonus',
				description: 'โบนัสพนักงานที่ต้องได้รับการ approve หลายฝ่าย',
				created_by: 'admin',
				allowed_users: ['admin'],
				rules: {
					max_amount: null,
					daily_limit: null,
					allowed_categories: ['payroll'],
					blocked_categories: [],
					require_checklist: true,
					require_external_verification: false,
					checklist_template: [
						{ description: 'ทีมขายยืนยันยอดถึงเป้า', required_by: 'admin' },
						{ description: 'HR ตรวจสอบสถานะการทำงาน', required_by: 'admin' },
						{ description: 'CFO อนุมัติการจ่าย', required_by: 'admin' }
					]
				}
			}
		}
	];

	let activeTab: Tab = 'Onboarding';
	let apiInput = getApiBase();
	let isConnecting = false;
	let loadError = '';
	let successMessage = '';

	let users: User[] = [];
	let merchants: Merchant[] = [];
	let programs: Program[] = [];
	let transactions: Transaction[] = [];
	let checklists: Record<string, ChecklistItem[]> = {};

	let isLoading = false;
	let isSubmittingProgram = false;
	let isSubmittingTransaction = false;
	let isChecklistBusy = false;

	let programForm = {
		name: '',
		description: '',
		created_by: '',
		allowed_users: [] as string[],
		allowedCategories: [] as string[],
		blockedCategories: [] as string[],
		maxAmount: 0,
		dailyLimit: 0,
		requireChecklist: false,
		checklistText: '',
		requireExternalVerification: false
	};

	let transactionForm = {
		programId: '',
		fromUser: '',
		toUser: '',
		amount: 500,
		merchantId: '',
		note: ''
	};

	let checklistSelection = {
		transactionId: '',
		actor: 'receiver' as ChecklistActor
	};

	let lastTransactionFeedback: Transaction | null = null;

	let programsMap: Record<string, Program> = {};
	let selectedProgram: Program | undefined;
	let categoryOptions: string[] = [];
	let checklistPreview: Array<{ description: string; required_by: ChecklistActor }> = [];
	let checklistPreviewError = '';

	$: programsMap = Object.fromEntries(programs.map((program) => [program.id, program]));
	$: selectedProgram = programsMap[transactionForm.programId];
	$: categoryOptions = Array.from(new Set(merchants.map((merchant) => merchant.category))).sort();
	$: {
		if (programForm.requireChecklist) {
			try {
				checklistPreview = toChecklistTemplate(programForm.checklistText);
				checklistPreviewError = '';
			} catch (error) {
				checklistPreview = [];
				checklistPreviewError =
					error instanceof Error ? error.message : 'Checklist format ผิด กรุณาตรวจสอบ';
			}
		} else {
			checklistPreview = [];
			checklistPreviewError = '';
		}
	}
	$: {
		if (programForm.created_by && !programForm.allowed_users.includes(programForm.created_by)) {
			programForm.allowed_users = [...programForm.allowed_users, programForm.created_by];
		}
	}

	function resetProgramForm(partial?: Partial<typeof programForm>) {
		programForm = {
			name: '',
			description: '',
			created_by: users[0]?.id ?? '',
			allowed_users: users.slice(0, 2).map((u) => u.id),
			allowedCategories: [],
			blockedCategories: [],
			maxAmount: 0,
			dailyLimit: 0,
			requireChecklist: false,
			checklistText: '',
			requireExternalVerification: false,
			...partial
		};
	}

	function resetTransactionForm() {
		transactionForm = {
			programId: programs[0]?.id ?? '',
			fromUser: users[0]?.id ?? '',
			toUser: users[1]?.id ?? users[0]?.id ?? '',
			amount: 500,
			merchantId: merchants[0]?.id ?? '',
			note: ''
		};
	}

	async function connectApi() {
		isConnecting = true;
		loadError = '';
		successMessage = '';
		setApiBase(apiInput);
		await loadEverything();
		isConnecting = false;
		successMessage = 'เชื่อมต่อ backend สำเร็จและโหลดข้อมูลล่าสุดแล้ว';
	}

	async function loadEverything(showSpinner = true) {
		loadError = '';
		if (showSpinner) {
			isLoading = true;
		}
		try {
			const [fetchedUsers, fetchedMerchants, fetchedPrograms, fetchedTransactions] =
				await Promise.all([fetchUsers(), fetchMerchants(), fetchPrograms(), fetchTransactions()]);

			users = fetchedUsers;
			merchants = fetchedMerchants;
			programs = fetchedPrograms;
			transactions = fetchedTransactions;
			checklists = {};

			resetProgramForm();
			resetTransactionForm();
			if (transactions.length > 0) {
				checklistSelection.transactionId = transactions[0].id;
			}
		} catch (error) {
			loadError =
				error instanceof Error
					? error.message
					: 'เกิดข้อผิดพลาดในการโหลดข้อมูล ลองเชื่อมต่อใหม่อีกครั้ง';
		} finally {
			isLoading = false;
		}
	}

	onMount(async () => {
		await loadEverything();
	});

	function applyTemplate(templateId: string) {
		const template = programTemplates.find((item) => item.id === templateId);
		if (!template) return;
		const { payload } = template;
		const checkText = (payload.rules.checklist_template ?? [])
			.map((item) => `${item.description} | ${item.required_by}`)
			.join('\n');
		resetProgramForm({
			name: payload.name,
			description: payload.description ?? '',
			created_by: payload.created_by,
			allowed_users: payload.allowed_users,
			allowedCategories: payload.rules.allowed_categories ?? [],
			blockedCategories: payload.rules.blocked_categories ?? [],
			maxAmount: payload.rules.max_amount ?? 0,
			dailyLimit: payload.rules.daily_limit ?? 0,
			requireChecklist: payload.rules.require_checklist ?? false,
			requireExternalVerification: payload.rules.require_external_verification ?? false,
			checklistText: checkText
		});
		successMessage = `เทมเพลต "${template.name}" ถูกเติมลงแบบฟอร์มแล้ว ตรวจสอบและกดสร้างโปรแกรมได้เลย`;
	}

	function toChecklistTemplate(text: string): Array<{ description: string; required_by: ChecklistActor }> {
		return text
			.split('\n')
			.map((line) => line.trim())
			.filter(Boolean)
			.map((line) => {
				const [description, actorRaw] = line.split('|').map((part) => part?.trim());
				if (!description || !actorRaw) {
					throw new Error('รูปแบบ checklist ต้องเป็น "รายละเอียด | actor" เช่น "ส่งใบเสร็จ | receiver"');
				}
				const actor = actorRaw.toLowerCase() as ChecklistActor;
				if (!['sender', 'receiver', 'admin'].includes(actor)) {
					throw new Error(`พบ actor "${actorRaw}" ที่ไม่รองรับ (ต้องเป็น sender/receiver/admin)`);
				}
				return { description, required_by: actor };
			});
	}

	async function handleCreateProgram() {
		isSubmittingProgram = true;
		loadError = '';
		successMessage = '';
		try {
			if (!programForm.name) {
				throw new Error('กรุณาใส่ชื่อโปรแกรม');
			}
			if (!programForm.created_by) {
				throw new Error('กรุณาเลือก Program owner');
			}
			const allowedUsers = Array.from(new Set(programForm.allowed_users)).filter(Boolean);
			if (!allowedUsers.includes(programForm.created_by)) {
				allowedUsers.push(programForm.created_by);
			}
			if (allowedUsers.length < 2) {
				successMessage =
					'เตือน: มีผู้ใช้น้อยกว่า 2 คนใน allowed list คุณอาจต้องเพิ่มทั้งผู้จ่ายและผู้รับเพื่อทดสอบธุรกรรม';
			}
			const payload: ProgramCreatePayload = {
				name: programForm.name,
				description: programForm.description,
				created_by: programForm.created_by,
				allowed_users: allowedUsers,
				rules: {
					allowed_categories: programForm.allowedCategories,
					blocked_categories: programForm.blockedCategories,
					max_amount: programForm.maxAmount || null,
					daily_limit: programForm.dailyLimit || null,
					require_checklist: programForm.requireChecklist,
					require_external_verification: programForm.requireExternalVerification,
					checklist_template: programForm.requireChecklist
						? toChecklistTemplate(programForm.checklistText)
						: []
				}
			};
			await createProgram(payload);
			successMessage = 'สร้างโปรแกรมสำเร็จ ✅ ระบบจะโหลดข้อมูลล่าสุดให้อัตโนมัติ';
			await loadEverything(false);
			activeTab = 'Programs';
		} catch (error) {
			loadError =
				error instanceof Error
					? error.message
					: 'ไม่สามารถสร้างโปรแกรมได้ กรุณาตรวจสอบข้อมูลอีกครั้ง';
		} finally {
			isSubmittingProgram = false;
		}
	}

	async function handleCreateTransaction() {
		isSubmittingTransaction = true;
		loadError = '';
		successMessage = '';
		try {
			if (!transactionForm.programId) throw new Error('กรุณาเลือกโปรแกรม');
			if (!transactionForm.fromUser || !transactionForm.toUser) {
				throw new Error('กรุณาเลือกผู้จ่ายและผู้รับ');
			}
			const payload: TransactionCreatePayload = {
				program_id: transactionForm.programId,
				from_user: transactionForm.fromUser,
				to_user: transactionForm.toUser,
				amount: transactionForm.amount,
				merchant_id: transactionForm.merchantId || null,
				note: transactionForm.note || null
			};
			const txn = await createTransaction(payload);
			lastTransactionFeedback = txn;
			successMessage =
				txn.status === 'HELD'
					? 'ธุรกรรมถูกถือไว้รอ checklist ✅ ไปที่แท็บ Checklists แล้วกดยืนยันทีละข้อ'
					: txn.status === 'COMPLETED'
						? 'ธุรกรรมผ่านทุกเงื่อนไขและเงินถูกปล่อยแล้ว ✅'
						: `สร้างธุรกรรมแล้ว สถานะ: ${txn.status}`;
			await loadEverything(false);
			transactions = await fetchTransactions();
			if (txn.status === 'HELD') {
				checklistSelection.transactionId = txn.id;
				activeTab = 'Checklists';
			} else {
				activeTab = 'Transactions';
			}
		} catch (error) {
			loadError =
				error instanceof Error
					? error.message
					: 'ไม่สามารถสร้างธุรกรรมได้ กรุณาตรวจสอบข้อมูลอีกครั้ง';
		} finally {
			isSubmittingTransaction = false;
		}
	}

	function getChecklistActorUser(txn: Transaction, actor: ChecklistActor): string {
		if (actor === 'sender') return txn.from_user;
		if (actor === 'receiver') return txn.to_user;
		return 'admin';
	}

	async function handleChecklistAction(item: ChecklistItem, action: 'complete' | 'undo') {
		isChecklistBusy = true;
		loadError = '';
		successMessage = '';
		try {
			const txn = transactions.find((t) => t.id === item.transaction_id);
			if (!txn) {
				throw new Error('ไม่พบบันทึกธุรกรรม');
			}
			const actorId = getChecklistActorUser(txn, item.required_by);
			const payload = { actor: item.required_by, user_id: actorId };
			const updated =
				action === 'complete'
					? await completeChecklistItem(item.id, payload)
					: await undoChecklistItem(item.id, payload);
			successMessage =
				action === 'complete'
					? 'บันทึกว่า checklist ข้อนี้เสร็จแล้ว ✅'
					: 'Checklist ถูกย้อนกลับเพื่อให้ตรวจใหม่ ✋';
			await loadEverything(false);
			transactions = await fetchTransactions();
			if (updated.status === 'COMPLETED') {
				successMessage = 'ครบทุก checklist แล้ว 🎉 เงินถูกปล่อยไปยังผู้รับเรียบร้อย';
			}
			checklists[item.transaction_id] = await fetchChecklist(item.transaction_id);
		} catch (error) {
			loadError = error instanceof Error ? error.message : 'ทำรายการ checklist ไม่สำเร็จ';
		} finally {
			isChecklistBusy = false;
		}
	}

	async function ensureChecklist(transactionId: string) {
		if (checklists[transactionId]) return;
		try {
			checklists[transactionId] = await fetchChecklist(transactionId);
		} catch (error) {
			loadError =
				error instanceof Error ? error.message : 'ไม่สามารถดึง checklist ได้ กรุณาลองใหม่';
		}
	}

	$: if (checklistSelection.transactionId) {
		ensureChecklist(checklistSelection.transactionId);
	}

	const getUserLabel = (id: string) => users.find((u) => u.id === id)?.display_name ?? id;
</script>

<main class="page-shell stack">
    <header class="card hero-card stack">
		<div class="pill">Programmable Payment Playground</div>
		<h1>Programmable Payment Control Center</h1>
		<p style="margin: 0; font-size: 1rem; color: rgba(16, 36, 63, 0.8); max-width: 760px;">
			คู่มือนี้ออกแบบให้คนที่ไม่เคยใช้ระบบ programmable payment ก็ทำเดโมได้ภายในไม่กี่นาที
			แค่ทำตามขั้นตอนทีละข้อ: เชื่อมต่อ API → เลือกเทมเพลต → ยิงธุรกรรม → กดยืนยัน checklist
			ระบบจะบอกทุกก้าวว่าต้องกดอะไรต่อ
		</p>
		<div class="grid two">
			<div class="card stack" style="background: linear-gradient(135deg, #eff6ff, #ffffff);">
				<h3>STEP 0 · เชื่อมต่อ backend</h3>
				<p style="margin: 0; font-size: 0.95rem;">
					ตรวจสอบว่า FastAPI backend รันอยู่ที่ <code>http://localhost:8000</code> (หรือ URL อื่น)
					แล้วกด “เชื่อมต่อและโหลดข้อมูล” เพื่อดึง users/programs/merchants ที่ seed ไว้
				</p>
				<div class="grid" style="margin-top: 0.75rem;">
					<label for="apiBase">API base URL</label>
					<input
						id="apiBase"
						bind:value={apiInput}
						placeholder="http://localhost:8000"
						aria-label="API base URL"
					/>
					<button on:click={connectApi} disabled={isConnecting}>
						{isConnecting ? 'กำลังโหลด...' : 'เชื่อมต่อและโหลดข้อมูล'}
					</button>
				</div>
			</div>
			<div class="card stack">
				<h3>STEP 1 · ทำความเข้าใจ flow</h3>
				<ol style="margin: 0; padding-left: 1.1rem; font-size: 0.95rem;">
					<li>ดูยอดเงินและ merchant ที่เตรียมไว้ (แท็บ Onboarding)</li>
					<li>สร้างโปรแกรมใหม่หรือใช้เทมเพลต (แท็บ Programs)</li>
					<li>ยิงธุรกรรมผ่านโปรแกรมนั้น (แท็บ Transactions)</li>
					<li>ถ้ามี checklist ระบบจะถือเงินไว้ → ไปกด complete ในแท็บ Checklists</li>
				</ol>
				<p style="margin: 0; font-size: 0.9rem; color: rgba(16, 36, 63, 0.7);">
					ระบบจะเตือนอัตโนมัติถ้ากรอกข้อมูลผิด เช่น เลือก user ที่ไม่มีสิทธิ์ หรือหมวดหมู่ไม่ตรง whitelist
				</p>
			</div>
		</div>
		{#if loadError}
			<div class="error-banner">{loadError}</div>
		{/if}
		{#if successMessage}
			<div class="success-banner">{successMessage}</div>
		{/if}
	</header>

	<nav class="tabs">
		{#each TABS as tab}
			<div
				class={`tab ${tab === activeTab ? 'active' : ''}`}
				role="button"
				tabindex="0"
				on:click={() => (activeTab = tab)}
				on:keydown={(event) => {
					if (event.key === 'Enter' || event.key === ' ') activeTab = tab;
				}}
			>
				{tab}
			</div>
		{/each}
	</nav>

	{#if isLoading}
		<div class="info-banner">กำลังโหลดข้อมูลจาก backend ...</div>
	{/if}

	{#if activeTab === 'Onboarding'}
		<section class="stack">
			<div class="card stack">
				<h2>ภาพรวมข้อมูลที่เตรียมไว้ให้</h2>
				<p style="margin: 0;">
					เราเตรียมข้อมูลตัวอย่างไว้ให้แล้ว คุณสามารถใช้ได้ทันที หรือแก้ไข/เพิ่มของใหม่ผ่าน API
				</p>
				<div class="grid two">
					<div>
						<h3>👥 Users & Balances</h3>
						<p style="margin-top: 0; font-size: 0.9rem;">
							เงินใน balance จะถูกหักเมื่อสร้างธุรกรรม และจะคืนเมื่อ checklist ไม่ผ่านหรือยกเลิก
						</p>
                    <div class="table-scroll scroll-shadow">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>Balance</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#each users as user}
                                    <tr>
                                        <td>{user.display_name} ({user.id})</td>
                                        <td>฿{user.balance.toLocaleString('th-TH')}</td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
					</div>
					<div>
						<h3>🏪 Merchants & Categories</h3>
						<p style="margin-top: 0; font-size: 0.9rem;">
							หมวดหมู่นี้ใช้กำหนด whitelist/blacklist ใน rules (พิมพ์ให้ตรง เช่น <code>food</code>)
						</p>
                    <div class="table-scroll scroll-shadow">
                        <table>
                            <thead>
                                <tr>
                                    <th>Merchant</th>
                                    <th>Category</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#each merchants as merchant}
                                    <tr>
                                        <td>{merchant.name} ({merchant.id})</td>
                                        <td>{merchant.category}</td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
					</div>
				</div>
			</div>
			<div class="card stack">
				<h2>คู่มือเร็ว 4 ขั้นสำหรับเดโม 10 นาที</h2>
        <ol class="step-list">
            <li><strong>ตั้งกฎ</strong> – เลือกเทมเพลตแล้วปรับให้ตรง use case (เช่น เพิ่มผู้รับ/ผู้จ่าย)</li>
            <li><strong>สร้างธุรกรรม</strong> – เลือกโปรแกรม + Merchant + ยอดเงิน แล้วยิง transaction</li>
            <li><strong>ตรวจผล</strong> – ระบบจะแจ้งผลทันทีว่าผ่าน/ถูกถือไว้/ถูกปฏิเสธ เพราะอะไร</li>
            <li><strong>ปล่อยเงิน</strong> – ถ้ามี checklist ให้ไปกด complete ทีละข้อ เงินจะถูกปล่อยเมื่อครบ</li>
        </ol>
				<p style="margin: 0; font-size: 0.95rem; color: rgba(16, 36, 63, 0.7);">
					พร้อมแล้วเลื่อนไปที่แท็บ “Programs” เพื่อเริ่มสร้างกฎได้เลย ✨
				</p>
			</div>
		</section>
	{/if}

	{#if activeTab === 'Programs'}
		<section class="stack">
			<div class="card stack">
				<h2>เทมเพลตยอดนิยม (คลิกเพื่อเติมค่าลงแบบฟอร์มทันที)</h2>
				<div class="grid two">
					{#each programTemplates as template}
						<div class="card stack" style="background: #f8fbff;">
							<h3>{template.name}</h3>
							<p style="margin: 0; font-size: 0.95rem;">{template.summary}</p>
							<p style="margin: 0; font-size: 0.85rem; color: rgba(16, 36, 63, 0.7);">
								{template.details}
							</p>
							<button class="secondary" on:click={() => applyTemplate(template.id)}>
								เติมเทมเพลตนี้ลงฟอร์ม
							</button>
						</div>
					{/each}
				</div>
			</div>

			<div class="card stack">
				<h2>สร้างโปรแกรมใหม่ (STEP 2)</h2>
				<p style="margin: 0; font-size: 0.95rem;">
					กรอกทีละข้อจากบนลงล่าง ระบบจะเตือนทันทีถ้าข้อมูลไม่ครบหรือ actor พิมพ์ผิด
				</p>
				<div class="grid two">
					<div class="stack">
						<div>
							<label for="programName">1) ชื่อโปรแกรม</label>
							<input
								id="programName"
								bind:value={programForm.name}
								placeholder="เช่น Freelance Escrow รอบที่ 1"
							/>
						</div>
						<div>
							<label for="programDescription">คำอธิบาย (เล่าให้ stakeholder ฟังสั้น ๆ)</label>
							<textarea
								id="programDescription"
								bind:value={programForm.description}
								placeholder="โครงการนี้ทำเพื่ออะไร ใครคือผู้ใช้งานหลัก ฯลฯ"
							></textarea>
						</div>
						<div class="grid">
							<label for="programOwner">2) Program owner (คนรับผิดชอบ)</label>
							<select id="programOwner" bind:value={programForm.created_by}>
								{#each users as user}
									<option value={user.id}>{user.display_name} ({user.id})</option>
								{/each}
							</select>
						</div>
						<div class="grid">
							<p style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.35rem;">
								ผู้ที่ใช้โปรแกรมได้ (ใส่ทั้งผู้จ่ายและผู้รับ)
							</p>
							<div class="stack">
								{#each users as user}
									<label style="display: flex; align-items: center; gap: 0.5rem; font-weight: 500;">
										<input
											type="checkbox"
											checked={programForm.allowed_users.includes(user.id)}
											on:change={(event) => {
												const checked = (event.currentTarget as HTMLInputElement).checked;
												programForm.allowed_users = checked
													? Array.from(new Set([...programForm.allowed_users, user.id]))
													: programForm.allowed_users.filter((id) => id !== user.id);
											}}
										/>
										{user.display_name} ({user.id})
									</label>
								{/each}
							</div>
						</div>
					</div>
					<div class="stack">
						<div class="grid two">
							<div>
								<label for="maxAmount">3) เพดานต่อครั้ง (0 = ไม่กำหนด)</label>
								<input id="maxAmount" type="number" min="0" bind:value={programForm.maxAmount} />
							</div>
							<div>
								<label for="dailyLimit">เพดานต่อวัน (0 = ไม่กำหนด)</label>
								<input id="dailyLimit" type="number" min="0" bind:value={programForm.dailyLimit} />
							</div>
						</div>

						<div>
							<p style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.35rem;">
								4) หมวด merchant ที่อนุญาต/ห้าม
							</p>
							<select
								multiple
								size={Math.min(6, categoryOptions.length || 3)}
								bind:value={programForm.allowedCategories}
							>
								<option value="" disabled>Allowed categories</option>
								{#each categoryOptions as cat}
									<option value={cat}>{cat}</option>
								{/each}
							</select>
							<select
								multiple
								size={Math.min(6, categoryOptions.length || 3)}
								bind:value={programForm.blockedCategories}
							>
								<option value="" disabled>Blocked categories</option>
								{#each categoryOptions as cat}
									<option value={cat}>{cat}</option>
								{/each}
							</select>
							<p style="margin: 0; font-size: 0.8rem; color: rgba(16, 36, 63, 0.65);">
								Tip: หมวดหมู่ต้องตรงกับ category ของ merchant (ดูในแท็บ Onboarding) เช่น
								<code>food</code>, <code>retail</code>
							</p>
						</div>

						<div>
							<label style="display: flex; gap: 0.6rem; align-items: center;">
								<input type="checkbox" bind:checked={programForm.requireChecklist} />
								ต้องมี checklist ก่อนปล่อยเงิน
							</label>
							<label style="display: flex; gap: 0.6rem; align-items: center; margin-top: 0.5rem;">
								<input
									type="checkbox"
									bind:checked={programForm.requireExternalVerification}
								/>
								ต้องมี verification เพิ่มเติม (PoC นี้จะถือว่า pass เสมอ)
							</label>
							<textarea
								class={!programForm.requireChecklist ? 'disabled-textarea' : ''}
								bind:value={programForm.checklistText}
								placeholder="ตัวอย่าง: ส่งใบเสร็จตัวจริง | receiver"
								disabled={!programForm.requireChecklist}
							></textarea>
							{#if programForm.requireChecklist}
								<div>
									<p style="margin: 0; font-size: 0.9rem; font-weight: 600;">Preview</p>
									{#if checklistPreviewError}
										<div class="error-banner">{checklistPreviewError}</div>
									{:else if checklistPreview.length === 0}
										<p style="margin: 0; font-size: 0.85rem;">
											พิมพ์ checklist ทีละบรรทัดเพื่อดูตัวอย่าง actor ที่นี่
										</p>
									{:else}
                    <div class="table-scroll">
                        <table>
                            <thead>
                                <tr>
                                    <th>รายละเอียด</th>
                                    <th>Actor</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#each checklistPreview as row (row.description)}
                                    <tr>
                                        <td>{row.description}</td>
                                        <td>{row.required_by}</td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
									{/if}
								</div>
							{/if}
						</div>
					</div>
				</div>
				<div class="divider"></div>
				<div class="stack">
					<button on:click={handleCreateProgram} disabled={isSubmittingProgram}>
						{isSubmittingProgram ? 'กำลังสร้างโปรแกรม...' : '✅ สร้างโปรแกรมนี้'}
					</button>
					<p style="margin: 0; font-size: 0.85rem; color: rgba(16, 36, 63, 0.65);">
						หลังสร้างเสร็จ ระบบจะโหลดรายการโปรแกรมใหม่อัตโนมัติ และแนะนำให้ไปยังแท็บ Transactions ต่อ
					</p>
				</div>
			</div>

			<div class="card stack">
				<h2>โปรแกรมที่พร้อมใช้งาน</h2>
				{#if programs.length === 0}
					<p>ยังไม่มีโปรแกรมในระบบ ลองสร้างจากเทมเพลตด้านบนก่อน</p>
				{:else}
					{#each programs as program}
						<details class="card stack" style="background: #ffffff;">
							<summary style="font-weight: 700; cursor: pointer;">
								{program.name} · Owner: {getUserLabel(program.created_by)} · Allowed:{' '}
								{program.allowed_users.map((userId) => `${getUserLabel(userId)} (${userId})`).join(', ')}
							</summary>
							<p style="margin: 0;">
								{program.description ?? 'ไม่มีคำอธิบาย'}
							</p>
                            <div class="table-scroll">
                                <table>
                                    <tbody>
                                        <tr>
                                            <td style="width: 180px;">Max amount</td>
                                            <td>{program.rules.max_amount ?? 'ไม่จำกัด'}</td>
                                        </tr>
                                        <tr>
                                            <td>Daily limit</td>
                                            <td>{program.rules.daily_limit ?? 'ไม่จำกัด'}</td>
                                        </tr>
                                        <tr>
                                            <td>Allowed categories</td>
                                            <td>
                                                {#if (program.rules.allowed_categories ?? []).length > 0}
                                                    {program.rules.allowed_categories.join(', ')}
                                                {:else}
                                                    ทั้งหมด
                                                {/if}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td>Blocked categories</td>
                                            <td>
                                                {#if (program.rules.blocked_categories ?? []).length > 0}
                                                    {program.rules.blocked_categories.join(', ')}
                                                {:else}
                                                    ไม่มี
                                                {/if}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td>Checklist required</td>
                                            <td>{program.rules.require_checklist ? 'ต้องตรวจ checklist' : 'ไม่ต้อง'}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
							{#if program.rules.checklist_template && program.rules.checklist_template.length > 0}
								<h4>Checklist template</h4>
                                <div class="table-scroll">
                                    <table>
                                        <thead>
                                            <tr>
                                                <th>รายละเอียด</th>
                                                <th>Actor</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {#each program.rules.checklist_template as item}
                                                <tr>
                                                    <td>{item.description}</td>
                                                    <td>{item.required_by}</td>
                                                </tr>
                                            {/each}
                                        </tbody>
                                    </table>
                                </div>
							{/if}
						</details>
					{/each}
				{/if}
			</div>
		</section>
	{/if}

	{#if activeTab === 'Transactions'}
		<section class="stack">
			<div class="card stack">
				<h2>ยิงธุรกรรมเดโม (STEP 3)</h2>
				{#if lastTransactionFeedback}
                    <div class="card stack" style="background: rgba(224, 242, 254, 0.85);">
						<h3>ผลลัพธ์ล่าสุด</h3>
						<p style="margin: 0;">สถานะ: {lastTransactionFeedback.status}</p>
						<p style="margin: 0;">
							ผู้จ่าย: {getUserLabel(lastTransactionFeedback.from_user)} →
							ผู้รับ: {getUserLabel(lastTransactionFeedback.to_user)}
						</p>
					</div>
				{/if}
				<form class="stack" on:submit|preventDefault={handleCreateTransaction}>
					<div class="grid two">
						<div>
							<label for="txnProgram">1) เลือกโปรแกรม (ดู allowed users ประกอบ)</label>
							<select
								id="txnProgram"
								bind:value={transactionForm.programId}
								on:change={() => {
									const prog = programsMap[transactionForm.programId];
									if (prog) {
										transactionForm.fromUser = prog.allowed_users[0] ?? '';
										transactionForm.toUser = prog.allowed_users[1] ?? prog.allowed_users[0] ?? '';
									}
								}}
							>
								{#each programs as program}
									<option value={program.id}>
										{program.name} · allowed: {program.allowed_users.length} คน
									</option>
								{/each}
							</select>
						</div>
						<div>
							<label for="txnAmount">2) จำนวนเงิน (บาท)</label>
							<input id="txnAmount" type="number" min="1" bind:value={transactionForm.amount} />
						</div>
					</div>

					{#if selectedProgram}
						<div class="info-banner">
							<strong>คู่มือสำหรับโปรแกรมนี้:</strong>
							<ul style="margin: 0; padding-left: 1.1rem;">
								<li>
									ผู้ที่มีสิทธิ์:
									{selectedProgram.allowed_users
										.map((id) => `${getUserLabel(id)} (${id})`)
										.join(', ')}
								</li>
								<li>
									หมวดที่อนุญาต:
									{(selectedProgram.rules.allowed_categories ?? []).length > 0
										? selectedProgram.rules.allowed_categories.join(', ')
										: 'ทุกหมวด'}
								</li>
								<li>
									หมวดที่ห้าม:
									{(selectedProgram.rules.blocked_categories ?? []).length > 0
										? selectedProgram.rules.blocked_categories.join(', ')
										: 'ไม่มี'}
								</li>
								<li>
									Checklist:
									{selectedProgram.rules.require_checklist
										? 'มี ต้องไปกด complete ทีละข้อหลังจากยิงธุรกรรม'
										: 'ไม่มี ปล่อยเงินอัตโนมัติ'}
								</li>
							</ul>
						</div>
					{/if}

					<div class="grid two">
						<div>
							<label for="txnFrom">3) ผู้จ่าย (ต้องมีสิทธิ์)</label>
							<select id="txnFrom" bind:value={transactionForm.fromUser}>
								{#each users as user}
									<option value={user.id}>{user.display_name} ({user.id})</option>
								{/each}
							</select>
						</div>
						<div>
							<label for="txnTo">ผู้รับ (ต้องมีสิทธิ์)</label>
							<select id="txnTo" bind:value={transactionForm.toUser}>
								{#each users as user}
									<option value={user.id}>{user.display_name} ({user.id})</option>
								{/each}
							</select>
						</div>
					</div>

					<div class="grid two">
						<div>
							<label for="txnMerchant">4) เลือก merchant</label>
							<select id="txnMerchant" bind:value={transactionForm.merchantId}>
								<option value="">(ไม่มี)</option>
								{#each merchants as merchant}
									<option value={merchant.id}>
										{merchant.name} · {merchant.category}
									</option>
								{/each}
							</select>
							<p style="margin: 0; font-size: 0.8rem; color: rgba(16, 36, 63, 0.65);">
								หากหมวดไม่ตรงกับ allowed categories ระบบจะ <strong>REJECT</strong>
								(เช่น เลือก 7-Eleven เมื่ออนุญาตเฉพาะ food)
							</p>
						</div>
						<div>
							<label for="txnNote">หมายเหตุ (optional)</label>
							<input
								id="txnNote"
								placeholder="เช่น milestone 1, ซื้ออุปกรณ์การแพทย์ ฯลฯ"
								bind:value={transactionForm.note}
							/>
						</div>
					</div>
					<p style="margin: 0; font-size: 0.85rem; color: rgba(16, 36, 63, 0.65);">
						Note: ผู้จ่าย/ผู้รับต้องอยู่ใน allow list ของโปรแกรม ไม่งั้นระบบจะปฏิเสธอัตโนมัติ
					</p>
					<button type="submit" disabled={isSubmittingTransaction}>
						{isSubmittingTransaction ? 'กำลังสร้างธุรกรรม...' : '🚀 ยิงธุรกรรม'}
					</button>
				</form>
			</div>

			<div class="card stack">
				<h2>ธุรกรรมทั้งหมด</h2>
				{#if transactions.length === 0}
					<p>ยังไม่มีธุรกรรม ลองสร้างจากแบบฟอร์มด้านบนก่อน</p>
				{:else}
					{#each transactions as txn}
						<details class="card stack" style="background: #ffffff;">
							<summary style="font-weight: 700; cursor: pointer;">
								{txn.id.slice(0, 8)} • ฿{txn.amount.toLocaleString('th-TH')} • {txn.status}
							</summary>
                        <div class="table-scroll">
                            <table>
                                <tbody>
                                    <tr>
                                        <td style="width: 180px;">Program</td>
                                        <td>{programsMap[txn.program_id]?.name ?? txn.program_id}</td>
                                    </tr>
                                    <tr>
                                        <td>From → To</td>
                                        <td>{getUserLabel(txn.from_user)} → {getUserLabel(txn.to_user)}</td>
                                    </tr>
                                    <tr>
                                        <td>Merchant</td>
                                        <td>
                                            {txn.merchant_id
                                                ? `${merchants.find((m) => m.id === txn.merchant_id)?.name ?? txn.merchant_id} (${txn.merchant_category ?? '?'})`
                                                : '—'}
                                        </td>
                                    </tr>
                                    <tr>
                                        <td>สร้างเมื่อ</td>
                                        <td>{new Date(txn.created_at).toLocaleString('th-TH')}</td>
                                    </tr>
                                    <tr>
                                        <td>หมายเหตุ</td>
                                        <td>{txn.note ?? '—'}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
							{#if txn.status !== 'COMPLETED' && txn.status !== 'CANCELLED' && txn.status !== 'REJECTED'}
								<button
									class="secondary"
									on:click={async () => {
										try {
											await cancelTransaction(txn.id);
											successMessage = 'ยกเลิกธุรกรรมแล้ว เงินถูกคืนให้ผู้จ่าย';
											await loadEverything(false);
										} catch (error) {
											loadError =
												error instanceof Error ? error.message : 'ยกเลิกธุรกรรมไม่สำเร็จ';
										}
									}}
								>
									ยกเลิกธุรกรรมนี้
								</button>
							{/if}
						</details>
					{/each}
				{/if}
			</div>
		</section>
	{/if}

	{#if activeTab === 'Checklists'}
		<section class="stack">
			<div class="card stack">
				<h2>จัดการ Checklist (STEP 4)</h2>
				<p style="margin: 0; font-size: 0.95rem;">
					เลือกธุรกรรมที่สถานะ <strong>HELD</strong> แล้วกด Complete ทีละข้อ
					ระบบจะปล่อยเงินทันทีเมื่อ checklist ครบทุกข้อ
				</p>
				<label for="checklistTxn" style="margin-top: 1rem;">1) เลือกธุรกรรม</label>
				<select id="checklistTxn" bind:value={checklistSelection.transactionId}>
					{#each transactions as txn}
						<option value={txn.id}>
							{txn.id.slice(0, 8)} • {txn.status} • ฿{txn.amount.toLocaleString('th-TH')}
						</option>
					{/each}
				</select>

				{#if checklistSelection.transactionId}
					{#if !(checklists[checklistSelection.transactionId] ?? []).length}
						<p>ธุรกรรมนี้ไม่ต้องใช้ checklist หรือกำลังโหลด...</p>
					{:else}
						<div class="stack">
							{#each checklists[checklistSelection.transactionId] as item}
								<div class="card stack" style="background: #ffffff;">
									<div style="display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap;">
										<div>
											<p style="margin: 0; font-weight: 600;">{item.description}</p>
											<p style="margin: 0; font-size: 0.85rem; color: rgba(16, 36, 63, 0.65);">
												Actor ที่ต้องกดยืนยัน: {item.required_by}
											</p>
											{#if item.is_completed}
												<p style="margin: 0; font-size: 0.85rem; color: rgba(22, 101, 52, 0.8);">
													✔️ กดยืนยันแล้วโดย {item.completed_by ?? '-'} เมื่อ{' '}
													{item.completed_at
														? new Date(item.completed_at).toLocaleString('th-TH')
														: '-'}
												</p>
											{/if}
										</div>
										<div class="stack" style="min-width: 200px;">
											{#if !item.is_completed}
												<button
													on:click={() => handleChecklistAction(item, 'complete')}
													disabled={isChecklistBusy}
												>
													✅ Complete (ยืนยันขั้นตอนนี้)
												</button>
											{:else}
												<button
													class="secondary"
													on:click={() => handleChecklistAction(item, 'undo')}
													disabled={isChecklistBusy}
												>
													↩️ Undo (ขอกลับไปตรวจใหม่)
												</button>
											{/if}
										</div>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{/if}
			</div>
		</section>
	{/if}

	{#if activeTab === 'Reference'}
		<section class="stack">
			<div class="card stack">
				<h2>Reference & Troubleshooting</h2>
				<ul style="margin: 0;">
					<li>
						<strong>403: ผู้ใช้ไม่ได้รับสิทธิ์</strong> – ตรวจ allowed users ของโปรแกรม
						ว่ามีทั้งผู้จ่ายและผู้รับไหม
					</li>
					<li>
						<strong>REJECT (category)</strong> – ตรวจว่า merchant.category อยู่ใน allowed categories
						และไม่ได้อยู่ใน blocked
					</li>
					<li>
						<strong>HELD</strong> – ไปที่แท็บ Checklists แล้วกด complete ให้ครบทุกข้อ
					</li>
					<li>
						<strong>Reset ระบบ</strong> – ลบไฟล์ <code>data/store.json</code> แล้วรัน backend ใหม่
					</li>
					<li>
						<strong>ทดลอง use case ใหม่</strong> – สร้างโปรแกรมเพิ่มหรือแก้ไข allowed users
						ให้ครอบคลุมทีมอื่น ๆ
					</li>
				</ul>
			</div>
		</section>
	{/if}
</main>
