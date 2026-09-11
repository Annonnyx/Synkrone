export function Tabs({
  items,
  value,
  onChange,
}: {
  items: Array<{ id: string; label: string }>;
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-[var(--line)] pb-2">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className="tab"
          data-active={value === item.id}
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
