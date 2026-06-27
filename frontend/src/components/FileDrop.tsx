import { useRef, useState } from "react";

export function FileDrop({
  accept,
  multiple = false,
  busy = false,
  done,
  label,
  onFiles,
}: {
  accept: string;
  multiple?: boolean;
  busy?: boolean;
  done?: string | null;
  label: string;
  onFiles: (files: File[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const handle = (files: FileList | null) => {
    if (files && files.length) onFiles(Array.from(files));
  };

  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        handle(e.dataTransfer.files);
      }}
      className={`flex w-full flex-col items-center justify-center gap-1 rounded-xl border border-dashed px-3 py-4 text-center transition-[border-color,background-color,transform] duration-150 ease-out active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
        over ? "border-brand bg-brand-soft" : done ? "border-good/40 bg-good/5" : "border-line bg-bg hover:border-brand/50"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        hidden
        onChange={(e) => handle(e.target.files)}
      />
      {busy ? (
        <span className="text-[12px] text-muted">Uploading…</span>
      ) : done ? (
        <span className="max-w-full truncate text-[12px] font-medium text-good">✓ {done}</span>
      ) : (
        <span className="text-[12px] text-muted">{label}</span>
      )}
    </button>
  );
}
