import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "standard" | "wide";
}

export function Modal({ title, eyebrow, onClose, children, footer, size = "standard" }: ModalProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const closeHandlerRef = useRef(onClose);

  useEffect(() => {
    closeHandlerRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const applicationRoot = document.getElementById("root") ?? document.getElementById("main-content");
    const applicationWasInert = applicationRoot?.hasAttribute("inert") ?? false;
    const previousBodyOverflow = document.body.style.overflow;
    applicationRoot?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    const closeButton = panel?.querySelector<HTMLButtonElement>("[data-modal-close]");
    closeButton?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeHandlerRef.current();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (!applicationWasInert) applicationRoot?.removeAttribute("inert");
      document.body.style.overflow = previousBodyOverflow;
      previouslyFocused.current?.focus();
    };
  }, []);

  return createPortal(
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        ref={panelRef}
        className={`modal-panel modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="modal-header">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            <h2 id={titleId}>{title}</h2>
          </div>
          <button data-modal-close type="button" className="icon-button" onClick={onClose} aria-label={`Close ${title}`}>
            <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m5 5 10 10M15 5 5 15" /></svg>
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}
