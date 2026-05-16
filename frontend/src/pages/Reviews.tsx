import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ReviewSummary } from "../api";

function statusBadge(status: string) {
  if (status === "completed") return <span className="badge badge-ok">{status}</span>;
  if (status === "failed") return <span className="badge badge-crit">{status}</span>;
  return <span className="badge badge-dim">{status}</span>;
}

function ReviewRow({ r, idx }: { r: ReviewSummary; idx: number }) {
  return (
    <Link
      to={`/reviews/${r.id}`}
      className="review-row"
      style={{ animationDelay: `${idx * 50}ms` }}
    >
      <div className="review-main">
        <div className="review-repo">
          {r.repo_full_name}
          <span className="provider-tag">{r.provider}</span>
          <span style={{ color: "var(--muted)", fontWeight: 400 }}>#{r.pr_number}</span>
        </div>
        <div className="review-sha">{r.commit_sha.slice(0, 12)}</div>
      </div>

      <div className="review-right">
        <div className="review-counts">
          {statusBadge(r.status)}
          {r.critical_count > 0 && (
            <span className="badge badge-crit">{r.critical_count} critical</span>
          )}
          <span className="badge badge-dim">{r.findings_count} находок</span>
        </div>
        <div className="review-date">
          {new Date(r.created_at).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>
    </Link>
  );
}

export default function Reviews() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["reviews"],
    queryFn: () => api.listReviews(),
  });

  return (
    <>
      <div className="page-header">
        <h2>Ревью</h2>
      </div>

      {isLoading && <div className="spinner">Загрузка…</div>}
      {error && (
        <div className="error-msg">
          {error instanceof Error ? error.message : "ошибка загрузки"}
        </div>
      )}
      {data?.length === 0 && (
        <div className="empty-state">
          Ревью появятся после открытия PR в подключённом репозитории
        </div>
      )}
      {data?.map((r, i) => <ReviewRow key={r.id} r={r} idx={i} />)}
    </>
  );
}
