import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Repo } from "../api";

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <div className="setup-label">{label}</div>
      <div className="copy-field">
        <span className="copy-field-val">{value}</span>
        <button
          onClick={() => {
            navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? "✓ Скопировано" : "Копировать"}
        </button>
      </div>
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="toggle-row">
      <input
        type="checkbox"
        className="toggle"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="toggle-label">{label}</span>
    </label>
  );
}

function RepoCard({ repo, idx }: { repo: Repo; idx: number }) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["repos"] });

  const update = useMutation({
    mutationFn: (patch: Partial<Repo>) => api.updateRepo(repo.id, patch),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: () => api.deleteRepo(repo.id),
    onSuccess: invalidate,
  });

  const hooksUrl =
    repo.provider === "github"
      ? `https://github.com/${repo.owner}/${repo.name}/settings/hooks`
      : `https://gitlab.com/${repo.owner}/${repo.name}/-/hooks`;

  return (
    <div className="card" style={{ animationDelay: `${idx * 60}ms` }}>
      <div className="repo-header">
        <div>
          <div className="repo-name">
            {repo.owner}/{repo.name}
            <span className="provider-tag">{repo.provider}</span>
          </div>
          <div className="repo-url">{repo.webhook_url}</div>
        </div>
        <button
          className="danger-ghost"
          onClick={() => {
            if (confirm(`Удалить ${repo.owner}/${repo.name}?`)) remove.mutate();
          }}
          disabled={remove.isPending}
        >
          Удалить
        </button>
      </div>

      <details className="webhook-setup">
        <summary>Настройка вебхука</summary>
        <div className="webhook-body">
          <CopyField label="Payload URL" value={repo.webhook_url} />
          <CopyField label="Secret" value={repo.webhook_secret} />
          <ol className="steps-list">
            <li>Content type: <code>application/json</code></li>
            <li>
              Событие:{" "}
              {repo.provider === "github" ? "Pull requests" : "Merge request events"}
            </li>
            <li>
              Откройте{" "}
              <a href={hooksUrl} target="_blank" rel="noreferrer">
                настройки репозитория
              </a>{" "}
              и вставьте URL и Secret
            </li>
          </ol>
        </div>
      </details>

      <div className="toggles-row">
        <Toggle
          checked={repo.block_critical_merge}
          onChange={(v) => update.mutate({ block_critical_merge: v })}
          label="Блокировать мерж при critical"
        />
        <Toggle
          checked={repo.dialog_enabled}
          onChange={(v) => update.mutate({ dialog_enabled: v })}
          label="Диалог в комментариях"
        />
      </div>
    </div>
  );
}

function AddRepo() {
  const qc = useQueryClient();
  const [provider, setProvider] = useState("github");
  const [owner, setOwner] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.createRepo(provider, owner, name),
    onSuccess: () => {
      setOwner("");
      setName("");
      setError(null);
      qc.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (e) => setError(e instanceof Error ? e.message : "ошибка"),
  });

  return (
    <div className="add-repo-card">
      <div className="add-repo-title">Добавить репозиторий</div>
      <div className="form-row">
        <div className="form-field narrow">
          <label className="field-label">Провайдер</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="github">github</option>
            <option value="gitlab">gitlab</option>
          </select>
        </div>
        <div className="form-field">
          <label className="field-label">Owner</label>
          <input
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="acme-corp"
          />
        </div>
        <div className="form-field">
          <label className="field-label">Repository</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-service"
          />
        </div>
        <button
          onClick={() => create.mutate()}
          disabled={!owner || !name || create.isPending}
        >
          {create.isPending ? "..." : "Добавить"}
        </button>
      </div>
      {error && <div className="error-msg">{error}</div>}
    </div>
  );
}

export default function Repos() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["repos"],
    queryFn: api.listRepos,
  });

  return (
    <>
      <div className="page-header">
        <h2>Репозитории</h2>
      </div>
      <AddRepo />
      {isLoading && <div className="spinner">Загрузка…</div>}
      {error && (
        <div className="error-msg">
          {error instanceof Error ? error.message : "ошибка загрузки"}
        </div>
      )}
      {data?.length === 0 && (
        <div className="empty-state">Нет подключённых репозиториев</div>
      )}
      {data?.map((repo, i) => (
        <RepoCard key={repo.id} repo={repo} idx={i} />
      ))}
    </>
  );
}
