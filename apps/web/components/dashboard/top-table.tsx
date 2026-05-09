interface Column<T> {
  key: keyof T;
  label: string;
  render?: (value: T[keyof T], row: T) => React.ReactNode;
}

interface TopTableProps<T> {
  title: string;
  rows: T[];
  columns: Column<T>[];
  emptyLabel?: string;
}

export function TopTable<T extends Record<string, unknown>>({
  title,
  rows,
  columns,
  emptyLabel = "No data for this period.",
}: TopTableProps<T>) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-300">{title}</h3>
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
                    className="pb-2 text-left text-xs font-semibold uppercase tracking-widest text-slate-500"
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
                    <td key={String(col.key)} className="py-2.5 pr-4 text-slate-300">
                      {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? "")}
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
