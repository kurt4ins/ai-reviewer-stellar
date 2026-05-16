import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, Finding } from "../api";

const SEV_ORDER: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3,
};

const SEV_COLOR: Record<string, string> = {
  critical: "var(--critical)",
  high: "var(--high)",
  medium: "var(--medium)",
  low: "var(--low)",
};

const SEV_CLASS: Record<string, string> = {
  critical: "badge badge-crit",
  high: "badge badge-high",
  medium: "badge badge-warn",
  low: "badge badge-low",
};

function FindingCard({ f, idx }: { f: Finding; idx: number }) {
  const borderColor = SEV_COLOR[f.severity] ?? "var(--border)";

  return (
    <div
      className="finding-card"
      style={{
        borderLeftColor: borderColor,
        animationDelay: `${idx * 50}ms`,
      }}
    >
      <div className="finding-header">
        <div className="finding-meta">
          <span className={SEV_CLASS[f.severity] ?? "badge badge-dim"}>
            {f.severity}
          </span>
          <span className="badge badge-dim">{f.cwe}</span>
          <span className="finding-path">
            {f.file_path}:{f.line_number}
          </span>
        </div>
        <span className="confidence-pill">
          {(f.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>

      <p className="finding-desc">{f.description}</p>

      {f.fix_explanation && (
        <p style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 0 }}>
          {f.fix_explanation}
        </p>
      )}

      {f.fix_code && (
        <>
          <div className="finding-fix-label">Исправление</div>
          <pre className="codeblock"><code>{f.fix_code}</code></pre>
        </>
      )}
    </div>
  );
}

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["review", id],
    queryFn: () => api.getReview(id!),
    enabled: !!id,
  });

  const findings = [...(data?.findings ?? [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  );

  const statusCls =
    data?.status === "completed"
      ? "badge badge-ok"
      : data?.status === "failed"
        ? "badge badge-crit"
        : "badge badge-dim";

  return (
    <>
      <Link to="/reviews" className="back-link">← Все ревью</Link>

      {isLoading && <div className="spinner">Загрузка…</div>}
      {error && (
        <div className="error-msg">
          {error instanceof Error ? error.message : "ошибка загрузки"}
        </div>
      )}

      {data && (
        <>
          <div className="page-header" style={{ alignItems: "flex-start" }}>
            <div>
              <h2 style={{ marginBottom: 6 }}>
                {data.repo_full_name}
                <span style={{ color: "var(--muted)", fontWeight: 400, marginLeft: 10 }}>
                  #{data.pr_number}
                </span>
              </h2>
            </div>
          </div>

          <div className="detail-meta">
            <span className={statusCls}>{data.status}</span>
            <span className="detail-sha">{data.commit_sha.slice(0, 12)}</span>
            {data.critical_count > 0 && (
              <span className="badge badge-crit">{data.critical_count} critical</span>
            )}
            <span className="badge badge-dim">{data.findings_count} находок</span>
          </div>

          {findings.length === 0 && (
            <div className="empty-state">Уязвимостей не найдено</div>
          )}
          {findings.map((f, i) => (
            <FindingCard key={f.id} f={f} idx={i} />
          ))}
        </>
      )}
    </>
  );
}
