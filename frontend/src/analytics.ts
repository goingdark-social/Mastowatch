import { apiFetch } from './api';

export type OverviewMetrics = {
  totals: {
    accounts: number;
    analyses: number;
    reports: number;
  };
  recent_24h: {
    analyses: number;
    reports: number;
  };
  rules: Array<{
    rule_key: string;
    count: number;
    avg_score: number;
  }>;
  top_domains: Array<{
    domain: string;
    analysis_count: number;
  }>;
};

export type TimelineData = {
  analyses: Array<{
    date: string;
    count: number;
  }>;
  reports: Array<{
    date: string;
    count: number;
  }>;
};

export type AccountData = {
  accounts: Array<{
    id: number;
    mastodon_account_id: string;
    acct: string;
    domain: string;
    last_checked_at: string | null;
    analysis_count: number;
    report_count: number;
    last_analysis: string | null;
  }>;
};

export type ReportData = {
  reports: Array<{
    id: number;
    mastodon_account_id: string;
    account: string;
    status_id: string | null;
    mastodon_report_id: string | null;
    comment: string;
    created_at: string;
  }>;
};

export type AnalysisData = {
  analyses: Array<{
    id: number;
    status_id: string | null;
    rule_key: string;
    score: number;
    evidence: any;
    created_at: string;
    scan_type?: string;
    content_hash?: string;
    scan_result?: any;
    rules_version?: string;
    last_scanned_at?: string;
    needs_rescan?: boolean;
  }>;
};

export type RulesData = {
  rules: {
    report_threshold: number;
    username_regex?: Array<{ name: string; pattern: string; weight: number; enabled?: boolean; id?: number }>;
    display_name_regex?: Array<{ name: string; pattern: string; weight: number; enabled?: boolean; id?: number }>;
    content_regex?: Array<{ name: string; pattern: string; weight: number; enabled?: boolean; id?: number }>;
  };
  report_threshold: number;
};

export type Rule = {
  id?: number;
  name: string;
  rule_type: 'regex' | 'keyword' | 'behavioral' | 'media';
  detector_type?: 'regex' | 'keyword' | 'behavioral' | 'media';
  pattern: string;
  weight: number;
  enabled: boolean;
  action_type?: string;
  trigger_threshold?: number;
  trigger_count?: number;
  last_triggered_at?: string | null;
  last_triggered_content?: any;
  created_by?: string;
  updated_by?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
};

export type RulesList = {
  rules: Rule[];
};

export type ScanningAnalytics = {
  active_sessions: Array<{
    id: number;
    session_type: string;
    accounts_processed: number;
    total_accounts?: number;
    started_at: string;
    current_cursor?: string;
  }>;
  recent_sessions: Array<{
    id: number;
    session_type: string;
    accounts_processed: number;
    started_at: string;
    completed_at?: string;
    status: string;
  }>;
  content_scan_stats: {
    total_scans: number;
    needs_rescan: number;
    last_scan?: string;
  };
};

export type DomainAnalytics = {
  summary: {
    total_domains: number;
    defederated_domains: number;
    high_risk_domains: number;
    monitored_domains: number;
  };
  domain_alerts: Array<{
    domain: string;
    violation_count: number;
    last_violation_at?: string;
    defederation_threshold: number;
    is_defederated: boolean;
    defederated_at?: string;
    defederated_by?: string;
    notes?: string;
  }>;
};

export type RuleStatistics = {
  total_rules: number;
  enabled_rules: number;
  disabled_rules: number;
  top_triggered_rules: Array<{
    name: string;
    trigger_count: number;
    rule_type: string;
    last_triggered_at?: string;
  }>;
  recent_activity: Array<{
    name: string;
    rule_type: string;
    last_triggered_at?: string;
  }>;
};

export type RuleDetails = Rule & {
  recent_analyses: Array<{
    id: number;
    mastodon_account_id: string;
    score: number;
    created_at: string;
    evidence: any;
  }>;
};

