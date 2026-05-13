import { clsx } from "clsx";

interface Column<T> {
  key: keyof T;
  label: string;
  align?: "left" | "right";
  render?: (value: T[keyof T], row: T) => React.ReactNode;
}

interface TopTableProps<T> {
  title: string;
  rows: T[];
  columns: Column<T>[];
  emptyLabel?: string;
  showViewAll?: boolean;
}

export function TopTable<T extends object>({
  title,
  rows,
  columns,
  emptyLabel = "No data for this period.",
  showViewAll = true,
}: TopTableProps<T>) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
        {showViewAll && rows.length > 0 && (
          <span
            aria-disabled
            title="Coming soon"
            className="cursor-not-allowed text-xs font-medium text-slate-500 hover:text-slate-400"
          >
            View all
          </span>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-600">{emptyLabel}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                {columns.map((col) => (
                  <th
                    key={String(col.key)}
                    className={clsx(
                      "pb-2 text-xs font-semibold uppercase tracking-widest text-slate-500",
                      col.align === "right" ? "text-right" : "text-left",
                    )}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {rows.map((row, i) => (
                <tr key={i} className="hover:bg-slate-800/30">
                  {columns.map((col) => (
                    <td
                      key={String(col.key)}
                      className={clsx(
                        "py-2.5 text-slate-300",
                        col.align === "right"
                          ? "text-right tabular-nums pl-4"
                          : "text-left pr-4",
                      )}
                    >
                      {col.render
                        ? col.render(row[col.key], row)
                        : String(row[col.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
