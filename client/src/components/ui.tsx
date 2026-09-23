import { type ReactNode, useEffect } from "react";
import { create } from "zustand";

import { ApiError } from "../lib/api";

export function Button({
  children,
  onClick,
  kind = "primary",
  disabled,
  busy,
  type = "button",
  small,
  testId,
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean;
  busy?: boolean;
  type?: "button" | "submit";
  small?: boolean;
  testId?: string;
}) {
  return (
    <button
      type={type}
      className={`btn btn-${kind}${small ? " btn-small" : ""}`}
      onClick={onClick}
      disabled={disabled || busy}
      data-testid={testId}
    >
      {busy ? <span className="spinner spinner-inline" aria-hidden /> : null}
      {children}
    </button>
  );
}

export function Card({ children, className, onClick, testId }: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  testId?: string;
}) {
  return (
    <div
      className={`card${onClick ? " card-tap" : ""}${className ? " " + className : ""}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === "Enter" ? onClick() : undefined) : undefined}
      data-testid={testId}
    >
      {children}
    </div>
  );
}

export function Section({ title, children, aside }: { title?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="section">
      {title ? (
        <div className="section-head">
          <h2>{title}</h2>
          {aside}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Spinner({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="center muted" role="status">
      <span className="spinner" aria-hidden /> {label}
    </div>
  );
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return "Нет связи с сервером. Проверьте интернет.";
  return "Что-то пошло не так.";
}

export function ErrorView({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="center error-view" role="alert">
      <p>{errorText(error)}</p>
      {onRetry ? <Button kind="secondary" onClick={onRetry}>Повторить</Button> : null}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Sheet({ open, onClose, title, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Закрыть">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Progress({ value, max, marks = [] }: { value: number; max: number; marks?: number[] }) {
  const pct = Math.min(100, (value / Math.max(1, max)) * 100);
  return (
    <div className="bar" role="progressbar" aria-valuenow={value} aria-valuemax={max}>
      <div className="bar-fill" style={{ width: `${pct}%` }} />
      {marks.map((m) => (
        <div key={m} className="bar-mark" style={{ left: `${(m / max) * 100}%` }} />
      ))}
    </div>
  );
}

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "accent" }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

export function Toggle({ label, checked, onChange, hint }: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  hint?: string;
}) {
  return (
    <label className="toggle">
      <span>
        {label}
        {hint ? <small className="muted block">{hint}</small> : null}
      </span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

interface ToastState {
  text: string | null;
  tone: "info" | "good" | "bad";
  show: (text: string, tone?: "info" | "good" | "bad") => void;
  hide: () => void;
}

export const useToast = create<ToastState>((set) => ({
  text: null,
  tone: "info",
  show: (text, tone = "info") => {
    set({ text, tone });
    window.setTimeout(() => set({ text: null }), 3500);
  },
  hide: () => set({ text: null }),
}));

export function Toaster() {
  const { text, tone, hide } = useToast();
  if (!text) return null;
  return (
    <div className={`toast toast-${tone}`} role="status" onClick={hide}>
      {text}
    </div>
  );
}

export function colourOf(value: number): string {
  if (value < 40) return "red";
  if (value < 70) return "yellow";
  return "green";
}

export function ConfidenceBar({ value }: { value: number }) {
  return (
    <div className="conf-bar" aria-label={`Уверенность ${Math.round(value)}%`}>
      <div className={`conf-fill conf-${colourOf(value)}`} style={{ width: `${Math.max(2, value)}%` }} />
    </div>
  );
}