export async function fetchOverview(): Promise<OverviewMetrics> {
  return apiFetch<OverviewMetrics>('/analytics/overview');
}

export async function fetchTimeline(days: number = 7): Promise<TimelineData> {
  return apiFetch<TimelineData>(`/analytics/timeline?days=${days}`);
}

export async function fetchAccounts(limit: number = 50, offset: number = 0): Promise<AccountData> {
  return apiFetch<AccountData>(`/analytics/accounts?limit=${limit}&offset=${offset}`);
}

export async function fetchReports(limit: number = 50, offset: number = 0): Promise<ReportData> {
  return apiFetch<ReportData>(`/analytics/reports?limit=${limit}&offset=${offset}`);
}

export async function fetchAccountAnalyses(accountId: string, limit: number = 50, offset: number = 0): Promise<AnalysisData> {
  return apiFetch<AnalysisData>(`/analytics/analyses/${accountId}?limit=${limit}&offset=${offset}`);
}

export async function fetchCurrentRules(): Promise<RulesData> {
  return apiFetch<RulesData>('/rules/current');
}

export async function fetchRulesList(): Promise<RulesList> {
  return apiFetch<RulesList>('/rules');
}

export async function createRule(rule: Omit<Rule, 'id'>): Promise<Rule> {
  return apiFetch<Rule>('/rules', {
    method: 'POST',
    body: JSON.stringify(rule)
  });
}

export async function updateRule(id: number, rule: Partial<Rule>): Promise<Rule> {
  return apiFetch<Rule>(`/rules/${id}`, {
    method: 'PUT',
    body: JSON.stringify(rule)
  });
}

export async function deleteRule(id: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/rules/${id}`, {
    method: 'DELETE'
  });
}

export async function toggleRule(id: number): Promise<{ id: number; name: string; enabled: boolean; message: string }> {
  return apiFetch<{ id: number; name: string; enabled: boolean; message: string }>(`/rules/${id}/toggle`, {
    method: 'POST'
  });
}

// Analytics Functions
export async function fetchScanningAnalytics(): Promise<ScanningAnalytics> {
  return apiFetch<ScanningAnalytics>('/analytics/scanning');
}

export async function fetchDomainAnalytics(): Promise<DomainAnalytics> {
  return apiFetch<DomainAnalytics>('/analytics/domains');
}

export async function fetchRuleStatistics(): Promise<RuleStatistics> {
  return apiFetch<RuleStatistics>('/analytics/rules/statistics');
}

export async function fetchRuleDetails(id: number): Promise<RuleDetails> {
  return apiFetch<RuleDetails>(`/rules/${id}/details`);
}

// Scanning Control Functions
export async function triggerFederatedScan(domains?: string[]): Promise<{ task_id: string; message: string; target_domains: string[] | string }> {
  return apiFetch<{ task_id: string; message: string; target_domains: string[] | string }>('/scanning/federated', {
    method: 'POST',
    body: JSON.stringify(domains ? { domains } : {})
  });
}

export async function triggerDomainCheck(): Promise<{ task_id: string; message: string }> {
  return apiFetch<{ task_id: string; message: string }>('/scanning/domain-check', {
    method: 'POST'
  });
}

export async function invalidateScanCache(rule_changes = false): Promise<{ message: string; rule_changes: boolean }> {
  return apiFetch<{ message: string; rule_changes: boolean }>('/scanning/invalidate-cache', {
    method: 'POST',
    body: JSON.stringify({ rule_changes })
  });
}

export async function bulkToggleRules(rule_ids: number[], enabled: boolean): Promise<{ updated_rules: string[]; enabled: boolean; message: string }> {
  return apiFetch<{ updated_rules: string[]; enabled: boolean; message: string }>('/rules/bulk-toggle', {
    method: 'POST',
    body: JSON.stringify({ rule_ids, enabled })
  });
}
