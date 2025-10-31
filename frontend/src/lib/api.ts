import type {
	ChecklistItem,
	ChecklistRequestPayload,
	Merchant,
	Program,
	ProgramCreatePayload,
	Transaction,
	TransactionCreatePayload,
	User
} from './types';

let apiBase = 'http://localhost:8000';

export function setApiBase(url: string) {
	apiBase = url.replace(/\/+$/, '');
}

export function getApiBase(): string {
	return apiBase;
}

async function handleResponse<T>(res: Response): Promise<T> {
	if (!res.ok) {
		let message = `${res.status} ${res.statusText}`;
		try {
			const payload = await res.json();
			if (payload?.detail) {
				if (typeof payload.detail === 'string') {
					message = payload.detail;
				} else {
					message = JSON.stringify(payload.detail);
				}
			}
		} catch (error) {
			// ignore JSON parse error, keep default status text
		}
		throw new Error(message);
	}
	return (await res.json()) as T;
}

export async function fetchPrograms(): Promise<Program[]> {
	const res = await fetch(`${apiBase}/api/programs`);
	return handleResponse<Program[]>(res);
}

export async function createProgram(payload: ProgramCreatePayload): Promise<Program> {
	const res = await fetch(`${apiBase}/api/programs`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});
	return handleResponse<Program>(res);
}

export async function fetchTransactions(): Promise<Transaction[]> {
	const res = await fetch(`${apiBase}/api/transactions`);
	return handleResponse<Transaction[]>(res);
}

export async function createTransaction(payload: TransactionCreatePayload): Promise<Transaction> {
	const res = await fetch(`${apiBase}/api/transactions`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});
	return handleResponse<Transaction>(res);
}

export async function cancelTransaction(id: string): Promise<Transaction> {
	const res = await fetch(`${apiBase}/api/transactions/${id}/cancel`, {
		method: 'POST'
	});
	return handleResponse<Transaction>(res);
}

export async function fetchChecklist(transactionId: string): Promise<ChecklistItem[]> {
	const res = await fetch(`${apiBase}/api/transactions/${transactionId}/checklist`);
	return handleResponse<ChecklistItem[]>(res);
}

export async function completeChecklistItem(
	itemId: string,
	payload: ChecklistRequestPayload
): Promise<Transaction> {
	const res = await fetch(`${apiBase}/api/checklist/${itemId}/complete`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});
	return handleResponse<Transaction>(res);
}

export async function undoChecklistItem(
	itemId: string,
	payload: ChecklistRequestPayload
): Promise<Transaction> {
	const res = await fetch(`${apiBase}/api/checklist/${itemId}/uncomplete`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});
	return handleResponse<Transaction>(res);
}

export async function fetchMerchants(): Promise<Merchant[]> {
	const res = await fetch(`${apiBase}/api/merchants`);
	return handleResponse<Merchant[]>(res);
}

export async function fetchUsers(): Promise<User[]> {
	const res = await fetch(`${apiBase}/api/users`);
	return handleResponse<User[]>(res);
}
