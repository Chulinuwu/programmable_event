export type ChecklistActor = 'sender' | 'receiver' | 'admin';

export interface ChecklistTemplateItem {
	description: string;
	required_by: ChecklistActor;
}

export interface RuleConfig {
	allowed_categories: string[];
	blocked_categories: string[];
	max_amount: number | null;
	daily_limit: number | null;
	require_checklist: boolean;
	checklist_template?: ChecklistTemplateItem[];
	require_external_verification?: boolean;
}

export interface Program {
	id: string;
	name: string;
	description?: string | null;
	rules: RuleConfig;
	created_at: string;
	created_by: string;
	allowed_users: string[];
}

export interface ProgramCreatePayload {
	name: string;
	description?: string | null;
	created_by: string;
	allowed_users: string[];
	rules: RuleConfig;
}

export type TransactionStatus = 'PENDING' | 'HELD' | 'COMPLETED' | 'REJECTED' | 'CANCELLED';

export interface ChecklistItem {
	id: string;
	transaction_id: string;
	description: string;
	required_by: ChecklistActor;
	is_completed: boolean;
	completed_by?: string | null;
	completed_at?: string | null;
}

export interface Transaction {
	id: string;
	program_id: string;
	from_user: string;
	to_user: string;
	amount: number;
	merchant_id?: string | null;
	merchant_category?: string | null;
	note?: string | null;
	status: TransactionStatus;
	created_at: string;
	updated_at: string;
	checklist: ChecklistItem[];
}

export interface TransactionCreatePayload {
	program_id: string;
	from_user: string;
	to_user: string;
	amount: number;
	merchant_id?: string | null;
	note?: string | null;
}

export interface ChecklistRequestPayload {
	actor: ChecklistActor;
	user_id: string;
}

export interface Merchant {
	id: string;
	category: string;
	name: string;
}

export interface User {
	id: string;
	display_name: string;
	balance: number;
}
