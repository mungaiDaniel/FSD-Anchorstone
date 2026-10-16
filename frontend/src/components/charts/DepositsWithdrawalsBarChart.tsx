import { Bar } from "react-chartjs-2";
import type { ChartData, ChartOptions } from "chart.js";
import { baseChartOptions, flowColors } from "@/lib/chartConfig";
import { formatKES, formatKESCompact } from "@/lib/utils";

// Rounded tops only, slim bars with a little air between each pair.
const BAR = { borderRadius: 6, borderSkipped: "bottom", maxBarThickness: 28, barPercentage: 0.8, categoryPercentage: 0.6 } as const;

interface Props {
  labels: string[];
  deposits: number[];
  withdrawals: number[];
  height?: number;
}

export function DepositsWithdrawalsBarChart({ labels, deposits, withdrawals, height = 260 }: Props) {
  const colors = flowColors();
  const data: ChartData<"bar"> = {
    labels,
    datasets: [
      { label: "Deposits", data: deposits, backgroundColor: colors.deposit, ...BAR },
      { label: "Withdrawals", data: withdrawals, backgroundColor: colors.withdrawal, ...BAR },
    ],
  };

  const base = baseChartOptions();
  const options: ChartOptions<"bar"> = {
    ...base,
    plugins: {
      ...base.plugins,
      tooltip: {
        ...base.plugins?.tooltip,
        callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatKES(ctx.parsed.y)}` },
      },
    },
    scales: {
      ...base.scales,
      x: {
        ...base.scales?.x,
        // "May 2026" → "May" so labels stay level on phones; the tooltip keeps the full month.
        ticks: { ...(base.scales?.x?.ticks ?? {}), maxRotation: 0, callback: (_v, i) => labels[i]?.split(" ")[0] ?? "" },
      },
      y: {
        ...base.scales?.y,
        ticks: { ...(base.scales?.y?.ticks ?? {}), callback: (v) => formatKESCompact(Number(v)) },
      },
    },
  };

  return (
    <div style={{ position: "relative", height }}>
      <Bar data={data} options={options} aria-label="Deposits and withdrawals by month" />
    </div>
  );
}
