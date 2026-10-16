interface ChartCardProps {
  title: string;
  subtitle?: string;
  legend?: { label: string; color: string }[];
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export function ChartCard({ title, subtitle, legend, children, actions }: ChartCardProps) {
  return (
    <div className="card shadow h-100">
      <div className="card-body d-flex flex-column p-3 p-md-4">
        {/* Header */}
        <div className="d-flex flex-column flex-sm-row align-items-stretch align-items-sm-start justify-content-between gap-2 mb-2">
          <div className="min-w-0">
            <h3
              className="fw-bold mb-0"
              style={{ color: "var(--color-text-primary)", fontSize: "14px" }}
            >
              {title}
            </h3>
            {subtitle && (
              <p className="mb-0 mt-1" style={{ color: "var(--color-text-tertiary)", fontSize: "12px" }}>
                {subtitle}
              </p>
            )}
          </div>
          {actions}
        </div>

        {/* Chart */}
        <div className="flex-grow-1 mt-3 min-w-0" style={{ position: "relative" }}>
          {children}
        </div>

        {/* Legend */}
        {legend && legend.length > 0 && (
          <div className="d-flex flex-wrap gap-3 mt-3">
            {legend.map((item) => (
              <span
                key={item.label}
                className="d-flex align-items-center gap-2"
                style={{ color: "var(--color-text-secondary)", fontSize: "11px" }}
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "2px",
                    background: item.color,
                    display: "inline-block",
                    flexShrink: 0,
                  }}
                />
                {item.label}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
